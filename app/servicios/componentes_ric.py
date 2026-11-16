"""
Estado de una descripción por componentes RiC.

La descripción en RICORA se construye por partes que se conectan: el recurso
documental, sus agentes, la actividad que documenta y su función, sus
vínculos con otros recursos, el tiempo y el lugar, la custodia y las
manifestaciones, y la evidencia de lo que propuso el motor. Este servicio dice,
para cada componente, si está completo, parcial o por completar, y qué falta,
a partir de la misma vista interna que ve el archivista (`descripcion.detalle`).

No es una regla de publicación: un componente por completar no impide
publicar. Es la guía de trabajo y la base para el control de calidad.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental

COMPLETO, PARCIAL, POR_COMPLETAR = "completo", "parcial", "por_completar"
CONJUNTOS = ("fondo", "seccion", "subseccion", "serie", "subserie", "expediente", "coleccion")


def _con_agente(entidades: list[dict], codigos: tuple[str, ...]) -> list[dict]:
    return [e for e in entidades if e["tipo"] == "agente" and e["codigo_ric"] in codigos]


def _custodia_heredada(db: Session, recurso: RecursoDocumental) -> bool:
    """El custodio declarado en un nivel superior también custodia al documento (RiC-R039)."""
    from app.servicios.jerarquia import linea

    return any(db.scalar(select(Relacion.id).where(Relacion.origen_id == x.id, Relacion.estado == "vigente",
                                                   Relacion.codigo_ric == "has_or_had_holder").limit(1))
               for x in linea(db, recurso, incluir_propio=False))


def _en_serie(db: Session, recurso: RecursoDocumental) -> bool:
    """¿Está dentro de una serie o subserie del cuadro?"""
    from app.servicios.jerarquia import linea

    return any(x.nivel in ("serie", "subserie") for x in linea(db, recurso, incluir_propio=False))


def componentes(db: Session, recurso: RecursoDocumental, d: dict) -> dict:
    """`d` es la vista interna de `descripcion.detalle(db, recurso)`."""
    ents = d["entidades"]
    conjunto = recurso.nivel in CONJUNTOS
    salida = []

    def poner(clave, nombre, ric, estado, tiene, falta):
        salida.append({"clave": clave, "nombre": nombre, "ric": ric, "estado": estado, "tiene": tiene, "falta": falta})

    # 1. Recurso documental: identidad y contenido.
    faltan = [n for n, v in (("identificador", recurso.codigo_referencia), ("alcance y contenido", recurso.alcance_contenido))
              if not (v or "").strip()]
    poner("recurso", "Recurso documental", "rico:Record · rico:RecordSet · rico:RecordPart",
          COMPLETO if not faltan else PARCIAL,
          [f"Título: {recurso.titulo}"] + ([f"Forma documental: {d['forma_documental']['nombre']}"] if d.get("forma_documental") else []),
          faltan)

    # 2. Agentes: quién lo produjo y quién más intervino.
    productores = _con_agente(ents, ("has_creator", "has_accumulator"))
    otros = [e for e in ents if e["tipo"] == "agente" and e not in productores]
    poner("agentes", "Agentes", "rico:Agent · hasCreator, hasAddressee, hasOrHadSubject…",
          COMPLETO if productores else (PARCIAL if otros else POR_COMPLETAR),
          [f"{e['valor']} ({(e.get('rol') or e['codigo_ric']).replace('_', ' ')})" for e in productores + otros][:6],
          [] if productores else ["el productor (hasCreator)"])

    # 3. Funciones y actividades: por qué existe.
    actividades = [e for e in ents if e["tipo"] == "actividad"]
    con_funcion = [a for a in actividades if (a.get("contexto") or {}).get("tipo_actividad")]
    tiene = []
    for a in actividades[:4]:
        tipo = (a.get("contexto") or {}).get("tipo_actividad")
        tiene.append(f"{a['valor']}" + (f" → función: {tipo['nombre']}" if tipo else ""))
    poner("funciones", "Funciones y actividades", "rico:Activity · rico:ActivityType · documents (R033)",
          COMPLETO if con_funcion else (PARCIAL if actividades else POR_COMPLETAR), tiene,
          [] if con_funcion else (["la función (tipo de actividad) de la actividad"] if actividades
                                  else ["la actividad que documenta y su función"]))

    # 4. Relaciones con otros recursos (además de la jerarquía del cuadro).
    vinculos = d.get("secuencia", []) + d.get("vinculos", []) + d.get("tambien_en", []) + d.get("partes", [])
    if d.get("parte_de"):
        vinculos.append(d["parte_de"])
    sin_serie = recurso.nivel in ("expediente", "unidad_documental") and not _en_serie(db, recurso)
    poner("relaciones", "Relaciones con otros recursos", "precedesOrPreceded, hasReply, isRelatedTo, hasOrHadConstituent…",
          COMPLETO if vinculos else POR_COMPLETAR,
          ([f"Incluido en {d['incluido_en']['titulo']}"] if d.get("incluido_en") else [])
          + [v.get("titulo", "") for v in vinculos[:5]],
          ([] if vinculos else ["vínculos con otros documentos (respuesta, antecedente, borrador, copia…)"])
          + (["su serie o subserie del cuadro (sin ella no le aplica regla de retención)"] if sin_serie else []))

    # 5. Tiempo y lugar.
    fechas = [e for e in ents if e["tipo"] == "fecha"] or ([1] if recurso.fechas_extremas_edtf or recurso.fechas_extremas else [])
    lugares = [e for e in ents if e["tipo"] == "lugar"]
    falta = ([] if fechas else ["la fecha (de creación o extremas)"]) + ([] if lugares else ["el lugar"])
    poner("tiempo_lugar", "Lugares y tiempos", "rico:Date · rico:Place",
          COMPLETO if not falta else (PARCIAL if fechas or lugares else POR_COMPLETAR),
          ([recurso.fechas_extremas or "Fecha registrada"] if fechas else []) + [e["valor"] for e in lugares[:4]], falta)

    # 6. Custodia y manifestaciones.
    insts = d.get("instanciaciones", [])
    custodia = bool(_con_agente(ents, ("has_or_had_holder",))) or any(i.get("custodios") for i in insts) \
        or _custodia_heredada(db, recurso)
    con_inst = bool(insts) or conjunto  # un conjunto se manifiesta en sus miembros
    falta = ([] if custodia else ["el custodio (hasOrHadHolder)"]) + ([] if con_inst else ["la manifestación física o digital"])
    poner("custodia", "Custodia y manifestaciones", "hasOrHadHolder · rico:Instantiation",
          COMPLETO if not falta else (PARCIAL if custodia or insts else POR_COMPLETAR),
          [f"{len(insts)} manifestación(es)"] if insts else [], falta)

    # 7. Fuentes y validación: lo que propuso el motor tiene evidencia y fue revisado.
    del_motor = [e for e in ents if e.get("origen") in ("motor", "motor_editado")]
    sin_evidencia = [e for e in del_motor if not (e.get("fragmento") or "").strip()]
    sin_revisar = [e for e in ents if e.get("estado_revision") not in (None, "validado")]
    falta = ([f"{len(sin_evidencia)} relación(es) del motor sin evidencia textual"] if sin_evidencia else []) \
        + ([f"{len(sin_revisar)} dato(s) sin revisar"] if sin_revisar else [])
    poner("fuentes", "Fuentes y validación", "relationSource · relationCertainty · validación SHACL",
          COMPLETO if not falta else PARCIAL,
          [f"{len(del_motor)} relación(es) propuestas por el motor, {len(del_motor) - len(sin_evidencia)} con evidencia"]
          if del_motor else ["Todas las relaciones las registró una persona"], falta)

    return {"id": str(recurso.id), "componentes": salida,
            "completos": sum(c["estado"] == COMPLETO for c in salida), "total": len(salida)}


def de_recurso(db: Session, recurso_id: uuid.UUID) -> dict | None:
    from app.servicios import descripcion

    r = db.get(RecursoDocumental, recurso_id)
    return componentes(db, r, descripcion.detalle(db, r)) if r is not None else None
