import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, ahora

# Estado de ingesta: un único campo decide qué pantalla muestra el
# documento. Ingesta muestra los tres primeros; descripción, el cuarto.
ESTADO_INGESTA = ("procesando", "duplicado_pendiente", "error", "listo_para_descripcion")
ESTADOS_COLA = ("procesando", "duplicado_pendiente", "error")

# Paso interno del procesamiento, solo para mostrar el avance.
PASO_PROCESO = ("en_espera", "huella", "duplicados", "formato", "texto", "terminado")

# De dónde salió el texto guardado para el motor de descripción.
ORIGEN_TEXTO = ("capa_de_texto", "ocr", "sin_texto")


class Instanciacion(Base):
    """RiC-CM: Instantiation (RiC-E06) — el archivo técnico que porta un
    documento. Se crea en la ingesta con sus metadatos técnicos (PREMIS:
    formato, tamaño, huella digital y algoritmo, fecha) y espera sola, sin
    Record Resource, hasta que el módulo de descripción la vincule.
    """

    __tablename__ = "instanciaciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=False, index=True)
    # Expediente elegido al cargar (opcional); descripción lo puede cambiar.
    expediente_destino_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=True)

    nombre_original = Column(String(500), nullable=False)
    ruta = Column(String(500), nullable=False)  # relativa a DIRECTORIO_ALMACENAMIENTO
    tamano_bytes = Column(BigInteger, nullable=False)
    tipo_declarado = Column(String(200), nullable=True)  # lo que dijo el navegador; no se usa para decidir nada

    estado = Column(Enum(*ESTADO_INGESTA, name="estado_ingesta"), nullable=False, default="procesando", index=True)
    paso = Column(Enum(*PASO_PROCESO, name="paso_proceso"), nullable=False, default="en_espera")
    progreso = Column(Integer, nullable=False, default=0)  # 0 a 100
    detalle_paso = Column(String(200), nullable=True)  # p. ej. "Página 3 de 12"
    tomado_en = Column(DateTime(timezone=True), nullable=True)  # cuándo lo tomó el trabajador
    intentos = Column(Integer, nullable=False, default=0)
    mensaje_error = Column(String(500), nullable=True)  # legible para el archivista, nunca una traza técnica

    # Integridad (PREMIS fixity)
    huella = Column(String(64), nullable=True)
    algoritmo_huella = Column(String(20), nullable=False, default="SHA-256")

    # Duplicado exacto
    duplicado_de_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id", ondelete="SET NULL"), nullable=True)
    duplicado_confirmado = Column(Boolean, nullable=False, default=False)

    # Formato (PREMIS format, contra el registro PRONOM)
    formato_puid = Column(String(40), nullable=True)
    formato_nombre = Column(String(300), nullable=True)
    formato_version = Column(String(100), nullable=True)
    formato_mime = Column(String(200), nullable=True)
    formato_base = Column(String(500), nullable=True)  # en qué se basó la identificación
    formato_no_identificado = Column(Boolean, nullable=False, default=False, index=True)
    herramienta_identificacion = Column(String(200), nullable=True)  # etiqueta tal como se vio entonces
    # El mecanismo (RiC-E13) del vocabulario que identificó el formato.
    mecanismo_identificacion_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)

    # Texto para el motor de descripción
    texto_extraido = Column(Text, nullable=True)
    origen_texto = Column(Enum(*ORIGEN_TEXTO, name="origen_texto"), nullable=True)
    paginas = Column(Integer, nullable=True)
    # Confianza del OCR (0 a 100), promedio por palabra de Tesseract. Vacía
    # cuando no hubo OCR (el documento traía capa de texto): cero sería una
    # extracción fallida, vacío es «no aplica».
    confianza_ocr = Column(Float, nullable=True)
    palabras_ocr = Column(Integer, nullable=True)
    # Bajo el umbral configurable: señal para leer con cuidado, nunca un bloqueo.
    ocr_baja_confianza = Column(Boolean, nullable=False, default=False, server_default="false", index=True)

    # Preservación (módulo 5): estado de la última verificación de
    # integridad y, si esta instanciación salió de una migración, de cuál.
    estado_integridad = Column(Enum("sin_verificar", "integra", "alterada", "ausente", name="estado_integridad"),
                               nullable=False, default="sin_verificar", server_default="sin_verificar")
    ultima_verificacion_en = Column(DateTime(timezone=True), nullable=True)
    derivada_de_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=True, index=True)
    # Recorte de otra instanciación (la firma o el sello de una parte
    # documental): de cuál, y qué zona {pagina, x, y, ancho, alto} en
    # proporciones de 0 a 1. No es una migración: no hereda la descripción.
    recorte_de_id = Column(UUID(as_uuid=True), ForeignKey("instanciaciones.id"), nullable=True, index=True)
    recorte_zona = Column(JSONB, nullable=True)

    cargado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    cargado_en = Column(DateTime(timezone=True), default=ahora, nullable=False, index=True)
    procesado_en = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_instanciaciones_fondo_huella", "fondo_id", "huella"),)
