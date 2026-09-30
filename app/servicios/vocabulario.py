"""
Servicio de vocabularios y control de autoridad.

verificar() es el servicio único de comparación por similitud: lo usa el
módulo de descripción antes de confirmar un agente, un lugar o una forma
documental, y lo usará la detección periódica de candidatos a fusión del
módulo de vocabularios. Nadie más compara nombres por su cuenta.

Comparación: trigramas de PostgreSQL (pg_trgm) sobre el nombre en
minúsculas y sin tildes (decisión documentada en
documentacion/modulo-2-descripcion.md).
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental


def normalizar(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


@dataclass
class Coincidencia:
    id: uuid.UUID
    nombre: str
    subtipo: str | None
    similitud: float
    conexiones: int


def conexiones(db: Session, entidad_id: uuid.UUID) -> int:
    """Documentos conectados a la entidad (relaciones vigentes, más los que
    la usan como forma documental)."""
    por_relacion = db.scalar(select(func.count(func.distinct(Relacion.origen_id))).where(
        Relacion.destino_id == entidad_id, Relacion.estado == "vigente")) or 0
    por_forma = db.scalar(select(func.count(RecursoDocumental.id)).where(
        RecursoDocumental.forma_documental_id == entidad_id)) or 0
    return por_relacion + por_forma


def verificar(db: Session, fondo_id: uuid.UUID, clase: str, valor: str, limite: int = 5) -> list[Coincidencia]:
    """Entidades activas del mismo tipo en el fondo que se parecen al valor
    propuesto, de mayor a menor coincidencia."""
    buscado = normalizar(valor)
    if not buscado:
        return []
    similitud = func.similarity(EntidadVocabulario.nombre_normalizado, buscado)
    filas = db.execute(
        select(EntidadVocabulario, similitud.label("s"))
        .where(EntidadVocabulario.fondo_id == fondo_id,
               EntidadVocabulario.clase == clase,
               EntidadVocabulario.estado == "activa",
               or_(similitud >= settings.umbral_similitud, EntidadVocabulario.nombre_normalizado == buscado))
        .order_by(similitud.desc(), EntidadVocabulario.nombre)
        .limit(limite)
    ).all()
    return [Coincidencia(id=e.id, nombre=e.nombre, subtipo=e.subtipo, similitud=round(float(s), 2),
                         conexiones=conexiones(db, e.id)) for e, s in filas]


def crear(db: Session, *, fondo_id: uuid.UUID, clase: str, nombre: str, subtipo: str | None, origen: str,
          confianza: float | None, motor: str | None, usuario_id: uuid.UUID) -> EntidadVocabulario:
    entidad = EntidadVocabulario(
        id=uuid.uuid4(), fondo_id=fondo_id, clase=clase, subtipo=subtipo, nombre=" ".join(nombre.split()),
        nombre_normalizado=normalizar(nombre), origen=origen, confianza=confianza, motor=motor,
        estado_revision="validado", creado_por_id=usuario_id,
    )
    db.add(entidad)
    return entidad


# --- Módulo 3: navegación, detección de candidatos y fusión -------------------------------------------

def conexiones_de(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Conexiones de varias entidades a la vez (para listados)."""
    if not ids:
        return {}
    por_relacion = dict(db.execute(
        select(Relacion.destino_id, func.count(func.distinct(Relacion.origen_id)))
        .where(Relacion.destino_id.in_(ids), Relacion.estado == "vigente").group_by(Relacion.destino_id)).all())
    por_forma = dict(db.execute(
        select(RecursoDocumental.forma_documental_id, func.count(RecursoDocumental.id))
        .where(RecursoDocumental.forma_documental_id.in_(ids)).group_by(RecursoDocumental.forma_documental_id)).all())
    return {i: por_relacion.get(i, 0) + por_forma.get(i, 0) for i in ids}


def documentos_conectados(db: Session, entidad_id: uuid.UUID, historicos: bool = False) -> list[RecursoDocumental]:
    """Descripciones conectadas hoy a la entidad; con `historicos`, las que
    la citaban antes de que se fusionara en otra."""
    campo = Relacion.destino_original_id if historicos else Relacion.destino_id
    ids = set(db.scalars(select(Relacion.origen_id).where(campo == entidad_id, Relacion.estado == "vigente")))
    if not historicos:
        ids |= set(db.scalars(select(RecursoDocumental.id).where(RecursoDocumental.forma_documental_id == entidad_id)))
    if not ids:
        return []
    return list(db.scalars(select(RecursoDocumental).where(RecursoDocumental.id.in_(ids))
                           .order_by(RecursoDocumental.titulo)))


class ErrorFusion(Exception):
    pass


