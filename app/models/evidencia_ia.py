"""
Evidencia de la IA (brechas RF-AI-002 y RF-OCR-001).

PropuestaIA: la propuesta del motor como registro propio. Se crea al
proponer y su contenido no cambia nunca (lo impide un disparador de la base,
migración 0036); solo cambia su estado. Así una decisión de la archivista
siempre se puede comparar con lo que de verdad propuso el motor, con qué
modelo, qué instrucción y sobre qué texto.

PaginaTexto: el texto extraído de un archivo partido por páginas, con las
líneas del OCR y su caja en fracciones de la página (0 a 1, origen arriba a
la izquierda), para ubicar cada fragmento citado y resaltarlo en el visor.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.db.base import Base

ESTADO_PROPUESTA = ("generada", "publicada", "cancelada", "expirada", "evaluada")


class PropuestaIA(Base):
    __tablename__ = "propuestas_ia"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    origen = Column(String(20), nullable=False)  # descripcion | evaluacion
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    trabajo_id = Column(UUID(as_uuid=True), ForeignKey("trabajos_descripcion.id"), nullable=True, index=True)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("evaluaciones.id"), nullable=True, index=True)
    solicitada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    nivel = Column(String(40), nullable=False)
    instanciaciones = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    motor = Column(String(120), nullable=True)  # el modelo pedido (p. ej. gemini-…-flash)
    version_modelo = Column(String(120), nullable=True)  # la versión que respondió, según el proveedor
    version_prompt = Column(String(20), nullable=True)
    parametros = Column(JSONB, nullable=False)  # temperatura, límites de texto, uso de tokens…
    entrada = Column(JSONB, nullable=False)  # documentos enviados (con la huella de su texto) y contexto
    respuesta = Column(JSONB, nullable=True)  # lo que devolvió el motor, sin tocar
    contenido = Column(JSONB, nullable=False)  # la propuesta ya controlada (fragmentos localizados…)
    huella = Column(String(64), nullable=False)  # SHA-256 de entrada + respuesta + contenido
    disponible = Column(Boolean, nullable=False)
    aviso = Column(Text, nullable=True)
    entidades = Column(Integer, nullable=False, default=0)
    confianza_media = Column(Float, nullable=True)
    generada_en = Column(DateTime(timezone=True), nullable=False, index=True)
    duracion_ms = Column(Integer, nullable=True)
    estado = Column(String(20), nullable=False, default="generada", index=True)
    estado_en = Column(DateTime(timezone=True), nullable=True)
    recurso_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=True, index=True)


class PaginaTexto(Base):
    __tablename__ = "paginas_texto"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id", ondelete="CASCADE"), nullable=False)
    numero = Column(Integer, nullable=False)
    inicio = Column(Integer, nullable=False)  # posición en texto_extraido
    fin = Column(Integer, nullable=False)
    origen = Column(String(20), nullable=False)  # ocr | capa_de_texto
    ancho_px = Column(Integer, nullable=True)
    alto_px = Column(Integer, nullable=True)
    confianza = Column(Float, nullable=True)
    # Líneas del OCR: [inicio, fin, x, y, ancho, alto, bloque], posiciones en
    # texto_extraido y caja en fracciones de la página.
    lineas = Column(JSONB, nullable=True)

    __table_args__ = (UniqueConstraint("instanciacion_id", "numero", name="uq_paginas_texto_numero"),)
