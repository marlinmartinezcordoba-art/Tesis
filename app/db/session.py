from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependencia de FastAPI: una sesión de base de datos por petición."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Guardián de la tabla de relaciones (hallazgo CM-19): se registra con la
# sesión, así toda escritura de cualquier proceso pasa por él.
import app.servicios.integridad_ric  # noqa: E402,F401
