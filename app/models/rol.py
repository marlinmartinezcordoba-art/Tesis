from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora

# Módulos a los que se da acceso por rol, y los niveles posibles.
MODULOS_CONFIGURABLES = ("ingesta", "descripcion", "vocabularios", "instrumentos", "preservacion", "catalogo", "auditoria")
NIVELES = ("ninguno", "leer", "escribir")
# Niveles válidos por módulo: el catálogo solo se consulta, y la auditoría
# se ve solo la propia («propia») o la de todo el equipo («todo»).
NIVELES_POR_MODULO = {
    **{m: NIVELES for m in ("ingesta", "descripcion", "vocabularios", "instrumentos", "preservacion")},
    "catalogo": ("ninguno", "leer"),
    "auditoria": ("ninguno", "propia", "todo"),
}


class Rol(Base):
    """Rol de usuario. Los cuatro roles base del diseño (administrador,
    archivista, revisor, consulta) vienen creados y no se modifican; la
    administradora puede crear otros con el acceso que decida por módulo.
    Un rol no se borra: se desactiva, y solo si nadie activo lo tiene."""

    __tablename__ = "roles"

    clave = Column(String(40), primary_key=True)
    nombre = Column(String(80), nullable=False, unique=True)
    descripcion = Column(String(300), nullable=True)
    base = Column(Boolean, nullable=False, default=False)
    activo = Column(Boolean, nullable=False, default=True)
    # {"ingesta": "escribir", "descripcion": "leer", ...}; lo que falte es «ninguno».
    permisos = Column(JSONB, nullable=False, default=dict)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id", use_alter=True, name="fk_rol_creado_por"), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), nullable=True)
