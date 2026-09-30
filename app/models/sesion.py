import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora

MOTIVO_CIERRE = (
    "cierre_voluntario",  # la persona cerró sesión
    "expiracion",  # pasó el tiempo de inactividad o el máximo de la sesión
    "revocada_administrador",  # un administrador cerró sus sesiones
    "cambio_contrasena",  # cambió o restableció la contraseña
    "cuenta_desactivada",  # un administrador desactivó la cuenta
    "reutilizacion_token",  # alguien presentó un token de renovación ya usado
)


class Sesion(Base):
    """Una sesión abierta con usuario y contraseña.

    El token de acceso (JWT, 15 minutos) lleva el identificador de esta
    fila; cada petición comprueba que la sesión siga abierta, y así un
    administrador puede revocarla antes de que el token expire solo. La
    renovación usa un secreto aparte, del que solo se guarda la huella.
    """

    __tablename__ = "sesiones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)
    huella_renovacion = Column(String(64), nullable=False)
    iniciada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    ultima_actividad = Column(DateTime(timezone=True), default=ahora, nullable=False)
    vence_en = Column(DateTime(timezone=True), nullable=False)  # máximo absoluto
    cerrada_en = Column(DateTime(timezone=True), nullable=True, index=True)
    motivo_cierre = Column(Enum(*MOTIVO_CIERRE, name="motivo_cierre_sesion"), nullable=True)
    ip = Column(String(64), nullable=True)
    navegador = Column(String(300), nullable=True)

    @property
    def abierta(self) -> bool:
        return self.cerrada_en is None
