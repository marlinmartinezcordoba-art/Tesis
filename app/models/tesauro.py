"""
Tesauros para normalizar las materias (temas) de la descripción.

Un tesauro (el de la UNESCO, el ambiental de Minambiente u otro sectorial)
se importa una vez y lo comparten todos los fondos. Cada concepto tiene su
término preferente, sus términos no preferentes («usado por»), su nota de
alcance, su término superior y la URI de la fuente. La materia de una
descripción (clase «materia» del vocabulario del fondo) apunta a un
concepto: así dos documentos con el mismo tema quedan unidos al mismo nodo
del grafo, aunque cada uno lo haya escrito distinto.

Nada se borra: un tesauro o un concepto se anulan.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora

ESTADO_TESAURO = ("vigente", "anulado")
TIPO_ETIQUETA = ("preferente", "no_preferente", "oculta")


class Tesauro(Base):
    __tablename__ = "tesauros"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(200), nullable=False)
    fuente = Column(String(500), nullable=True)  # sitio o publicación de origen
    licencia = Column(String(200), nullable=True)
    idioma = Column(String(8), nullable=False, default="es")
    uri_esquema = Column(String(500), nullable=True)  # skos:ConceptScheme, si el archivo lo trae
    formato = Column(String(20), nullable=False)  # skos | excel | csv
    archivo = Column(String(300), nullable=True)
    huella = Column(String(64), nullable=True)  # SHA-256 del archivo importado
    conceptos = Column(Integer, nullable=False, default=0)
    estado = Column(String(20), nullable=False, default="vigente")
    importado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    importado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class ConceptoTesauro(Base):
    __tablename__ = "conceptos_tesauro"
    __table_args__ = (UniqueConstraint("tesauro_id", "clave", name="uq_concepto_tesauro_clave"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tesauro_id = Column(UUID(as_uuid=True), ForeignKey("tesauros.id"), nullable=False, index=True)
    clave = Column(String(500), nullable=False)  # la URI del concepto o, en una tabla, su término preferente
    uri = Column(String(500), nullable=True)
    preferente = Column(String(300), nullable=False)
    notacion = Column(String(60), nullable=True)
    nota_alcance = Column(Text, nullable=True)
    superior_id = Column(UUID(as_uuid=True), ForeignKey("conceptos_tesauro.id"), nullable=True, index=True)
    estado = Column(String(20), nullable=False, default="vigente")


class EtiquetaConcepto(Base):
    """Cada forma con que se puede buscar un concepto: la preferente y las no
    preferentes, normalizadas (sin tildes ni mayúsculas) para compararlas."""
    __tablename__ = "etiquetas_concepto"

    id = Column(Integer, primary_key=True, autoincrement=True)
    concepto_id = Column(UUID(as_uuid=True), ForeignKey("conceptos_tesauro.id"), nullable=False, index=True)
    etiqueta = Column(String(300), nullable=False)
    normalizada = Column(String(300), nullable=False, index=True)
    tipo = Column(String(20), nullable=False)
