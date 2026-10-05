"""
Versiones de una descripción (brecha RF-RIC-001).

Cada vez que una descripción publicada cambia (publicación, corrección,
restauración) queda una versión numerada con la instantánea completa de
sus atributos y del contexto (entidades, documentos, partes, secuencia),
quién la hizo, cuándo y por qué. Las versiones no se modifican ni se borran
(disparador de la migración 0037): restaurar una versión anterior crea una
versión nueva.
"""

import uuid

from sqlalchemy import Column, DateTime, FetchedValue, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora


class VersionDescripcion(Base):
    __tablename__ = "versiones_descripcion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recurso_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    numero = Column(Integer, nullable=False)
    # publicacion | edicion | restauracion | estado_inicial | agrupacion
    motivo = Column(String(30), nullable=False)
    restaurada_de = Column(Integer, nullable=True)
    autor_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    # {"atributos": {...}, "contexto": {...} | null}
    contenido = Column(JSONB, nullable=False)
    huella = Column(String(64), nullable=False, server_default=FetchedValue())  # la calcula la base

    __table_args__ = (UniqueConstraint("recurso_id", "numero", name="uq_version_descripcion_numero"),)
