"""
Módulo 5 · Preservación digital: metadatos PREMIS anclados en la
Instantiation (RiC-E06), nunca en el Record Resource.

- VerificacionIntegridad: evento PREMIS «fixity check», uno por cada
  verificación (periódica o manual), con su resultado.
- Migracion: evento PREMIS «migration». Se aprueba siempre de forma
  explícita; si termina bien, deja una Instantiation nueva enlazada a la
  original por RiC-R015 migrated into. La original no se toca.
- SegundaCopia: réplica de cada instanciación en un segundo lugar de
  almacenamiento (evento PREMIS «replication»; OAIS Almacenamiento de
  Archivo). Una copia nunca se borra: si se rehace o cambia la ubicación,
  la anterior queda «reemplazada», con su archivo.
- Restauracion: evento PREMIS «recovery», la copia primaria repuesta desde
  la segunda copia (plan de preservación, contingencia).
- DeclaracionDerechos: entidad Derechos de PREMIS en su versión mínima,
  sobre una instanciación o un Record Resource (se hereda hacia abajo).
"""

import uuid

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora

RESULTADO_INTEGRIDAD = ("integra", "alterada", "ausente")
ORIGEN_VERIFICACION = ("periodica", "manual")
ESTADO_MIGRACION = ("en_curso", "completada", "fallida", "esperando_archivo")
MODO_MIGRACION = ("automatica", "manual")
# Resultado de la segunda copia en una verificación: «sin_copia» cuando aún
# no existe ninguna en la ubicación configurada.
RESULTADO_SEGUNDA_COPIA = ("integra", "alterada", "ausente", "sin_copia")
ESTADO_SEGUNDA_COPIA = ("sincronizada", "alterada", "ausente", "reemplazada")
# Por qué se creó: ingesta, migración, reposición de una copia dañada,
# cambio de la ubicación configurada, o creación tardía (fondos anteriores).
MOTIVO_SEGUNDA_COPIA = ("ingesta", "migracion", "reposicion", "cambio_de_ubicacion", "pendiente", "recorte")
# Derechos (PREMIS rightsBasis) y acceso según la Ley 1712 de 2014
# (información pública, clasificada art. 18, reservada art. 19).
BASE_DERECHOS = ("estatuto", "licencia", "derecho_de_autor", "politica_institucional", "otra")
ACCESO_DERECHOS = ("publico", "clasificado", "reservado")
REPRODUCCION_DERECHOS = ("permitida", "condicionada", "no_permitida")


class VerificacionIntegridad(Base):
    __tablename__ = "verificaciones_integridad"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False, index=True)
    fecha = Column(DateTime(timezone=True), default=ahora, nullable=False, index=True)
    resultado = Column(Enum(*RESULTADO_INTEGRIDAD, name="resultado_integridad"), nullable=False)
    algoritmo = Column(String(20), nullable=False, default="SHA-256")
    huella_registrada = Column(String(64), nullable=True)
    huella_calculada = Column(String(64), nullable=True)
    origen = Column(Enum(*ORIGEN_VERIFICACION, name="origen_verificacion"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    # La misma verificación, sobre la segunda copia.
    segunda_copia_id = Column(UUID(as_uuid=True), ForeignKey("segundas_copias.id"), nullable=True)
    segunda_copia_resultado = Column(Enum(*RESULTADO_SEGUNDA_COPIA, name="resultado_segunda_copia"), nullable=True)
    segunda_copia_huella = Column(String(64), nullable=True)
    mecanismo_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)  # RiC-E13


class Migracion(Base):
    __tablename__ = "migraciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_origen_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False, index=True)
    destino = Column(String(40), nullable=False)  # clave del formato destino (ver servicios/preservacion.py)
    destino_nombre = Column(String(120), nullable=False)
    modo = Column(Enum(*MODO_MIGRACION, name="modo_migracion"), nullable=False)
    estado = Column(Enum(*ESTADO_MIGRACION, name="estado_migracion"), nullable=False, index=True)
    herramienta = Column(String(200), nullable=True)  # solo filas anteriores a la migración 0013
    parametros = Column(String(200), nullable=True)  # qué hizo el programa (no quién)
    mensaje = Column(String(500), nullable=True)
    aprobada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    aprobada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    terminada_en = Column(DateTime(timezone=True), nullable=True)
    instanciacion_resultado_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=True)
    mecanismo_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)  # RiC-E13


class SegundaCopia(Base):
    __tablename__ = "segundas_copias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False, index=True)
    ubicacion = Column(String(500), nullable=False)  # raíz configurada en el momento de crearla
    ruta = Column(String(500), nullable=False)  # relativa a esa raíz
    algoritmo = Column(String(20), nullable=False, default="SHA-256")
    huella = Column(String(64), nullable=False)  # calculada sobre la copia ya escrita
    tamano_bytes = Column(BigInteger, nullable=False)
    motivo = Column(Enum(*MOTIVO_SEGUNDA_COPIA, name="motivo_segunda_copia"), nullable=False)
    estado = Column(Enum(*ESTADO_SEGUNDA_COPIA, name="estado_segunda_copia"), nullable=False, default="sincronizada",
                    index=True)
    creada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    creada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)  # vacío: el sistema
    ultima_verificacion_en = Column(DateTime(timezone=True), nullable=True)
    reemplazada_en = Column(DateTime(timezone=True), nullable=True)
    mecanismo_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)  # RiC-E13