def fusionar(db: Session, *, definitiva: EntidadVocabulario, absorbida: EntidadVocabulario, usuario_id: uuid.UUID,
             sugerencia=None, ip: str | None = None) -> int:
    """Fusiona `absorbida` en `definitiva` en una sola transacción. Las
    relaciones se redirigen (guardando a quién apuntaban), la absorbida no se
    borra: queda «fusionada» y enlazada a la definitiva. Devuelve cuántas
    relaciones se movieron."""
    from sqlalchemy import update

    from app.db.base import ahora
    from app.models.descripcion import SugerenciaFusion
    from app.servicios.auditoria import registrar

    if definitiva.id == absorbida.id:
        raise ErrorFusion("Elija dos entidades distintas.")
    if definitiva.fondo_id != absorbida.fondo_id or definitiva.clase != absorbida.clase:
        raise ErrorFusion("Solo se fusionan entidades del mismo tipo y del mismo fondo.")
    if definitiva.estado != "activa" or absorbida.estado != "activa":
        raise ErrorFusion("Alguna de las dos entidades ya fue fusionada antes.")
    conexiones_antes = conexiones_de(db, [definitiva.id, absorbida.id])
    movidas = db.execute(
        update(Relacion).where(Relacion.destino_id == absorbida.id, Relacion.estado == "vigente")
        .values(destino_id=definitiva.id, destino_original_id=func.coalesce(Relacion.destino_original_id, absorbida.id))
    ).rowcount
    formas = db.execute(update(RecursoDocumental).where(RecursoDocumental.forma_documental_id == absorbida.id)
                        .values(forma_documental_id=definitiva.id)).rowcount
    # Las que ya se habían fusionado en la absorbida pasan a apuntar a la definitiva.
    db.execute(update(EntidadVocabulario).where(EntidadVocabulario.fusionada_en_id == absorbida.id)
               .values(fusionada_en_id=definitiva.id))
    absorbida.estado = "fusionada"
    absorbida.fusionada_en_id = definitiva.id
    momento = ahora()
    pendientes = db.scalars(select(SugerenciaFusion).where(
        SugerenciaFusion.estado == "pendiente",
        (SugerenciaFusion.entidad_a_id == absorbida.id) | (SugerenciaFusion.entidad_b_id == absorbida.id))).all()
    for s in pendientes:
        if sugerencia is not None and s.id == sugerencia.id:
            continue
        s.estado, s.resuelta_en = "obsoleta", momento
    if sugerencia is not None:
        sugerencia.estado, sugerencia.resuelta_en = "aprobada", momento
        sugerencia.resuelta_por_id, sugerencia.definitiva_id = usuario_id, definitiva.id
    registrar(db, modulo="vocabularios", accion="fusion_vocabulario", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=definitiva.id, ip=ip,
              anterior={"absorbida": {"id": str(absorbida.id), "nombre": absorbida.nombre,
                                      "conexiones": conexiones_antes[absorbida.id]},
                        "definitiva": {"id": str(definitiva.id), "nombre": definitiva.nombre,
                                       "conexiones": conexiones_antes[definitiva.id]}},
              nuevo={"definitiva": str(definitiva.id), "relaciones_movidas": movidas + formas,
                     "origen": "sugerencia" if sugerencia is not None else "manual"},
              detalle=f"«{absorbida.nombre}» se fusionó en «{definitiva.nombre}».")
    return movidas + formas


def detectar_candidatos(db: Session, fondo_id: uuid.UUID | None = None) -> int:
    """Compara entre sí las entidades activas del mismo tipo y fondo con el
    mismo criterio de similitud que verificar(), y registra una sugerencia
    por cada par muy parecido en el que ambas tienen pocas conexiones. No
    fusiona nada. Un par ya sugerido (en cualquier estado) no se repite."""
    from sqlalchemy.orm import aliased

    from app.models.descripcion import SugerenciaFusion
    from app.servicios import parametros

    umbral = int(parametros.leer(db, "fusion_similitud_pct")) / 100
    maximo = int(parametros.leer(db, "fusion_max_conexiones"))
    a, b = aliased(EntidadVocabulario), aliased(EntidadVocabulario)
    similitud = func.similarity(a.nombre_normalizado, b.nombre_normalizado)
    consulta = (select(a, b, similitud.label("s"))
                .join(b, (a.fondo_id == b.fondo_id) & (a.clase == b.clase) & (a.id < b.id))
                .where(a.estado == "activa", b.estado == "activa", similitud >= umbral))
    if fondo_id is not None:
        consulta = consulta.where(a.fondo_id == fondo_id)
    pares = db.execute(consulta).all()
    if not pares:
        return 0
    conexiones = conexiones_de(db, list({x.id for p in pares for x in p[:2]}))
    existentes = set(db.execute(select(SugerenciaFusion.entidad_a_id, SugerenciaFusion.entidad_b_id)).all())
    nuevas = 0
    for x, y, s in pares:
        if (x.id, y.id) in existentes or conexiones[x.id] > maximo or conexiones[y.id] > maximo:
            continue
        db.add(SugerenciaFusion(fondo_id=x.fondo_id, clase=x.clase, entidad_a_id=x.id, entidad_b_id=y.id,
                                similitud=round(float(s), 2)))
        nuevas += 1
    return nuevas


CLAVE_ULTIMA_DETECCION = "fusion_ultima_deteccion"


def deteccion_periodica(db: Session) -> int | None:
    """La llama el trabajador en cada vuelta: si ya pasó el intervalo
    configurado desde la última búsqueda, busca candidatos en todos los
    fondos. Devuelve cuántas sugerencias nuevas creó, o None si no tocaba."""
    from datetime import datetime, timedelta

    from app.db.base import ahora
    from app.models.parametro import Parametro
    from app.servicios import parametros

    horas = int(parametros.leer(db, "fusion_horas_deteccion"))
    fila = db.get(Parametro, CLAVE_ULTIMA_DETECCION)
    if fila is not None and ahora() - datetime.fromisoformat(fila.valor) < timedelta(hours=horas):
        return None
    nuevas = detectar_candidatos(db)
    if fila is None:
        db.add(Parametro(clave=CLAVE_ULTIMA_DETECCION, valor=ahora().isoformat()))
    else:
        fila.valor = ahora().isoformat()
    db.commit()
    return nuevas
