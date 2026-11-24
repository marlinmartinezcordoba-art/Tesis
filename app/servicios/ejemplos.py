"""Ejemplos validados para el motor: RICORA aprende de lo que la archivista ya aprobó.

El modelo de lenguaje no se reentrena (3.4 y 3.7 de la tesis). Lo que mejora es lo que se le muestra: con
cada documento recibe una o dos descripciones que una persona ya validó en el mismo fondo, como modelo del
estilo, del nivel de detalle y de los roles. Así cada descripción publicada ayuda a la siguiente.

Reglas:
- Solo descripciones publicadas y sin reserva (Ley 1712): su contenido sale hacia el servicio del motor.
- Nunca un documento del conjunto de prueba de una evaluación: sería mostrarle al motor la respuesta.
- Mientras un documento está en una evaluación en curso, los ejemplos son los que quedaron congelados al
  iniciarla (los del conjunto de desarrollo), los mismos para todo el conjunto de prueba.
- Se prefieren los del mismo tipo documental que el documento declara en su encabezado.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario
from app.models.evaluacion import Evaluacion, EvaluacionDocumento
from app.models.recurso_documental import RecursoDocumental

MAXIMO = 2
ENTIDADES_POR_EJEMPLO = 25
ENCABEZADO = 800


def _normal(texto: str | None) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower()) if not unicodedata.combining(c))


def _de_prueba(db: Session) -> set:
    """Los Record Resources de documentos de prueba de cualquier evaluación: nunca van como ejemplo."""
    from app.models.descripcion import Relacion

    insts = list(db.scalars(select(EvaluacionDocumento.instanciacion_id).where(EvaluacionDocumento.conjunto == "prueba")))
    if not insts:
        return set()
    return set(db.scalars(select(Relacion.origen_id).where(
        Relacion.destino_id.in_(insts), Relacion.codigo_ric == "has_or_had_instantiation")))


def resumen(db: Session, recurso: RecursoDocumental) -> dict:
    """Lo que el motor ve de un ejemplo: título, alcance y las entidades con su tipo y su rol."""
    from app.servicios import descripcion

    d = descripcion.detalle(db, recurso)
    entidades = [{"tipo": e["tipo"], "rol": e.get("rol"), "valor": e["valor"]} for e in d.get("entidades", [])
                 if e.get("tipo") and e.get("valor")][:ENTIDADES_POR_EJEMPLO]
    return {"id": str(recurso.id), "titulo": recurso.titulo, "alcance": recurso.alcance_contenido or "",
            "entidades": entidades}


def _candidatos(db: Session, fondo_id: uuid.UUID) -> list[RecursoDocumental]:
    from app.servicios import derechos

    excluir = _de_prueba(db)
    filas = db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == fondo_id, RecursoDocumental.publicado_en.is_not(None),
        RecursoDocumental.nivel == "unidad_documental").order_by(RecursoDocumental.publicado_en.desc()).limit(60)).all()
    return [r for r in filas if r.id not in excluir and not derechos.restringe(derechos.declaracion_de_recurso(db, r))]


def en_evaluacion(db: Session, instanciaciones: list[uuid.UUID]) -> Evaluacion | None:
    if not instanciaciones:
        return None
    return db.scalar(select(Evaluacion).join(EvaluacionDocumento, EvaluacionDocumento.evaluacion_id == Evaluacion.id)
                     .where(Evaluacion.estado == "en_curso", EvaluacionDocumento.instanciacion_id.in_(instanciaciones))
                     .limit(1))


def para(db: Session, fondo_id: uuid.UUID, instanciaciones: list[uuid.UUID], texto: str,
         excluir: set | None = None) -> list[dict]:
    """Los ejemplos para describir estos documentos."""
    ev = en_evaluacion(db, instanciaciones)
    if ev is not None:  # congelados al iniciar: los mismos para todo el conjunto de prueba
        ids = [uuid.UUID(i) for i in (ev.version_congelada or {}).get("ejemplos", [])]
        return [resumen(db, r) for r in (db.get(RecursoDocumental, i) for i in ids) if r is not None]
    excluir = excluir or set()
    candidatos = [r for r in _candidatos(db, fondo_id) if r.id not in excluir]
    cabeza = _normal(texto[:ENCABEZADO])
    formas = {e.id: _normal(e.nombre) for e in db.scalars(select(EntidadVocabulario).where(
        EntidadVocabulario.id.in_([r.forma_documental_id for r in candidatos if r.forma_documental_id])))}
    mismo_tipo = [r for r in candidatos if r.forma_documental_id and formas.get(r.forma_documental_id)
                  and formas[r.forma_documental_id] in cabeza]
    elegidos = (mismo_tipo + [r for r in candidatos if r not in mismo_tipo])[:MAXIMO]
    return [resumen(db, r) for r in elegidos]


def congelar(db: Session, ev: Evaluacion) -> list[str]:
    """Al iniciar una evaluación: las descripciones validadas del conjunto de desarrollo que servirán de ejemplo
    para todo el conjunto de prueba (hasta MAXIMO, las más recientes)."""
    from app.models.descripcion import Relacion

    insts = [d.instanciacion_id for d in db.scalars(select(EvaluacionDocumento).where(
        EvaluacionDocumento.evaluacion_id == ev.id, EvaluacionDocumento.conjunto == "desarrollo"))]
    if not insts:
        return []
    ids = set(db.scalars(select(Relacion.origen_id).where(
        Relacion.destino_id.in_(insts), Relacion.codigo_ric == "has_or_had_instantiation")))
    recursos = db.scalars(select(RecursoDocumental).where(RecursoDocumental.id.in_(ids),
                                                          RecursoDocumental.publicado_en.is_not(None))
                          .order_by(RecursoDocumental.publicado_en.desc())).all() if ids else []
    return [str(r.id) for r in recursos[:MAXIMO]]


def texto(ejemplos: list[dict] | None) -> str:
    """Cómo los lee el motor. Van en el pedido, como el vocabulario: son datos del fondo, no instrucciones."""
    if not ejemplos:
        return ""
    lineas = ["EJEMPLOS DE DESCRIPCIONES YA VALIDADAS POR LA ARCHIVISTA EN ESTE FONDO (muestran el estilo, el nivel de "
              "detalle y cómo se asignan los roles; son de OTROS documentos: no copies sus datos, describe solo lo que "
              "dice el documento actual):"]
    for i, e in enumerate(ejemplos, start=1):
        lineas.append(f"[EJEMPLO {i}] Título: {e['titulo']}")
        if e.get("alcance"):
            lineas.append(f"Alcance y contenido: {e['alcance'][:900]}")
        for x in e.get("entidades", []):
            rol = f" ({x['rol']})" if x.get("rol") else ""
            lineas.append(f"- {x['tipo']}{rol}: {x['valor']}")
        lineas.append(f"[FIN DEL EJEMPLO {i}]")
    return "\n".join(lineas) + "\n\n"
