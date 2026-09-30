from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora


class Parametro(Base):
    """Parámetros que ajusta el administrador sin tocar código (p. ej. el
    límite de tamaño de la ingesta). Cada cambio queda en auditoría con el
    valor anterior y el nuevo."""

    __tablename__ = "parametros"

    clave = Column(String(80), primary_key=True)
    valor = Column(JSONB, nullable=False)
    actualizado_en = Column(DateTime(timezone=True), default=ahora, onupdate=ahora, nullable=False)
    actualizado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
