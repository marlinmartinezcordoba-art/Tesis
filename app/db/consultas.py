"""Ayudas de consulta comunes a los servicios."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def contar(db: Session, consulta) -> int:
    """Cuántas filas devuelve una consulta (sin traerlas)."""
    return db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
