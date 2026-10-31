"""
La digitalización de un original físico y su verificación (requisito 5).

La digitalización ya es, en RiC-O, una actividad que afecta al original y
resulta en la copia digital: la relación «instanciación derivada» (RiC-R014)
entre el original físico y el archivo. Aquí se guarda lo que esa relación no
dice: quién digitalizó, cuándo, con qué equipo y a qué resolución, y cada
verificación de la copia con sus comprobaciones. «Digitalizado» no significa
«verificado»: el estado sale de la última verificación.
"""

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora

# Lo que se comprueba de la copia frente al original.
COMPROBACIONES = {
    "completa": "Están todas las páginas o folios del original",
    "legible": "Se lee todo el contenido",
    "fiel": "Orientación, color y escala corresponden al original",
    "integra": "El archivo abre y su huella coincide con la registrada",
}
RESULTADO = ("verificada", "con_problemas")


class Digitalizacion(Base):
    __tablename__ = "digitalizaciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    relacion_id = Column(UUID(as_uuid=True), ForeignKey("relaciones.id"), nullable=False, unique=True)
    responsable = Column(String(200), nullable=True)  # quien digitalizó (puede no ser usuario del sistema)
    fecha = Column(Date, nullable=True)
    equipo = Column(String(200), nullable=True)
    resolucion_ppp = Column(Integer, nullable=True)
    nota = Column(Text, nullable=True)
    registrado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    registrado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class VerificacionDigitalizacion(Base):
    """Cada verificación queda; ninguna se borra ni se edita. Vale la última."""

    __tablename__ = "verificaciones_digitalizacion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    relacion_id = Column(UUID(as_uuid=True), ForeignKey("relaciones.id"), nullable=False, index=True)
    comprobaciones = Column(JSONB, nullable=False)  # {clave de COMPROBACIONES: bool}
    resultado = Column(String(20), nullable=False)  # RESULTADO
    nota = Column(Text, nullable=True)
    verificado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    verificado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
