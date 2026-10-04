from sqlalchemy import BigInteger, Column, DateTime, FetchedValue, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora


class RegistroAuditoria(Base):
    """Registro único de auditoría de todo el sistema, de solo anexar.

    Todos los módulos escriben aquí a través de app.servicios.auditoria
    .registrar(); ninguno lleva un registro propio. La base de datos
    rechaza cualquier UPDATE o DELETE sobre esta tabla (disparador creado
    en la migración 0001), así que ni un administrador ni un error de
    programación pueden alterar un evento ya registrado.
    """

    __tablename__ = "registro_auditoria"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    fecha = Column(DateTime(timezone=True), default=ahora, nullable=False, index=True)
    # Nulo cuando la acción la ejecuta el propio sistema (p. ej. el
    # despliegue que restablece la cuenta administradora).
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True, index=True)
    modulo = Column(String(40), nullable=False, index=True)
    accion = Column(String(60), nullable=False, index=True)
    entidad_tipo = Column(String(60), nullable=True)
    entidad_id = Column(String(64), nullable=True, index=True)
    valor_anterior = Column(JSONB, nullable=True)
    valor_nuevo = Column(JSONB, nullable=True)
    detalle = Column(Text, nullable=True)
    ip = Column(String(64), nullable=True)
    # Cadena de huellas (brecha RF-AUD-002): la llena la base de datos al
    # insertar (disparador de la migración 0032), nunca la aplicación.
    orden = Column(BigInteger, nullable=True, unique=True, index=True, server_default=FetchedValue())
    huella_anterior = Column(String(64), nullable=True, server_default=FetchedValue())
    huella = Column(String(64), nullable=True, server_default=FetchedValue())
