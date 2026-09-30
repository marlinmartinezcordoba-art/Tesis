"""
Base declarativa común. Todas las fechas se guardan con zona horaria (UTC)
y se muestran en la hora de Colombia en la interfaz.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import declarative_base

Base = declarative_base()


def ahora() -> datetime:
    return datetime.now(timezone.utc)
