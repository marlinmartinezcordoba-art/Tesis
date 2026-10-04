import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base, ahora


class Usuario(Base):
    """Cuenta de una persona del equipo. Solo un administrador la crea.

    contrasena_hash queda vacía hasta que la persona usa su enlace de
    invitación y define su propia contraseña: el administrador nunca la
    conoce ni la define. Una cuenta nunca se borra, se desactiva.
    """

    __tablename__ = "usuarios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(150), nullable=False)
    correo = Column(String(254), nullable=False, unique=True, index=True)  # siempre en minúsculas
    # Uno de los roles de la tabla roles (base o creado por la administradora).
    rol = Column(String(40), ForeignKey("roles.clave"), nullable=False, default="consulta")
    rol_info = relationship("Rol", lazy="joined", foreign_keys=[rol])
    activo = Column(Boolean, nullable=False, default=True)
    contrasena_hash = Column(String(255), nullable=True)
    contrasena_cambiada_en = Column(DateTime(timezone=True), nullable=True)
    # Segundo factor (TOTP). El secreto nunca se devuelve después de activarlo
    # ni se escribe en la auditoría; de los códigos de respaldo solo hay huellas.
    mfa_secreto = Column(String(64), nullable=True)
    mfa_activo = Column(Boolean, nullable=False, default=False, server_default="false")
    mfa_activado_en = Column(DateTime(timezone=True), nullable=True)
    mfa_ultimo_paso = Column(BigInteger, nullable=True)
    mfa_respaldo = Column(JSONB, nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), default=ahora, onupdate=ahora, nullable=False)

    @property
    def iniciales(self) -> str:
        partes = [p for p in self.nombre.split() if p]
        if not partes:
            return "?"
        if len(partes) == 1:
            return partes[0][:2].upper()
        return (partes[0][0] + partes[-1][0]).upper()

    @property
    def invitacion_pendiente(self) -> bool:
        return self.contrasena_hash is None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario {self.correo} ({self.rol})>"
