"""
Modelo del grafo descriptivo: las entidades RiC que crea el módulo de
descripción y las relaciones que las conectan.

Regla que atraviesa todo el archivo: el origen de un dato (motor o
persona), su confianza y su estado de revisión viven en columnas propias
(origen, confianza, estado_revision, motor), nunca dentro del texto
descriptivo. Esas columnas no salen jamás en la consulta pública ni en
un instrumento exportado (ver app/servicios/consulta.py).
"""

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora
from app.models.enums import CODIGO_RELACION_RIC, TIPO_RELACION

ORIGEN_DATO = ("motor", "motor_editado", "persona")
ESTADO_REVISION = ("validado",)  # solo se publica lo que una persona validó

CLASE_VOCABULARIO = ("agente", "lugar", "forma_documental")
SUBTIPO_AGENTE = ("persona", "entidad_corporativa", "cargo", "familia")
ESTADO_ENTIDAD = ("activa", "fusionada")

ESTADO_RELACION = ("vigente", "anulada")
ESTADO_TRABAJO = ("abierto", "publicado", "cancelado", "expirado")


class _Procedencia:
    """Columnas de procedencia del dato, comunes a entidades y relaciones."""

    origen = Column(Enum(*ORIGEN_DATO, name="origen_dato"), nullable=False, default="persona")
    confianza = Column(Float, nullable=True)  # 0 a 1, tal como la dio el motor
    motor = Column(String(120), nullable=True)  # qué motor propuso (RiC-E13 Mechanism)
    estado_revision = Column(Enum(*ESTADO_REVISION, name="estado_revision"), nullable=False, default="validado")


class EntidadVocabulario(_Procedencia, Base):
    """Registro único y reutilizable por fondo de Agent (RiC-E07: persona,
    entidad corporativa, cargo, familia), Place (RiC-E22) y forma
    documental (tipo documental, RiC-A13). Lo administra el módulo de
    vocabularios; aquí se crea cuando el archivista confirma una entidad."""

    __tablename__ = "entidades_vocabulario"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    clase = Column(Enum(*CLASE_VOCABULARIO, name="clase_vocabulario"), nullable=False, index=True)
    subtipo = Column(String(40), nullable=True)
    nombre = Column(String(300), nullable=False)
    # Minúsculas y sin tildes: base de la comparación por trigramas.
    nombre_normalizado = Column(String(300), nullable=False)
    estado = Column(Enum(*ESTADO_ENTIDAD, name="estado_entidad_vocabulario"), nullable=False, default="activa")
    fusionada_en_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)

    __table_args__ = (
        Index("ix_vocabulario_trigramas", "nombre_normalizado", postgresql_using="gin",
              postgresql_ops={"nombre_normalizado": "gin_trgm_ops"}),
    )


class Fecha(_Procedencia, Base):
    """RiC-CM Date (RiC-E18): la expresión tal como aparece en el documento
    y, si se pudo, su forma normalizada. No se fuerza una fecha exacta."""

    __tablename__ = "fechas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expresion = Column(String(200), nullable=False)
    normalizada = Column(Date, nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class Actividad(_Procedencia, Base):
    """RiC-CM Activity (RiC-E15): lo que el documento documenta
    (p. ej. «sesión ordinaria del concejo»)."""

    __tablename__ = "actividades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    nombre = Column(String(300), nullable=False)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


# Tablas que puede conectar una relación (clave foránea polimórfica,
# validada en el código).
TIPOS_NODO = ("recurso_documental", "instanciacion", "entidad_vocabulario", "fecha", "actividad")


class Relacion(_Procedencia, Base):
    """RiC-CM Relation: arista del grafo, con su categoría amplia y su código
    oficial RiC-R. Nunca se borra: al corregir una descripción, la relación
    que sobra queda «anulada» y la historia se conserva."""

    __tablename__ = "relaciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    origen_tipo = Column(String(40), nullable=False)
    origen_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    destino_tipo = Column(String(40), nullable=False)
    destino_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tipo_relacion = Column(Enum(*TIPO_RELACION, name="tipo_relacion"), nullable=False)
    codigo_ric = Column(Enum(*CODIGO_RELACION_RIC, name="codigo_relacion_ric"), nullable=False, index=True)
    rol = Column(String(40), nullable=True)  # rol del agente o del lugar en el documento
    # Fragmento textual exacto del que se derivó, y de qué documento.
    fragmento = Column(Text, nullable=True)
    fragmento_instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id", ondelete="SET NULL"), nullable=True)
    fragmento_inicio = Column(Integer, nullable=True)
    estado = Column(Enum(*ESTADO_RELACION, name="estado_relacion"), nullable=False, default="vigente", index=True)
    confirmada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    anulada_en = Column(DateTime(timezone=True), nullable=True)
    anulada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)


class TrabajoDescripcion(Base):
    """Marca «en edición»: quién está describiendo qué, desde cuándo.
    Guarda la propuesta del motor para no perderla si se recarga la página.
    Vence tras 30 minutos sin actividad (ver documentación, decisiones)."""

    __tablename__ = "trabajos_descripcion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False)
    nivel = Column(String(40), nullable=False)
    # Reapertura de una descripción ya publicada (si no, es una nueva).
    recurso_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=True)
    propuesta = Column(Text, nullable=True)  # JSON de la propuesta del motor
    estado = Column(Enum(*ESTADO_TRABAJO, name="estado_trabajo"), nullable=False, default="abierto", index=True)
    iniciado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    ultima_actividad = Column(DateTime(timezone=True), default=ahora, nullable=False)
    cerrado_en = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Una descripción publicada solo puede tener una reapertura abierta.
        Index("ux_trabajo_recurso_abierto", "recurso_id", unique=True,
              postgresql_where=text("estado = 'abierto' AND recurso_id IS NOT NULL")),
    )


class TrabajoInstanciacion(Base):
    """Documentos de un trabajo. El índice único parcial es el candado: la
    base de datos misma impide que dos trabajos abiertos tomen el mismo
    documento, aunque dos personas pulsen «Describir» en el mismo instante."""

    __tablename__ = "trabajo_instanciaciones"

    trabajo_id = Column(UUID(as_uuid=True), ForeignKey("trabajos_descripcion.id"), primary_key=True)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id", ondelete="CASCADE"), primary_key=True)
    abierto = Column(Boolean, nullable=False, default=True)
    orden = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ux_instanciacion_en_edicion", "instanciacion_id", unique=True, postgresql_where=text("abierto")),
    )
