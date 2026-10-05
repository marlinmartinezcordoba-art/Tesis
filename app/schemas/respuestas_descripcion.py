"""
Esquemas de respuesta del módulo 2 (descripción) y de la ficha del
catálogo, para documentar la API en OpenAPI y para la prueba de contrato.

Solo documentan: las rutas no los usan como response_model, así que no
filtran ni cambian lo que se responde. Admiten campos adicionales.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

# --- Piezas comunes -----------------------------------------------------------------------


class ReferenciaBreve(BaseModel):
    """Una descripción nombrada por su identificador, título y nivel."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    nivel: str


class FondoBreve(BaseModel):
    """El fondo al que pertenece lo que se describe."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str


class AgenteBreve(BaseModel):
    """Un agente del vocabulario, por su identificador y nombre."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str


class CustodioOut(BaseModel):
    """Un tramo de la cadena de custodia de un documento o de un archivo."""
    model_config = ConfigDict(extra="allow")

    relacion_id: str
    agente: AgenteBreve | None
    periodo: str | None
    periodo_legible: str | None
    nota: str | None


# --- Propuestas del motor (RF-AI-002) -----------------------------------------------------------


class PropuestaIAOut(BaseModel):
    """Una propuesta del motor guardada como registro inalterable, con su huella."""
    model_config = ConfigDict(extra="allow")

    id: str
    origen: str
    nivel: str
    motor: str | None
    version_modelo: str | None
    version_prompt: str | None
    generada_en: str
    duracion_ms: int | None
    estado: str
    estado_nombre: str
    estado_en: str | None
    disponible: bool
    aviso: str | None
    entidades: int
    confianza_media: float | None
    huella: str
    integra: bool
    trabajo_id: str | None
    evaluacion_id: str | None
    recurso_id: str | None
    instanciaciones: list[str]
    parametros: Any
    entrada: Any = None
    respuesta: Any = None
    contenido: Any = None


# --- Espacio de trabajo ------------------------------------------------------------------------


class DocumentoTrabajo(BaseModel):
    """Un documento abierto en el espacio de trabajo, con su texto extraído."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    texto: str
    origen_texto: str | None
    confianza_ocr: float | None
    ocr_baja_confianza: bool
    expediente_destino_id: str | None


class EspacioTrabajoOut(BaseModel):
    """Todo lo que la pantalla de trabajo necesita para abrirse o recargarse."""
    model_config = ConfigDict(extra="allow")

    trabajo_id: str
    nivel: str
    fondo: FondoBreve
    recurso_id: str | None
    documentos: list[DocumentoTrabajo]
    umbral_ocr: int
    propuesta: dict | None
    minutos_bloqueo: int
    umbral_confianza: float


class PaginasOut(BaseModel):
    """Si el documento se puede mostrar como imagen y cuántas páginas tiene."""
    model_config = ConfigDict(extra="allow")

    admite: bool
    total: int


class PrevisualizacionOut(BaseModel):
    """Datos del visor: páginas que se pueden mostrar y texto extraído."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    formato: str | None
    puid: str | None
    admite: bool
    total: int
    texto: str | None
    origen_texto: str | None


class ProductividadOut(BaseModel):
    """Lo descrito hoy por quien consulta y el total publicado del fondo."""
    model_config = ConfigDict(extra="allow")

    hoy_por_mi: int
    total_fondo: int


# --- Detalle interno de una descripción --------------------------------------------------------------


class ClasificacionOut(BaseModel):
    """La clasificación de acceso de la descripción (Ley 1712 de 2014)."""
    model_config = ConfigDict(extra="allow")

    acceso: str
    fundamento: str | None
    reproduccion: str | None
    vigente_hasta: str | None
    de: str | None = None


class FormaDocumentalBreve(BaseModel):
    """La forma documental asignada, con su origen."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    origen: str | None


class EntidadDetalle(BaseModel):
    """Una entidad relacionada con la descripción, con su origen y confianza."""
    model_config = ConfigDict(extra="allow")

    relacion_id: str
    entidad_id: str
    tipo: str
    valor: str | None
    subtipo: str | None
    rol: str | None
    codigo_ric: str
    uri_rico: str | None
    fragmento: str | None
    documento_id: str | None
    pagina: int | None
    zona: Any
    propuesta_id: str | None
    origen: str
    confianza: float | None
    motor: str | None
    estado_revision: str


class InstanciacionDetalle(BaseModel):
    """Un archivo o un original físico de la descripción, con su custodia."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    custodios: list[CustodioOut]
    fisica: bool | None = None
    soporte: str | None = None
    ubicacion: str | None = None
    caracteristicas_fisicas: str | None = None
    estado_conservacion: str | None = None
    deposito: str | None = None
    estante: str | None = None
    entrepano: str | None = None
    signatura: str | None = None


class ProteccionOut(BaseModel):
    """Datos personales (Ley 1581) y nota de accesibilidad (Ley 1680)."""
    model_config = ConfigDict(extra="allow")

    datos_personales: str | None
    nota_accesibilidad: str | None


class AtributoConFuente(BaseModel):
    """Un atributo con valor, con su fuente, confianza y cardinalidad (RF-RIC-002)."""
    model_config = ConfigDict(extra="allow")

    clave: str
    etiqueta: str
    valor: Any
    fuente: str
    confianza: float | None
    cardinalidad: str
    rico: str | None
    isad: str | None


class VocabularioBreve(BaseModel):
    """Una entidad del vocabulario por su identificador, nombre y subtipo."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    subtipo: str | None


class RecorteBreve(BaseModel):
    """Un archivo de una parte documental, con la zona recortada."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    recorte_zona: Any = None


