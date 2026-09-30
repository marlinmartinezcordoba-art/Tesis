"""Todos los modelos, importados aquí para que Alembic los conozca."""

from app.db.base import Base  # noqa: F401
from app.models.auditoria import RegistroAuditoria  # noqa: F401
from app.models.sesion import Sesion  # noqa: F401
from app.models.token_acceso import TokenUnUso  # noqa: F401
from app.models.usuario import Usuario  # noqa: F401
