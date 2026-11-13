"""
Biblioteca de referencia del Asistente RICORA: leyes, acuerdos del AGN, manuales y procedimientos
de la entidad. El asistente responde con ellos (RAG): recupera los pasajes que tratan la pregunta y
responde solo con lo que dicen, citándolos. Nada se borra: un documento que ya no sirve se anula.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID

from app.db.base import Base, ahora

CLASES = ("ley", "decreto", "acuerdo_agn", "manual", "procedimiento", "otro")


class DocumentoReferencia(Base):
    __tablename__ = "documentos_referencia"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo = Column(String(300), nullable=False)
    clase = Column(String(30), nullable=False, default="otro")
    nombre_original = Column(String(255), nullable=False)
    ruta = Column(String(500), nullable=False)
    huella = Column(String(64), nullable=False)
    tamano_bytes = Column(Integer, nullable=False)
    formato_mime = Column(String(120), nullable=True)
    estado = Column(String(20), nullable=False, default="procesando")  # procesando | listo | error | anulado
    error = Column(Text, nullable=True)
    texto = Column(Text, nullable=True)
    origen_texto = Column(String(20), nullable=True)  # capa_de_texto | ocr
    paginas = Column(Integer, nullable=True)
    busqueda = Column(TSVECTOR, nullable=True)  # la llena un disparador (migración 0057)
    cargado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    cargado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    procesado_en = Column(DateTime(timezone=True), nullable=True)
    anulado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    anulado_en = Column(DateTime(timezone=True), nullable=True)
    motivo_anulacion = Column(Text, nullable=True)
