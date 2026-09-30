import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora

# Niveles de la jerarquía multinivel (ISAD(G) 3.1.4, que RiC-CM representa
# como Record Set con su tipo y la relación de inclusión RiC-R024).
NIVEL_DESCRIPCION = ("fondo", "seccion", "serie", "subserie", "expediente", "unidad_documental")


class RecursoDocumental(Base):
    """RiC-CM: Record Resource (RiC-E02) — Record Set en los niveles de
    agrupación y Record en la unidad documental.

    En esta etapa solo existen los fondos, que registra el administrador
    como punto de partida del trabajo. El módulo de descripción crea los
    demás niveles y amplía esta tabla con sus atributos y relaciones.
    """

    __tablename__ = "recursos_documentales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nivel = Column(Enum(*NIVEL_DESCRIPCION, name="nivel_descripcion"), nullable=False, index=True)
    titulo = Column(String(300), nullable=False)
    fechas_extremas = Column(String(60), nullable=True)  # p. ej. "1930–1955", tal como se describe
    nota = Column(Text, nullable=True)
    # Inclusión (RiC-R024 includes / is included in): nivel superior inmediato.
    incluido_en_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=True, index=True)
    # Fondo al que pertenece (él mismo si es un fondo): acota búsquedas y duplicados.
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=True, index=True)
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
