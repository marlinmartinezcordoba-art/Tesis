import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora

SEVERIDAD = ("alta", "media", "baja")

# Tipos de alerta del sistema. Cada módulo agrega los suyos.
TIPO_ALERTA = (
    "formato_no_identificado",  # ingesta
    "ocr_baja_confianza",  # ingesta: la transcripción automática es dudosa
    "inventario_campos_pendientes",  # instrumentos
    "integridad_alterada",  # preservación
    "riesgo_obsolescencia",  # preservación
    "segunda_copia_alterada",  # preservación: la segunda copia cambió, falta o no se pudo crear
    "respaldo_fallido",  # preservación: el respaldo de la base o su simulacro de restauración falló
    "respaldo_atrasado",  # preservación: no hay un respaldo probado reciente
    "respaldo_sin_copia_externa",  # preservación: nadie se llevó el respaldo fuera del servidor
    "verificacion_atrasada",
    "huella_referencia_alterada",  # preservación: la huella de la base no coincide con el manifiesto independiente  # preservación: hay instanciaciones sin verificar dentro del plazo
)


class Alerta(Base):
    """Panel central de alertas y estado (diseño consolidado, Parte 1): un
    solo lugar para todo lo que requiere revisión humana, venga del módulo
    que venga. Una alerta no se borra: se marca como atendida.
    """

    __tablename__ = "alertas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(String(60), nullable=False, index=True)
    severidad = Column(Enum(*SEVERIDAD, name="severidad_alerta"), nullable=False)
    modulo = Column(String(40), nullable=False)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=True, index=True)
    entidad_tipo = Column(String(60), nullable=False)
    entidad_id = Column(String(64), nullable=False)
    mensaje = Column(String(500), nullable=False)
    detalle = Column(JSONB, nullable=True)
    creada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    atendida_en = Column(DateTime(timezone=True), nullable=True)
    atendida_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    nota_atencion = Column(String(500), nullable=True)

    __table_args__ = (
        # Nunca dos alertas pendientes del mismo tipo sobre la misma entidad.
        Index("ux_alerta_pendiente", "tipo", "entidad_id", unique=True, postgresql_where=text("atendida_en IS NULL")),
    )
