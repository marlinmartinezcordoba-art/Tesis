"""
Evaluación ciega del motor frente a archivistas (objetivo 3 de la tesis).

Una evaluación reúne documentos aún no descritos. Para cada uno, el motor
propone una descripción que nadie ve; archivistas lo describen a ciegas
(patrón de referencia) y, en otra condición, con la propuesta delante
(asistida). Además califican la propuesta con una rúbrica. Nada se borra:
una anotación se anula, no se elimina.
"""

import uuid

from sqlalchemy import (CheckConstraint, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora

ESTADO_EVALUACION = ("preparacion", "en_curso", "cerrada")
CONDICION = ("ciega", "asistida")
ESTADO_ANOTACION = ("en_curso", "enviada", "anulada")
CRITERIOS = ("exactitud", "completitud", "pertinencia")


class Evaluacion(Base):
    __tablename__ = "evaluaciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    protocolo = Column(Text, nullable=True)  # cómo se hizo: quiénes, instrucciones, criterios
    umbral_similitud = Column(Float, nullable=False, default=0.85)
    estado = Column(Enum(*ESTADO_EVALUACION, name="estado_evaluacion"), nullable=False, default="preparacion")
    creada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    creada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    iniciada_en = Column(DateTime(timezone=True), nullable=True)
    cerrada_en = Column(DateTime(timezone=True), nullable=True)


class EvaluacionDocumento(Base):
    __tablename__ = "evaluacion_documentos"
    __table_args__ = (UniqueConstraint("evaluacion_id", "instanciacion_id"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("evaluaciones.id"), nullable=False, index=True)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False)
    propuesta = Column(JSONB, nullable=True)  # la del motor, congelada al generarla
    motor = Column(String(120), nullable=True)
    version_prompt = Column(String(16), nullable=True)
    generada_en = Column(DateTime(timezone=True), nullable=True)
    # El registro inalterable de esa propuesta (RF-AI-002).
    propuesta_id = Column(UUID(as_uuid=True), ForeignKey("propuestas_ia.id"), nullable=True)


class Anotacion(Base):
    __tablename__ = "evaluacion_anotaciones"
    __table_args__ = (UniqueConstraint("evaluacion_id", "instanciacion_id", "evaluador_id", "condicion"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("evaluaciones.id"), nullable=False, index=True)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False)
    evaluador_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)
    condicion = Column(Enum(*CONDICION, name="condicion_anotacion"), nullable=False)
    estado = Column(Enum(*ESTADO_ANOTACION, name="estado_anotacion"), nullable=False, default="en_curso")
    datos = Column(JSONB, nullable=True)  # {titulo, alcance, entidades: [{tipo, valor, rol, edtf}]}
    iniciada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    enviada_en = Column(DateTime(timezone=True), nullable=True)


class Exposicion(Base):
    """Cuándo vio alguien la propuesta del motor de un documento: desde ese
    momento ya no puede describirlo a ciegas."""
    __tablename__ = "evaluacion_exposiciones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("evaluaciones.id"), nullable=False, index=True)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)
    motivo = Column(String(20), nullable=False)  # asistida, calificacion, resultados
    momento = Column(DateTime(timezone=True), default=ahora, nullable=False)


class Calificacion(Base):
    __tablename__ = "evaluacion_calificaciones"
    __table_args__ = (UniqueConstraint("evaluacion_id", "instanciacion_id", "evaluador_id", "criterio"),
                      CheckConstraint("puntaje BETWEEN 1 AND 5", name="ck_calificacion_puntaje"))

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("evaluaciones.id"), nullable=False, index=True)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False)
    evaluador_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    criterio = Column(Enum(*CRITERIOS, name="criterio_rubrica"), nullable=False)
    puntaje = Column(Integer, nullable=False)
    creada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
