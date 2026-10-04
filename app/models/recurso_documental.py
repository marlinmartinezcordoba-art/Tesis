import uuid

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, ahora

# Niveles de la jerarquía multinivel (ISAD(G) 3.1.4, que RiC-CM representa
# como Record Set con su tipo y la relación de inclusión RiC-R024).
# La parte documental (RiC-E05 Record Part: un anexo, un folio, una firma,
# un sello) es el último nivel, por debajo de la unidad documental.
# La subsección (cuadro de clasificación documental colombiano, Acuerdo AGN
# 004 de 2019) va entre la sección y la serie (hallazgo DES-08).
NIVEL_DESCRIPCION = ("fondo", "seccion", "subseccion", "serie", "subserie", "expediente", "unidad_documental",
                     "parte_documental")


# Categoría de datos personales (Ley 1581 de 2012, arts. 3, 5 y 7).
DATOS_PERSONALES = ("no_contiene", "personales", "sensibles", "menores")


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
    # La misma fecha normalizada en EDTF (servicios/fechas.extremas): la que se
    # usa para ordenar, filtrar y exportar. La de arriba queda como se escribió.
    fechas_extremas_edtf = Column(String(200), nullable=True)
    nota = Column(Text, nullable=True)
    # Inclusión (RiC-R024 includes / is included in): nivel superior inmediato.
    incluido_en_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=True, index=True)
    # Fondo al que pertenece (él mismo si es un fondo): acota búsquedas y duplicados.
    fondo_id = Column(UUID(as_uuid=True), ForeignKey("recursos_documentales.id"), nullable=True, index=True)
    creado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=ahora, nullable=False)

    # --- Descripción (módulo 2) ---
    # Alcance y contenido (ISAD(G) 3.3.1; RiC-A38 Scope and content).
    alcance_contenido = Column(Text, nullable=True)
    # Forma documental (RiC-A17 Documentary form type), del vocabulario.
    forma_documental_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)
    # Procedencia de los campos descriptivos, en columnas propias.
    origen_titulo = Column(Enum("motor", "motor_editado", "persona", name="origen_dato", create_type=False), nullable=True)
    origen_alcance = Column(Enum("motor", "motor_editado", "persona", name="origen_dato", create_type=False), nullable=True)
    confianza_alcance = Column(Float, nullable=True)
    motor = Column(String(120), nullable=True)
    motor_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)  # RiC-E13
    # Idioma del contenido (ISO 639-3, uno o varios; rico:hasOrHadLanguage),
    # con su procedencia: el motor puede proponerlo.
    idiomas = Column(ARRAY(String(3)), nullable=True)
    origen_idiomas = Column(Enum("motor", "motor_editado", "persona", name="origen_dato", create_type=False), nullable=True)
    confianza_idiomas = Column(Float, nullable=True)
    # Condiciones de acceso (RiC-A08) y de uso o reproducción (RiC-A09):
    # descriptivas, distintas de la declaración técnica de derechos PREMIS.
    # Siempre las decide una persona.
    condiciones_acceso = Column(Text, nullable=True)
    condiciones_uso = Column(Text, nullable=True)
    # Historia archivística (ISAD-G 3.2.3; rico:history): cómo llegó el fondo
    # o el documento a su custodio actual (hallazgo DES-06). Distinta de la
    # relación puntual con el custodio (has_or_had_holder).
    historia_archivistica = Column(Text, nullable=True)
    origen_historia_archivistica = Column(String(20), nullable=True)
    # Resto de ISAD-G (hallazgo DES-07): textos que escribe una persona. La
    # tabla de los 26 elementos, con su fuente y su propiedad RiC-O, está en
    # app/servicios/isadg.py.
    forma_ingreso = Column(Text, nullable=True)  # 3.2.4 (además del lote de transferencia)
    valoracion = Column(Text, nullable=True)  # 3.3.2 (además de la regla de retención)
    nuevos_ingresos = Column(Text, nullable=True)  # 3.3.3; rico:accruals
    organizacion = Column(Text, nullable=True)  # 3.3.4; rico:structure
    escrituras = Column(ARRAY(String(4)), nullable=True)  # 3.4.3; ISO 15924 (Latn, Grek…)
    instrumentos_descripcion = Column(Text, nullable=True)  # 3.4.5
    localizacion_originales = Column(Text, nullable=True)  # 3.5.1
    localizacion_copias = Column(Text, nullable=True)  # 3.5.2
    unidades_relacionadas = Column(Text, nullable=True)  # 3.5.3 (material fuera del sistema)
    nota_publicaciones = Column(Text, nullable=True)  # 3.5.4
    nota_archivero = Column(Text, nullable=True)  # 3.7.1
    reglas_descripcion = Column(Text, nullable=True)  # 3.7.2
    # Tipo de una parte documental (anexo, folio, firma, sello), del vocabulario.
    tipo_parte_id = Column(UUID(as_uuid=True), ForeignKey("entidades_vocabulario.id"), nullable=True)
    publicado_en = Column(DateTime(timezone=True), nullable=True)
    publicado_por_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), nullable=True)

    # --- Datos de control para el inventario (módulo 4, FUID del AGN) ---
    # Los escribe siempre una persona al describir o corregir; si faltan,
    # el inventario los marca como pendientes, sin bloquear.
    codigo_referencia = Column(String(60), nullable=True)  # ISAD(G) 3.1.1; RiC-A22 Identifier
    caja = Column(String(30), nullable=True)  # unidad de conservación
    carpeta = Column(String(30), nullable=True)
    folios = Column(Integer, nullable=True)  # ISAD(G) 3.1.5 volumen; RiC-A35 Record Resource Extent
    soporte = Column(String(40), nullable=True)  # ISAD(G) 3.1.5; RiC-A05 Carrier Type del original (papel…)
    # Resto del FUID (Acuerdo 042 de 2002; hallazgo INS-06): otras unidades de
    # conservación y la frecuencia de consulta (alta, media, baja, ninguna).
    tomo = Column(String(30), nullable=True)
    otra_unidad = Column(String(60), nullable=True)
    frecuencia_consulta = Column(String(10), nullable=True)
    # Ley 1581 de 2012 y Esquema de Metadatos del AGN (protección de datos,
    # minimización): qué clase de datos personales contiene. Vacío = sin
    # revisar. No es la clasificación de acceso de la Ley 1712: un documento
    # público puede contener datos personales que se anonimizan al consultarlo.
    datos_personales = Column(String(20), nullable=True)  # DATOS_PERSONALES
    # Accesibilidad (Ley 1680 de 2013; AGN, principio 3): si hay una versión
    # accesible, en qué formato y con qué ayudas (texto alternativo, lectura).
    nota_accesibilidad = Column(Text, nullable=True)