class ParteDetalle(BaseModel):
    """Una parte documental del documento (RiC-R002)."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    nivel: str
    relacion_id: str
    tipo_parte: str | None
    alcance_contenido: str | None
    instanciaciones: list[RecorteBreve]


class ParteDeOut(BaseModel):
    """El documento del que esta descripción es parte."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    nivel: str
    relacion_id: str


class SecuenciaDetalle(BaseModel):
    """Una descripción que precede o sigue a esta en la secuencia."""
    model_config = ConfigDict(extra="allow")

    relacion_id: str
    id: str
    titulo: str
    posicion: str
    uri_rico: str


class DetalleDescripcionOut(BaseModel):
    """Descripción publicada, vista interna: cada dato con su origen y confianza."""
    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    titulo: str
    alcance_contenido: str | None
    fondo_id: str
    clasificacion: ClasificacionOut | None
    clasificacion_heredada: ClasificacionOut | None
    incluido_en: ReferenciaBreve | None
    forma_documental: FormaDocumentalBreve | None
    entidades: list[EntidadDetalle]
    instanciaciones: list[InstanciacionDetalle]
    control: dict[str, Any]
    proteccion: ProteccionOut
    atributos: list[AtributoConFuente]
    propuestas_ia: list[PropuestaIAOut]
    idiomas: list[str]
    origen_idiomas: str | None
    confianza_idiomas: float | None
    condiciones_acceso: str | None
    condiciones_uso: str | None
    historia_archivistica: str | None
    origen_historia_archivistica: str | None
    isadg: dict[str, Any]
    tipo_parte: VocabularioBreve | None
    partes: list[ParteDetalle]
    parte_de: ParteDeOut | None
    secuencia: list[SecuenciaDetalle]
    origen_titulo: str | None
    origen_alcance: str | None
    confianza_alcance: float | None
    motor: str | None
    publicado_en: str | None
    actualizado_en: str | None


class ReabrirOut(BaseModel):
    """El trabajo abierto para corregir y la descripción tal como está."""
    model_config = ConfigDict(extra="allow")

    trabajo_id: str
    descripcion: DetalleDescripcionOut


class CustodiosOut(BaseModel):
    """El tramo de custodia registrado y la cadena completa del archivo."""
    model_config = ConfigDict(extra="allow")

    relacion_id: str
    custodios: list[CustodioOut]


# --- Ficha ISAD(G) ------------------------------------------------------------------------------


class ElementoIsadg(BaseModel):
    """Un elemento de la ISAD(G), con su valor, su fuente y su propiedad RiC-O."""
    model_config = ConfigDict(extra="allow")

    elemento: str
    area: str
    nombre: str
    valor: str | None
    fuente: str
    rico: str | None  # algunos elementos no tienen propiedad en RiC-O 1.1
    sin_propiedad: str | None


class FichaIsadgOut(BaseModel):
    """Ficha ISAD(G) completa: los 26 elementos y cuántos tienen dato."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    elementos: list[ElementoIsadg]
    con_dato: int
    total: int


# --- Atributos y versiones (RF-RIC-001 y RF-RIC-002) ------------------------------------------------


class AtributoCatalogo(BaseModel):
    """Un atributo del catálogo: tipo, cardinalidad, ISAD(G), RiC-O y procedencia."""
    model_config = ConfigDict(extra="allow")

    clave: str
    etiqueta: str
    tipo: str
    cardinalidad: str
    minimo: int
    maximo: int
    isad: str | None
    rico: str | None
    procedencia: str


class VersionResumen(BaseModel):
    """Una versión de la descripción, con su autor y lo que cambió."""
    model_config = ConfigDict(extra="allow")

    numero: int
    motivo: str
    motivo_nombre: str
    restaurada_de: int | None
    autor: str | None
    creada_en: str
    huella: str
    integra: bool
    con_contexto: bool
    cambios: list[dict[str, Any]]


class VersionCompleta(BaseModel):
    """Una versión completa: atributos y contexto, con su huella verificada."""
    model_config = ConfigDict(extra="allow")

    numero: int
    motivo: str
    creada_en: str
    huella: str
    integra: bool
    contenido: dict[str, Any]


# --- Ficha de consulta (catálogo) -------------------------------------------------------------------


class EntidadPublica(BaseModel):
    """Una entidad relacionada, tal como se muestra en la ficha de consulta."""
    model_config = ConfigDict(extra="allow")

    entidad_id: str
    tipo: str
    valor: str | None
    subtipo: str | None
    rol: str | None
    codigo_ric: str
    uri_rico: str | None


class ArchivoBreve(BaseModel):
    """Un archivo por su identificador y nombre."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str


class PartePublica(BaseModel):
    """Una parte documental visible en la ficha de consulta."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    tipo_parte: str | None
    alcance_contenido: str | None
    instanciaciones: list[ArchivoBreve]


class SecuenciaPublica(BaseModel):
    """Una descripción vecina en la secuencia, visible para quien consulta."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    posicion: str
    uri_rico: str


class FichaPublicaOut(BaseModel):
    """Ficha de consulta de una descripción publicada, sin lo reservado."""
    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    titulo: str
    alcance_contenido: str | None
    incluido_en: ReferenciaBreve | None
    forma_documental: str | None
    entidades: list[EntidadPublica]
    instanciaciones: list[InstanciacionDetalle]
    idiomas: list[str]
    condiciones_acceso: str | None
    historia_archivistica: str | None
    condiciones_uso: str | None
    nota_accesibilidad: str | None
    tipo_parte: str | None
    partes: list[PartePublica]
    parte_de: ReferenciaBreve | None
    secuencia: list[SecuenciaPublica]
    publicado_en: str | None
