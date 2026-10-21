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
CLASE_BANCO = ("serie", "subserie", "tipo_documental")
SOPORTE = ("fisico", "electronico", "hibrido")


class VersionTrd(Base):
    __tablename__ = "trd_versiones"
    __table_args__ = (UniqueConstraint("fondo_id", "numero", name="uq_trd_version_numero"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id", ondelete="CASCADE"), nullable=False,
                      index=True)
    numero = Column(Integer, nullable=False)
    nombre = Column(String(300), nullable=False)
    acto_aprobacion = Column(String(300), nullable=True)  # p. ej. «Resolución 123 de 2024»
    fecha_aprobacion = Column(Date, nullable=True)
    convalidacion = Column(String(300), nullable=True)  # certificado del AGN o del consejo territorial
    fecha_convalidacion = Column(Date, nullable=True)
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
    estado = Column(String(20), nullable=False, default="vigente")
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)