class Restauracion(Base):
    __tablename__ = "restauraciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False, index=True)
    segunda_copia_id = Column(UUID(as_uuid=True), ForeignKey("segundas_copias.id"), nullable=False)
    fecha = Column(DateTime(timezone=True), default=ahora, nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    estado_previo = Column(String(20), nullable=False)  # alterada o ausente
    huella_previa = Column(String(64), nullable=True)  # la del archivo dañado, si existía
    # El archivo dañado no se borra: se aparta aquí (relativa al almacenamiento).
    ruta_cuarentena = Column(String(500), nullable=True)
    mecanismo_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)  # RiC-E13


class DeclaracionDerechos(Base):
    __tablename__ = "declaraciones_derechos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    entidad_tipo = Column(Enum("instanciacion", "recurso_documental", name="entidad_derechos"), nullable=False)
    entidad_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    base = Column(Enum(*BASE_DERECHOS, name="base_derechos"), nullable=False)
    acceso = Column(Enum(*ACCESO_DERECHOS, name="acceso_derechos"), nullable=False)
    reproduccion = Column(Enum(*REPRODUCCION_DERECHOS, name="reproduccion_derechos"), nullable=False)
    fundamento = Column(String(500), nullable=False)  # p. ej. «Ley 1712 de 2014, art. 19»
    nota = Column(String(500), nullable=True)
    vigente_hasta = Column(Date, nullable=True)
    vigente = Column(Boolean, nullable=False, default=True, index=True)
    creada_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    creada_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    reemplazada_en = Column(DateTime(timezone=True), nullable=True)


ESTADO_RESPALDO = ("en_curso", "correcto", "fallido")
ESTADO_SIMULACRO = ("correcto", "fallido")


class RespaldoBaseDatos(Base):
    """Respaldo de la base de datos (OAIS Gestión de Datos; NDSA
    Almacenamiento y Metadatos) y su simulacro de restauración: el volcado
    se restaura en una base efímera y se comparan los conteos y la huella de
    las tablas clave con los que tenía la base en el instante del volcado.
    Un respaldo sin restauración probada no cuenta como respaldo."""

    __tablename__ = "respaldos_bd"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    iniciado_en = Column(DateTime(timezone=True), default=ahora, nullable=False, index=True)
    terminado_en = Column(DateTime(timezone=True), nullable=True)
    origen = Column(String(20), nullable=False, default="periodico")  # periodico | manual
    estado = Column(Enum(*ESTADO_RESPALDO, name="estado_respaldo"), nullable=False, default="en_curso")
    archivo = Column(String(300), nullable=True)  # ruta del volcado (formato personalizado de pg_dump)
    tamano_bytes = Column(BigInteger, nullable=True)
    huella = Column(String(64), nullable=True)  # SHA-256 del volcado
    conteos = Column(JSONB, nullable=True)  # tabla → filas, y la huella de las huellas de fijeza
    error = Column(String(1000), nullable=True)
    simulacro_en = Column(DateTime(timezone=True), nullable=True)
    simulacro_estado = Column(Enum(*ESTADO_SIMULACRO, name="estado_simulacro"), nullable=True)
    simulacro_detalle = Column(JSONB, nullable=True)  # lo restaurado frente a lo esperado
    descargado_en = Column(DateTime(timezone=True), nullable=True)  # última copia llevada fuera del servidor
    descargado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    depurado_en = Column(DateTime(timezone=True), nullable=True)  # el archivo salió por la retención; la fila queda


TIPO_COMPROBACION = ("antivirus", "validacion")
RESULTADO_COMPROBACION = ("limpio", "infectado", "conforme", "no_conforme", "error", "no_disponible")


class ComprobacionTecnica(Base):
    """Antivirus (ClamAV) y validación de formato (veraPDF para PDF/A,
    JHOVE para TIFF): eventos PREMIS «virus check» y «validation», con el
    mecanismo y su versión (hallazgos PRE-09 y PRE-13). «no_disponible»
    dice la verdad cuando la herramienta no está instalada: nunca se da por
    hecha una comprobación que no ocurrió."""

    __tablename__ = "comprobaciones_tecnicas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False, index=True)
    tipo = Column(Enum(*TIPO_COMPROBACION, name="tipo_comprobacion"), nullable=False)
    herramienta = Column(String(60), nullable=False)
    mecanismo_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)
    resultado = Column(Enum(*RESULTADO_COMPROBACION, name="resultado_comprobacion"), nullable=False)
    perfil = Column(String(60), nullable=True)  # «PDF/A-2B», «TIFF-hul»
    resumen = Column(Text, nullable=True)
    detalle = Column(JSONB, nullable=True)
    origen = Column(String(20), nullable=False)  # ingesta, migracion, manual
    realizada_en = Column(DateTime(timezone=True), nullable=False, default=ahora)
