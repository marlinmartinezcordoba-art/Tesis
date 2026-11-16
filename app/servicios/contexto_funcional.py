"""
Contexto funcional del fondo: por qué existen los documentos.

En RiC-O una función es un tipo de actividad (rico:ActivityType). Para cada
función del fondo se reúne lo que el grafo ya dice de ella: las actividades de
ese tipo (hasActivityType), quién las ejerce (performsOrPerformed), los
mandatos que las regulan (regulatesOrRegulated), su periodo, las series que la
función produce según la TRD y los documentos que documentan cada actividad
(RiC-R033). Se navega en los dos sentidos: de la función a los documentos y,
desde la ficha del documento, a la función que lo originó.

Los documentos se cuentan solo dentro de lo que la persona puede ver (la misma
regla del catálogo y el buscador): para el rol de consulta, nada reservado.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental

MUESTRA = 8  # documentos que se nombran por actividad; el resto se cuenta


def _breve(e: EntidadVocabulario) -> dict:
    return {"id": str(e.id), "nombre": e.nombre, "clase": e.clase}


def _vecinos(db: Session, codigo: str, *, hacia: uuid.UUID | None = None, desde: uuid.UUID | None = None) -> list:
    q = select(Relacion).where(Relacion.codigo_ric == codigo, Relacion.estado == "vigente")
    q = q.where(Relacion.destino_id == hacia) if hacia else q.where(Relacion.origen_id == desde)
    return list(db.scalars(q))


def de_fondo(db: Session, fondo: RecursoDocumental, ver_restringidos: bool) -> dict:
    from app.servicios import busqueda, descripcion

    visibles = busqueda._alcance_del_fondo(db, fondo, ver_restringidos).visibles

    def documentos(ids: set[uuid.UUID]) -> dict:
        vistos = [visibles[i] for i in ids if i in visibles and visibles[i].nivel != "fondo"]
        vistos.sort(key=lambda r: r.titulo.lower())
        return {"total": len(vistos),
                "ejemplos": [{"id": str(r.id), "titulo": r.titulo, "nivel": r.nivel} for r in vistos[:MUESTRA]]}

    def actividad(a: EntidadVocabulario) -> dict:
        agentes = [db.get(EntidadVocabulario, r.origen_id) for r in _vecinos(db, "performs_or_performed", hacia=a.id)]
        mandatos = [db.get(EntidadVocabulario, r.origen_id) for r in _vecinos(db, "regulates_or_regulated", hacia=a.id)
                    if r.origen_tipo == "entidad_vocabulario"]
        docs = {r.origen_id for r in _vecinos(db, "documents", hacia=a.id) if r.origen_tipo == "recurso_documental"}
        return {**_breve(a), "ejercida_por": [_breve(x) for x in agentes if x is not None],
                "mandatos": [_breve(x) for x in mandatos if x is not None and x.clase == "mandato"],
                "periodo": descripcion._fecha_de(db, a.id, "is_date_associated_with"), "documentos": documentos(docs)}

    entidades = db.scalars(select(EntidadVocabulario).where(
        EntidadVocabulario.fondo_id == fondo.id, EntidadVocabulario.estado == "activa",
        EntidadVocabulario.clase.in_(("tipo_actividad", "actividad"))).order_by(EntidadVocabulario.nombre)).all()
    funciones, con_funcion, sueltas = [], set(), []
    for f in (e for e in entidades if e.clase == "tipo_actividad"):
        actividades = [db.get(EntidadVocabulario, r.origen_id) for r in _vecinos(db, "has_activity_type", hacia=f.id)]
        actividades = [a for a in actividades if a is not None and a.estado == "activa"]
        con_funcion |= {a.id for a in actividades}
        series = [visibles[r.destino_id] for r in _vecinos(db, "is_related_to", desde=f.id)
                  if r.rol == "serie_producida" and r.destino_id in visibles]
        detalle = [actividad(a) for a in sorted(actividades, key=lambda x: x.nombre.lower())]
        docs = {d for a in actividades for r in _vecinos(db, "documents", hacia=a.id) if (d := r.origen_id)}
        funciones.append({**_breve(f), "actividades": detalle,
                          "series": [{"id": str(s.id), "titulo": s.titulo, "codigo": s.codigo_referencia} for s in series],
                          "documentos": documentos(docs)})
    for a in (e for e in entidades if e.clase == "actividad" and e.id not in con_funcion):
        sueltas.append(actividad(a))
    return {"fondo": {"id": str(fondo.id), "titulo": fondo.titulo}, "funciones": funciones,
            "actividades_sin_funcion": sueltas,
            "totales": {"funciones": len(funciones), "actividades": len(con_funcion) + len(sueltas),
                        "con_documentos": sum(1 for f in funciones if f["documentos"]["total"])}}
