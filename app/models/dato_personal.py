"""
Posibles datos personales (Ley 1581 de 2012) encontrados en el texto de un archivo.

Los encuentra el sistema con reglas y los decide una persona: confirmar,
corregir (otro tipo u otra categoría) o descartar con su motivo. Nada se
borra: un hallazgo descartado queda con quién, cuándo y por qué.

El dato mismo no se copia aquí: se guardan su posición en el texto del
archivo (que ya está protegido igual que el archivo), una muestra enmascarada
para listados y alertas, y una huella con clave para reconocerlo al volver a
revisar el texto.
"""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora

CATEGORIA_DATO = ("personal", "sensible", "menores")  # Ley 1581: art. 3 c), art. 5 y art. 7
ESTADO_DATO = ("pendiente", "confirmado", "corregido", "descartado")


class DatoPersonalDetectado(Base):
    __tablename__ = "datos_personales_detectados"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instanciacion_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=False, index=True)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    tipo = Column(String(40), nullable=False)  # cedula, correo, salud…
    categoria = Column(String(10), nullable=False)  # CATEGORIA_DATO, la que propone la regla
    confianza = Column(Float, nullable=False)  # 0 a 1, fija por regla
    regla = Column(String(40), nullable=False)
    version_reglas = Column(String(10), nullable=False)
    muestra = Column(String(120), nullable=False)  # enmascarada: nunca el dato completo
    huella_valor = Column(String(64), nullable=False)  # HMAC del valor normalizado
    # Dónde aparece: [{pagina, inicio, fin}], posiciones en texto_extraido.
    ocurrencias = Column(JSONB, nullable=False)
    estado = Column(String(12), nullable=False, default="pendiente", index=True)  # ESTADO_DATO
    tipo_final = Column(String(40), nullable=True)  # al corregir
    categoria_final = Column(String(10), nullable=True)
    motivo = Column(Text, nullable=True)  # obligatorio al descartar
    decidido_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)  # vacío: lo cerró el sistema
    decidido_en = Column(DateTime(timezone=True), nullable=True)
    detectado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)

    __table_args__ = (UniqueConstraint("instanciacion_id", "tipo", "huella_valor", name="uq_dato_personal_valor"),)
