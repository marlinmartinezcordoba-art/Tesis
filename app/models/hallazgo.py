"""
Hallazgos de conformidad con RiC (registro manual del equipo) y etiquetas
legibles de las versiones de la instrucción del motor (prompt de
auditoría v7, §5 y §5bis).
"""

import uuid

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.db.base import Base, ahora

ESTADO_HALLAZGO = ("abierto", "en_correccion", "cerrado")
# Los siete módulos del sistema (los que un hallazgo puede afectar).
COMPONENTES = ("autenticacion", "ingesta", "descripcion", "vocabularios", "instrumentos", "preservacion", "auditoria")


class HallazgoConformidad(Base):
    __tablename__ = "hallazgos_conformidad"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    numero = Column(Integer, nullable=False, unique=True)  # para citarlo («hallazgo 4»)
    titulo = Column(String(300), nullable=False)  # no se edita después de creado
    descripcion = Column(Text, nullable=False)  # tampoco
    componentes = Column(ARRAY(String(20)), nullable=False)
    estado = Column(Enum(*ESTADO_HALLAZGO, name="estado_hallazgo"), nullable=False, default="abierto", index=True)
    abierto_en = Column(Date, nullable=False)
    cerrado_en = Column(Date, nullable=True)
    accion = Column(Text, nullable=True)  # qué se hizo o qué falta para cerrarlo
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)  # vacío: sembrado al desplegar
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    actualizado_en = Column(DateTime(timezone=True), nullable=True)


class EtiquetaVersionPrompt(Base):
    """Nombre fácil de recordar («v3») para una versión ya calculada de la
    instrucción. Nunca la reemplaza: la trazabilidad sigue siendo el
    resumen criptográfico."""

    __tablename__ = "etiquetas_version_prompt"

    version = Column(String(16), primary_key=True)  # el identificador calculado (SHA-256 truncado)
    etiqueta = Column(String(40), nullable=False, unique=True)
    nota = Column(String(300), nullable=True)
    asignada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    asignada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
