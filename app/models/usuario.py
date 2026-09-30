import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora
from app.models.enums import ROL_USUARIO


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
    rol = Column(Enum(*ROL_USUARIO, name="rol_usuario"), nullable=False, default="consulta")
    activo = Column(Boolean, nullable=False, default=True)
    contrasena_hash = Column(String(255), nullable=True)
    contrasena_cambiada_en = Column(DateTime(timezone=True), nullable=True)
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
