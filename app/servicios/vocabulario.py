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
