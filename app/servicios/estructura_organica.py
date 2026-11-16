"""
Estructura orgánica: las dependencias de la entidad como agentes RiC.

En el cuadro de clasificación, cada sección y subsección es la agrupación de
lo que produjo una dependencia. En RiC esa dependencia es un agente
(rico:CorporateBody) que produce la agrupación (rico:hasCreator) y que está
subordinado a la dependencia superior (rico:hasOrHadSubordinate). Su vigencia
(desde cuándo existe y hasta cuándo) es la de ese agente.

- `ver` muestra el árbol de secciones y subsecciones con su agente, su
  superior y su vigencia, y lo que falta.
- `derivar` completa lo que falta a partir del cuadro: crea el agente de cada
  dependencia que no lo tiene (con el nombre de la agrupación), lo une a su
  agrupación como productor y lo subordina al agente de la dependencia
  superior. No inventa nombres: una agrupación con nombre provisional
  («Dependencia 3203») se deja sin agente hasta que se corrija.
- `fijar_vigencia` registra la vigencia de una dependencia (EDTF).
- Nada se borra; cada paso queda en la auditoría.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios.auditoria import registrar

NIVELES = ("seccion", "subseccion")


class ErrorEstructura(ValueError):
    pass


def _productor(db: Session, agrupacion_id: uuid.UUID) -> EntidadVocabulario | None:
    rid = db.scalar(select(Relacion.destino_id).where(
        Relacion.origen_id == agrupacion_id, Relacion.codigo_ric == "has_creator", Relacion.estado == "vigente",
        Relacion.destino_tipo == "entidad_vocabulario").limit(1))
    e = db.get(EntidadVocabulario, rid) if rid else None
    return e if e is not None and e.estado == "activa" else None


def _superior_de(db: Session, agente_id: uuid.UUID) -> EntidadVocabulario | None:
    rid = db.scalar(select(Relacion.origen_id).where(
        Relacion.destino_id == agente_id, Relacion.codigo_ric == "has_or_had_subordinate", Relacion.estado == "vigente",
        Relacion.origen_tipo == "entidad_vocabulario").limit(1))
    return db.get(EntidadVocabulario, rid) if rid else None


def _agrupaciones(db: Session, fondo: RecursoDocumental) -> list[RecursoDocumental]:
    return list(db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == fondo.id, RecursoDocumental.nivel.in_(NIVELES))
        .order_by(RecursoDocumental.codigo_referencia, RecursoDocumental.titulo)))


def ver(db: Session, fondo: RecursoDocumental) -> dict:
    from app.servicios import cuadro, fechas

    entidad = _productor(db, fondo.id)
    filas = []
    for a in _agrupaciones(db, fondo):
        ag = _productor(db, a.id)
        sup = _superior_de(db, ag.id) if ag else None
        padre = db.get(RecursoDocumental, a.incluido_en_id) if a.incluido_en_id else None
        filas.append({
            "id": str(a.id), "nivel": a.nivel, "codigo": a.codigo_referencia, "titulo": a.titulo,
            "superior_en_cuadro": padre.titulo if padre is not None and padre.nivel in NIVELES else None,
            "provisional": cuadro.es_nombre_provisional(a.titulo),
            "agente": {"id": str(ag.id), "nombre": ag.nombre, "vigencia": ag.existencia_edtf,
                       "vigencia_legible": fechas.legible(ag.existencia_edtf) if ag.existencia_edtf else None} if ag else None,
            "subordinada_a": {"id": str(sup.id), "nombre": sup.nombre} if sup else None,
        })
    return {"fondo": {"id": str(fondo.id), "titulo": fondo.titulo},
            "entidad": {"id": str(entidad.id), "nombre": entidad.nombre} if entidad else None,
            "dependencias": filas,
            "totales": {"dependencias": len(filas), "con_agente": sum(1 for f in filas if f["agente"]),
                        "subordinadas": sum(1 for f in filas if f["subordinada_a"]),
                        "con_vigencia": sum(1 for f in filas if f["agente"] and f["agente"]["vigencia"]),
                        "provisionales": sum(1 for f in filas if f["provisional"])}}


def derivar(db: Session, fondo: RecursoDocumental, usuario_id: uuid.UUID) -> dict:
    from app.servicios import autoridad, cuadro

    creados = unidos = subordinados = 0
    omitidos: list[str] = []
    agente_de: dict[uuid.UUID, EntidadVocabulario] = {}
    entidad = _productor(db, fondo.id)
    agrupaciones = _agrupaciones(db, fondo)
    por_id = {a.id: a for a in agrupaciones}

    def profundidad(a: RecursoDocumental) -> int:
        n, x = 0, a
        while x.incluido_en_id in por_id and n < 12:
            x, n = por_id[x.incluido_en_id], n + 1
        return n

    for a in sorted(agrupaciones, key=profundidad):  # el superior llega antes que sus subordinadas
        ag = _productor(db, a.id)
        if ag is None:
            if cuadro.es_nombre_provisional(a.titulo):
                omitidos.append(a.titulo)
                continue
            from app.servicios import vocabulario

            ag, nuevo = vocabulario.obtener_o_crear(db, fondo_id=fondo.id, clase="agente", nombre=a.titulo,
                                                    subtipo="entidad_corporativa", usuario_id=usuario_id)
            creados += int(nuevo)
            db.add(Relacion(origen_tipo="recurso_documental", origen_id=a.id, destino_tipo="entidad_vocabulario",
                            destino_id=ag.id, tipo_relacion="procedencia", codigo_ric="has_creator", rol="productor",
                            origen="persona", confirmada_por_id=usuario_id))
            db.flush()
            unidos += 1
        agente_de[a.id] = ag
        superior = agente_de.get(a.incluido_en_id) if a.incluido_en_id else None
        if superior is None and a.nivel == "seccion":
            superior = entidad
        if superior is not None and superior.id != ag.id and _superior_de(db, ag.id) is None:
            try:
                autoridad.vincular(db, tipo="subordinado", desde=superior, con_tipo="entidad_vocabulario", con_id=ag.id,
                                   usuario_id=usuario_id)
                subordinados += 1
            except autoridad.ErrorAutoridad:
                pass  # ya estaba o formaría un ciclo: se deja como está
    registrar(db, modulo="instrumentos", accion="estructura_organica_derivada", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=fondo.id,
              detalle=f"{creados} agente(s) creados, {unidos} unidos, {subordinados} subordinados",
              nuevo={"creados": creados, "unidos": unidos, "subordinados": subordinados, "omitidos": omitidos})
    return {"creados": creados, "unidos": unidos, "subordinados": subordinados, "omitidos": omitidos}


def fijar_vigencia(db: Session, agente: EntidadVocabulario, vigencia: str, usuario_id: uuid.UUID) -> None:
    from app.servicios import autoridad

    if agente.clase != "agente":
        raise ErrorEstructura("La vigencia se fija sobre el agente de la dependencia.")
    try:
        autoridad.actualizar(db, agente, {"existencia_edtf": vigencia}, usuario_id)
    except autoridad.ErrorAutoridad as exc:
        raise ErrorEstructura(str(exc)) from exc
