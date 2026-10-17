"""
Registro de sincronización del grafo RiC-O persistente.

Una fila por fondo y alcance («publico»: sin lo clasificado ni lo reservado;
«completo»: todo). `version_datos` sube cada vez que cambia algo que entra
en el grafo del fondo; el trabajador reconstruye el grafo y, si nadie lo
cambió mientras tanto, deja `version_sincronizada` igual a `version_datos`.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class GrafoRdf(Base):
    __tablename__ = "grafos_rdf"
    __table_args__ = (UniqueConstraint("fondo_id", "alcance", name="uq_grafos_rdf_fondo_alcance"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id", ondelete="CASCADE"), nullable=False, index=True)
    alcance = Column(String(10), nullable=False)  # publico | completo
    version_datos = Column(Integer, nullable=False, default=1, server_default="1")
    version_sincronizada = Column(Integer, nullable=False, default=0, server_default="0")
    cambiado_en = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sincronizado_en = Column(DateTime(timezone=True), nullable=True)
    tripletas = Column(Integer, nullable=True)
    huella = Column(String(64), nullable=True)  # SHA-256 de las N-Triples canónicas guardadas
    conforme = Column(Boolean, nullable=True)  # OWL y SHACL de RiC-O 1.1 sobre lo guardado
    problemas_owl = Column(Integer, nullable=True)
    resultados_shacl = Column(Integer, nullable=True)
    resumen = Column(JSONB, nullable=True)  # por clase y lo omitido, como la exportación
    error = Column(String(1000), nullable=True)

    @property
    def al_dia(self) -> bool:
        return self.version_sincronizada >= self.version_datos and self.error is None
