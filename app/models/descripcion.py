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

# Las seis clases reutilizables del vocabulario del fondo. Actividad, tipo
# de actividad y mandato se agregaron en la versión actualizada del módulo
# 2: la actividad es el ejercicio concreto y fechado de una competencia
# (RiC-E15 Activity), el tipo de actividad es el valor controlado de esa
# competencia (rico:ActivityType, no una entidad «Función», que no existe
# en RiC-O) y el mandato es la norma que la regula (RiC-E17 Mandate).
CLASE_VOCABULARIO = ("agente", "lugar", "forma_documental", "actividad", "tipo_actividad", "mandato")
# «grupo» (RiC-E09 Group usado directamente): un colectivo que no es ni
# entidad corporativa ni familia, como un comité o una junta. La nota de
# alcance de rico:Group admite «otras clases de grupos».
SUBTIPO_AGENTE = ("persona", "entidad_corporativa", "grupo", "cargo", "familia", "mecanismo")
# Estatuto jurídico de una entidad corporativa (ISAAR-CPF 5.2.4; rico:LegalStatus).
ESTATUTO_JURIDICO = ("publica", "privada", "mixta")
# Tipo de lugar, lista controlada (rico:PlaceType).
TIPO_LUGAR = ("pais", "departamento", "provincia", "municipio", "corregimiento", "vereda", "barrio", "edificio",
              "otro")
# Esquemas de identificador: interno de la institución o de una autoridad
# externa reconocida (rico:hasOrHadIdentifier + rico:IdentifierType).
ESQUEMA_IDENTIFICADOR = ("interno", "viaf", "wikidata", "isni", "lcnaf", "otro")
ESQUEMA_EXTERNO = ("viaf", "wikidata", "isni", "lcnaf")
NIVEL_DETALLE = ("minimo", "completo")
TIPO_NOMBRE_ENTIDAD = ("paralela", "normalizada", "otra", "historica")
TIPO_HITO = ("creacion", "reforma", "traslado", "supresion", "otro")
ESTADO_REGISTRO = ("vigente", "anulado")
# Tipo de instrumento jurídico de un mandato (rico:MandateType).
SUBTIPO_MANDATO = ("ley", "decreto", "ordenanza", "acuerdo", "resolucion", "otro")
# Los tres niveles de precisión de una fecha (RiC-CM 1.0: Single Date,
# Date Range, Date Set; en RiC-O 1.1 son tipos de rico:Date).
SUBTIPO_FECHA = ("simple", "rango", "conjunto")
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
    documental (tipo documental, RiC-A17). Lo administra el módulo de
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

    # --- Ficha de autoridad ISAAR (CPF), para agentes (módulo 3, versión 2) ---
    # Identificación: versión exacta, obligatoria para un mecanismo (RiC-A41
    # Technical characteristics). Las formas paralelas, normalizadas y otras
    # del nombre y los identificadores viven en sus propias tablas.
    version = Column(String(120), nullable=True)
    # Descripción: fechas de existencia en EDTF (inicio sin fin admitido),
    # historia (RiC-A21), estatuto jurídico, estructura interna y contexto.
    existencia_edtf = Column(String(200), nullable=True)
    existencia_inicio = Column(Date, nullable=True)
    existencia_fin = Column(Date, nullable=True)
    historia = Column(Text, nullable=True)
    estatuto_juridico = Column(String(20), nullable=True)
    estructura = Column(Text, nullable=True)
    contexto_general = Column(Text, nullable=True)
    # Control: reglas o convenciones (vacío = ISAAR-CPF 2.ª ed.), nivel de
    # detalle (se recalcula al guardar) y fuentes del enriquecimiento.
    reglas = Column(String(200), nullable=True)
    nivel_detalle = Column(Enum(*NIVEL_DETALLE, name="nivel_detalle"), nullable=False, default="minimo",
                           server_default="minimo", index=True)
    fuentes = Column(Text, nullable=True)
    # --- Lugar ampliado (RiC-A11 coordenadas; rico:PlaceType) ---
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)
    tipo_lugar = Column(String(30), nullable=True)
    # --- Tipo de actividad como concepto SKOS: skos:broader (función →
    # subfunción → trámite). No es una relación de RiC-O.
    concepto_superior_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_vocabulario_trigramas", "nombre_normalizado", postgresql_using="gin",
              postgresql_ops={"nombre_normalizado": "gin_trgm_ops"}),
    )


