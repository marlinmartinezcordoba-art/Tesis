import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora

TIPO_TOKEN = ("invitacion", "recuperacion")


class TokenUnUso(Base):
    """Enlace de un solo uso para definir contraseña: invitación a una
    cuenta nueva o recuperación de una existente. Solo se guarda la huella
    SHA-256 del token; el token en claro solo existe en el enlace enviado.
    """

    __tablename__ = "tokens_un_uso"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)
    tipo = Column(Enum(*TIPO_TOKEN, name="tipo_token"), nullable=False)
    huella = Column(String(64), nullable=False, unique=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    vence_en = Column(DateTime(timezone=True), nullable=False)
    usado_en = Column(DateTime(timezone=True), nullable=True)
    # Si se reemplaza por uno nuevo antes de usarse, queda anulado.
    anulado_en = Column(DateTime(timezone=True), nullable=True)
    ip_solicitud = Column(String(64), nullable=True)
