"""
Instrumento de descripción aprobado (Ley 594 de 2000, art. 26; Acuerdo 042 de
2002): el inventario FUID, la guía y el índice que el sistema arma al vuelo
quedan, cuando se aprueban, como un documento fijo con su fecha, quien lo
aprobó, el acta y la huella SHA-256 del archivo. Lo aprobado no cambia aunque
la descripción siga creciendo: se aprueba una versión nueva, que reemplaza a
la anterior (la anterior se conserva).

En RiC-O cada uno es un rico:Record del fondo que describe el nivel
(rico:describesOrDescribed, RiC-R021), como el cuadro de clasificación y la
TRD. Nada se borra: un instrumento aprobado por error se anula con su motivo.
"""

import uuid

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora

TIPO_INSTRUMENTO = {"inventario": "Inventario documental (FUID)", "guia": "Guía del fondo",
                    "indice": "Índice de consulta"}
ESTADO_INSTRUMENTO = ("vigente", "reemplazado", "anulado")


class InstrumentoAprobado(Base):
    __tablename__ = "instrumentos_aprobados"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    # El nivel que describe: el fondo (guía, índice) o el nivel del inventario.
    recurso_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    tipo = Column(String(20), nullable=False)  # TIPO_INSTRUMENTO
    version = Column(Integer, nullable=False)  # por tipo y nivel: 1, 2, 3…
    titulo = Column(String(500), nullable=False)
    ruta = Column(String(500), nullable=False)  # relativa a DIRECTORIO_ALMACENAMIENTO
    formato_mime = Column(String(200), nullable=False)
    tamano_bytes = Column(BigInteger, nullable=False)
    huella = Column(String(64), nullable=False)  # SHA-256 del archivo aprobado
    acta = Column(String(200), nullable=True)  # acta del comité u otro soporte de la aprobación
    fecha_acta = Column(Date, nullable=True)
    aprobado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    aprobado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    estado = Column(String(20), nullable=False, default="vigente", server_default="vigente")
    reemplaza_id = Column(UUID(as_uuid=True), ForeignKey("instrumentos_aprobados.id"), nullable=True)
    motivo_anulacion = Column(Text, nullable=True)
    anulado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    anulado_en = Column(DateTime(timezone=True), nullable=True)