class Fecha(_Procedencia, Base):
    """RiC-CM Date (RiC-E18): la expresión tal como aparece en el documento
    (RiC-A19) y su forma normalizada en EDTF (RiC-A29), con su subtipo:
    simple, rango o conjunto. No se fuerza una fecha exacta: «c. 1948» o
    «década de 1940» se guardan como tales (1948~, 194X)."""

    __tablename__ = "fechas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expresion = Column(String(200), nullable=False)
    subtipo = Column(Enum(*SUBTIPO_FECHA, name="subtipo_fecha"), nullable=False, default="simple",
                     server_default="simple")
    edtf = Column(String(200), nullable=True)  # vacío solo en fechas anteriores a esta versión
    # Límites del intervalo que cubre (para ordenar y buscar), calculados del EDTF.
    inicio = Column(Date, nullable=True)
    fin = Column(Date, nullable=True)
    normalizada = Column(Date, nullable=True)  # solo si es un día exacto
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class Actividad(_Procedencia, Base):
    """Tabla de la primera versión. Desde la migración 0009 las actividades
    viven en el vocabulario (clase «actividad»), con verificación de
    duplicados; esta tabla se conserva sin uso (nada se borra)."""

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
    # Si la relación se redirigió al fusionar dos entidades del vocabulario,
    # aquí queda a qué entidad apuntaba originalmente (trazabilidad).
    destino_original_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    # Lo mismo para el origen (p. ej. el agente que ejerce una actividad).
    origen_original_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    confirmada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    # Vigencia de la relación (EDTF) y una nota breve sobre su naturaleza,
    # p. ej. en una relación entre agentes.
    fecha_edtf = Column(String(200), nullable=True)
    nota = Column(String(500), nullable=True)
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


ESTADO_SUGERENCIA = ("pendiente", "aprobada", "descartada", "obsoleta")


class SugerenciaFusion(Base):
    """Par de entidades del vocabulario que la detección periódica cree que
    son la misma. Nunca se fusiona sola: espera la decisión del archivista.
    Un par ya decidido (aprobado o descartado) no se vuelve a sugerir."""

    __tablename__ = "sugerencias_fusion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    clase = Column(Enum(*CLASE_VOCABULARIO, name="clase_vocabulario", create_type=False), nullable=False)
    # Par ordenado (entidad_a_id < entidad_b_id) para no repetirlo al revés.
    entidad_a_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=False)
    entidad_b_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=False)
    similitud = Column(Float, nullable=False)
    estado = Column(Enum(*ESTADO_SUGERENCIA, name="estado_sugerencia"), nullable=False, default="pendiente", index=True)
    creada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    resuelta_en = Column(DateTime(timezone=True), nullable=True)
    resuelta_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    definitiva_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)

    __table_args__ = (Index("ux_sugerencia_par", "entidad_a_id", "entidad_b_id", unique=True),)


class NombreEntidad(Base):
    """Otras formas del nombre de una entidad (ISAAR-CPF 5.1.3 a 5.1.5) y,
    para un lugar, sus nombres históricos (rico:PlaceName), con su periodo de
    vigencia. La forma autorizada es el nombre de la entidad."""

    __tablename__ = "nombres_entidad"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entidad_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=False, index=True)
    tipo = Column(Enum(*TIPO_NOMBRE_ENTIDAD, name="tipo_nombre_entidad"), nullable=False)
    nombre = Column(String(300), nullable=False)
    idioma = Column(String(12), nullable=True)  # ISO 639, para formas paralelas
    regla = Column(String(120), nullable=True)  # para formas normalizadas según otras reglas
    vigencia_edtf = Column(String(200), nullable=True)
    inicio = Column(Date, nullable=True)
    fin = Column(Date, nullable=True)
    estado = Column(Enum(*ESTADO_REGISTRO, name="estado_registro"), nullable=False, default="vigente",
                    server_default="vigente")
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class IdentificadorEntidad(Base):
    """Identificador con su esquema declarado: un código interno o una
    autoridad externa (VIAF, Wikidata, ISNI, LCNAF). Nunca un texto suelto
    sin saber a qué autoridad pertenece (ISAAR-CPF 5.1.6)."""

    __tablename__ = "identificadores_entidad"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entidad_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=False, index=True)
    esquema = Column(String(40), nullable=False)
    valor = Column(String(200), nullable=False)
    estado = Column(Enum(*ESTADO_REGISTRO, name="estado_registro", create_type=False), nullable=False,
                    default="vigente", server_default="vigente")
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class Hito(Base):
    """Hito de la línea de tiempo institucional de un agente: creación,
    reforma, traslado del archivo, supresión. Es un rico:Event usado
    directamente (no una Activity), unido al agente por RiC-R059 affects or
    affected (ver anexo de verificación)."""

    __tablename__ = "hitos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False)
    agente_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=False, index=True)
    tipo = Column(Enum(*TIPO_HITO, name="tipo_hito"), nullable=False)
    descripcion = Column(String(500), nullable=False)
    edtf = Column(String(200), nullable=False)
    inicio = Column(Date, nullable=True)
    fin = Column(Date, nullable=True)
    estado = Column(Enum(*ESTADO_REGISTRO, name="estado_registro", create_type=False), nullable=False,
                    default="vigente", server_default="vigente")
    # Si el agente se fusionó en otro, a qué agente pertenecía originalmente.
    agente_original_id = Column(UUID(as_uuid=True), nullable=True)
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
