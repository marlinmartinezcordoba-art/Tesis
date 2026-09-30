"""
Módulo 5 · Preservación digital: metadatos PREMIS anclados en la
Instantiation (RiC-E06), nunca en el Record Resource.

- VerificacionIntegridad: evento PREMIS «fixity check», uno por cada
  verificación (periódica o manual), con su resultado.
- Migracion: evento PREMIS «migration». Se aprueba siempre de forma
  explícita; si termina bien, deja una Instantiation nueva enlazada a la
  original por RiC-R015 migrated into. La original no se toca.
"""

import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora

RESULTADO_INTEGRIDAD = ("integra", "alterada", "ausente")
ORIGEN_VERIFICACION = ("periodica", "manual")
ESTADO_MIGRACION = ("en_curso", "completada", "fallida", "esperando_archivo")
MODO_MIGRACION = ("automatica", "manual")


class VerificacionIntegridad(Base):
    __tablename__ = "verificaciones_integridad"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False, index=True)
    fecha = Column(DateTime(timezone=True), default=ahora, nullable=False, index=True)
    resultado = Column(Enum(*RESULTADO_INTEGRIDAD, name="resultado_integridad"), nullable=False)
    algoritmo = Column(String(20), nullable=False, default="SHA-256")
    huella_registrada = Column(String(64), nullable=True)
    huella_calculada = Column(String(64), nullable=True)
    origen = Column(Enum(*ORIGEN_VERIFICACION, name="origen_verificacion"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)


class Migracion(Base):
    __tablename__ = "migraciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_origen_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False, index=True)
    destino = Column(String(40), nullable=False)  # clave del formato destino (ver servicios/preservacion.py)
    destino_nombre = Column(String(120), nullable=False)
    modo = Column(Enum(*MODO_MIGRACION, name="modo_migracion"), nullable=False)
    estado = Column(Enum(*ESTADO_MIGRACION, name="estado_migracion"), nullable=False, index=True)
    herramienta = Column(String(200), nullable=True)
    mensaje = Column(String(500), nullable=True)
    aprobada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    aprobada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    terminada_en = Column(DateTime(timezone=True), nullable=True)
    instanciacion_resultado_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=True)
