"""
Parametrización de la tabla de retención documental (TRD) y del cuadro de
clasificación (CCD), en el orden en que la hacen los SGDEA colombianos
(Modelo de requisitos para un SGDEA del AGN):

1. Versión de la TRD: número, acto administrativo que la aprueba, fecha,
   convalidación y vigencia. Solo se edita en borrador; al aplicarse queda
   vigente y la anterior pasa a histórica (nunca se borra).
2. Dependencias productoras (secciones y subsecciones) con su código.
3. Banco terminológico de series, subseries y tipos documentales del fondo.
4. Matriz de la TRD: por dependencia, cada serie o subserie con sus tipos
   documentales, la retención en archivo de gestión (AG) y central (AC), la
   disposición final, el soporte y el procedimiento.

Estas tablas son la mesa de trabajo de la parametrización. Lo que vale en
RiC-O se crea al aplicar una versión: las secciones, series y subseries como
rico:RecordSet, el productor como rico:CorporateBody, los tipos como
rico:DocumentaryFormType y cada regla de retención como rico:Rule unida a su
serie con una relación fechada con la vigencia de la versión.

Nada se borra: una dependencia, un término del banco o una fila se anulan.
"""

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.db.base import Base, ahora

ESTADO_VERSION = ("borrador", "vigente", "historica", "anulada")
# TRD: rige desde su vigencia hacia adelante. TVD (Acuerdo 004 de 2019): valora el
# fondo acumulado por periodos institucionales; sus reglas rigen los documentos
# producidos en el periodo (desde, hasta).
INSTRUMENTO = {"trd": "Tabla de retención documental", "tvd": "Tabla de valoración documental"}
CLASE_BANCO = ("serie", "subserie", "tipo_documental")
SOPORTE = ("fisico", "electronico", "hibrido")


class VersionTrd(Base):
    __tablename__ = "trd_versiones"
    __table_args__ = (UniqueConstraint("fondo_id", "instrumento", "numero", name="uq_trd_version_numero"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id", ondelete="CASCADE"), nullable=False,
                      index=True)
    instrumento = Column(String(3), nullable=False, default="trd", server_default="trd")
    # Solo la TVD: el periodo institucional que valora (p. ej. «Periodo 2: MAVDT»).
    periodo = Column(String(300), nullable=True)
    periodo_desde = Column(Date, nullable=True)
    periodo_hasta = Column(Date, nullable=True)
    numero = Column(Integer, nullable=False)
    nombre = Column(String(300), nullable=False)
    acto_aprobacion = Column(String(300), nullable=True)  # p. ej. «Resolución 123 de 2024»
    fecha_aprobacion = Column(Date, nullable=True)
    convalidacion = Column(String(300), nullable=True)  # certificado del AGN o del consejo territorial
    fecha_convalidacion = Column(Date, nullable=True)
    # Quién vigila su aplicación (RiC-R066 is or was enforced by): el AGN o el consejo
    # territorial de archivos, como agente del vocabulario del fondo.
    ente_vigilancia_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)
    vigente_desde = Column(Date, nullable=True)
    vigente_hasta = Column(Date, nullable=True)
    estado = Column(String(20), nullable=False, default="borrador")
    observaciones = Column(Text, nullable=True)
    informe = Column(JSONB, nullable=True)  # lo que hizo la aplicación
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
    aplicado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    aplicado_en = Column(DateTime(timezone=True), nullable=True)


class DependenciaTrd(Base):
    """Sección (dependencia productora) o subsección (oficina) del fondo."""
    __tablename__ = "trd_dependencias"
    __table_args__ = (UniqueConstraint("fondo_id", "superior_id", "codigo", name="uq_trd_dependencia_codigo"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id", ondelete="CASCADE"), nullable=False,
                      index=True)
    superior_id = Column(UUID(as_uuid=True), ForeignKey("trd_dependencias.id"), nullable=True, index=True)
    codigo = Column(String(40), nullable=False)
    nombre = Column(String(300), nullable=False)
    estado = Column(String(20), nullable=False, default="activa")
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class TerminoBanco(Base):
    """Banco terminológico: serie, subserie (con su serie) o tipo documental."""
    __tablename__ = "trd_banco"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id", ondelete="CASCADE"), nullable=False,
                      index=True)
    clase = Column(String(20), nullable=False)
    superior_id = Column(UUID(as_uuid=True), ForeignKey("trd_banco.id"), nullable=True, index=True)
    codigo = Column(String(40), nullable=True)  # los tipos documentales no llevan código
    nombre = Column(String(300), nullable=False)
    definicion = Column(Text, nullable=True)
    estado = Column(String(20), nullable=False, default="activo")
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class FilaTrd(Base):
    """Una serie o subserie de una dependencia en una versión de la TRD."""
    __tablename__ = "trd_filas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("trd_versiones.id", ondelete="CASCADE"), nullable=False,
                        index=True)
    dependencia_id = Column(UUID(as_uuid=True), ForeignKey("trd_dependencias.id"), nullable=False, index=True)
    serie_id = Column(UUID(as_uuid=True), ForeignKey("trd_banco.id"), nullable=False)
    subserie_id = Column(UUID(as_uuid=True), ForeignKey("trd_banco.id"), nullable=True)
    tipos = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    gestion = Column(Integer, nullable=True)
    central = Column(Integer, nullable=True)
    disposicion = Column(String(2), nullable=True)  # ct | s | m | e
    otras_disposiciones = Column(ARRAY(String(2)), nullable=False, default=list)
    soporte = Column(String(20), nullable=True)
    procedimiento = Column(Text, nullable=True)
    funcion = Column(String(300), nullable=True)
    # De dónde salió la fila (requisito 3): {carga, archivo, parte, fila}. Vacío si se escribió a mano.
    procedencia = Column(JSONB, nullable=True)
    estado = Column(String(20), nullable=False, default="vigente")
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)


class CargaInstrumento(Base):
    """El archivo original de una carga de CCD/TRD/TVD (requisito 3), tal como llegó: se guarda
    con su huella SHA-256 y nunca se borra, para poder mostrar de dónde salió cada fila."""

    __tablename__ = "cargas_instrumento"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id", ondelete="CASCADE"), nullable=False,
                      index=True)
    version_id = Column(UUID(as_uuid=True), ForeignKey("trd_versiones.id", ondelete="CASCADE"), nullable=False, index=True)
    archivo = Column(String(300), nullable=False)  # nombre con que se subió
    huella = Column(String(64), nullable=False)  # SHA-256 del archivo
    tamano = Column(Integer, nullable=False)
    ruta = Column(String(500), nullable=False)  # en el almacenamiento, por su huella
    origen = Column(String(300), nullable=True)  # cómo se leyó (plantilla, formato del AGN, zip…)
    # Qué instrumento es: la TRD o la TVD que llenó la versión, o el CCD con que se cotejó (fase C).
    clase = Column(String(3), nullable=False, default="trd", server_default="trd")
    informe = Column(JSONB, nullable=True)  # en un CCD, el resultado del cotejo con la versión
    filas_cargadas = Column(Integer, nullable=False, default=0)
    cargado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    cargado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
