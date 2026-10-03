import uuid

from sqlalchemy import BigInteger, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora

# Forma de ingreso (ISAD-G 3.2.4; Ley 594 de 2000, art. 23-24 y Acuerdo 042
# de 2002 del AGN para las transferencias).
FORMA_INGRESO = ("transferencia_primaria", "transferencia_secundaria", "donacion", "compra", "comodato", "deposito",
                 "otro")
NOMBRE_FORMA_INGRESO = {"transferencia_primaria": "Transferencia primaria", "transferencia_secundaria":
                        "Transferencia secundaria", "donacion": "Donación", "compra": "Compra", "comodato": "Comodato",
                        "deposito": "Depósito", "otro": "Otra forma de ingreso"}
ESTADO_LOTE = ("abierto", "confirmado", "anulado")


class LoteIngesta(Base):
    """Lote de transferencia (hallazgos ING-01 e ING-02): la unidad en que
    llega un conjunto de documentos, con su procedencia (quién lo remite, de
    qué dependencia, con qué acta). Al confirmarlo se arma el paquete de
    envío (SIP) en BagIt y queda el acuse de recibo. Un lote no se borra:
    se anula con motivo."""

    __tablename__ = "lotes_ingesta"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    numero = Column(String(40), nullable=False)  # «L-2026-0001», único por fondo
    forma_ingreso = Column(Enum(*FORMA_INGRESO, name="forma_ingreso"), nullable=False)
    # Procedencia, del vocabulario de agentes: quien entrega (persona o cargo)
    # y la dependencia productora de la que salen los documentos.
    remitente_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)
    dependencia_origen_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)
    acta_numero = Column(String(60), nullable=True)
    acta_fecha_edtf = Column(String(200), nullable=True)
    acta_instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=True)
    observaciones = Column(Text, nullable=True)
    estado = Column(Enum(*ESTADO_LOTE, name="estado_lote"), nullable=False, default="abierto")
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=ahora)
    confirmado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    confirmado_en = Column(DateTime(timezone=True), nullable=True)
    motivo_anulacion = Column(Text, nullable=True)
    # Paquete de envío (SIP) en BagIt, armado al confirmar.
    sip_ruta = Column(String(500), nullable=True)  # relativa a DIRECTORIO_ALMACENAMIENTO
    sip_huella = Column(String(64), nullable=True)  # SHA-256 del tagmanifest: identifica el paquete
    sip_archivos = Column(Integer, nullable=True)
    sip_bytes = Column(BigInteger, nullable=True)
