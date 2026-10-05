"""
Esquemas de respuesta de los instrumentos de descripción y de los datos
abiertos, solo para documentar la API.

No se usan como `response_model`: describen en OpenAPI lo que ya devuelven
las rutas, sin filtrar ni validar la salida. `extra="allow"` deja pasar
cualquier dato adicional.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


# --- Piezas comunes -------------------------------------------------------------------------------


class FondoBreve(BaseModel):
    """El fondo al que pertenece la respuesta: identificador y título."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str


class Miga(BaseModel):
    """Un nivel superior en la ruta de migas de pan."""

    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    titulo: str


class ClaveNombre(BaseModel):
    """Una columna o categoría: clave interna y nombre legible."""

    model_config = ConfigDict(extra="allow")

    clave: str
    nombre: str


# --- Catálogo navegable ---------------------------------------------------------------------------


class NodoArbol(BaseModel):
    """Una descripción del árbol del fondo con sus fechas extremas y su número de hijos."""

    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    titulo: str
    codigo_referencia: str | None
    fechas_extremas: str | None
    hijos: int
    unidades_documentales: int


class NivelCatalogo(BaseModel):
    """Un nivel del árbol del fondo para navegar por migas de pan."""

    model_config = ConfigDict(extra="allow")

    fondo: FondoBreve
    migas: list[Miga]
    actual: NodoArbol
    hijos: list[NodoArbol]


class EntidadFicha(BaseModel):
    """Un punto de acceso de la ficha (agente, lugar, fecha, forma, etc.)."""

    model_config = ConfigDict(extra="allow")

    entidad_id: str
    tipo: str
    valor: Any = None
    subtipo: Any = None
    rol: Any = None
    codigo_ric: Any = None
    uri_rico: Any = None
    en_vocabulario: bool
    documentos: int | None


class FormaDocumentalFicha(BaseModel):
    """La forma documental de la descripción y cuántos documentos visibles la comparten."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    documentos: int


class FichaConsulta(BaseModel):
    """Ficha de consulta de una descripción publicada: datos, entidades, archivos y preservación."""

    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    titulo: str
    alcance_contenido: Any = None
    incluido_en: Any = None
    entidades: list[EntidadFicha]
    instanciaciones: list[dict]
    idiomas: Any = None
    condiciones_acceso: Any = None
    historia_archivistica: Any = None
    condiciones_uso: Any = None
    nota_accesibilidad: Any = None
    tipo_parte: str | None
    partes: list[dict]
    parte_de: dict | None
    secuencia: list[dict]
    publicado_en: Any = None
    forma_documental: FormaDocumentalFicha | None
    migas: list[Miga]
    fechas_extremas: str | None
    control: dict
    hijos: int
    retencion: dict | None


class SubgrafoFondo(BaseModel):
    """Vecindario de un nodo del grafo RiC: nodos, aristas y límites del recorrido."""

    model_config = ConfigDict(extra="allow")

    fondo: FondoBreve
    centro: str
    saltos: int
    nodos: list[dict]
    aristas: list[dict]
    truncado: bool
    maximo_nodos: int
    filtros_activos: int


# --- Resumen del fondo ----------------------------------------------------------------------------


class ConteoNivel(BaseModel):
    """Cuántas descripciones hay de un nivel de descripción."""

    model_config = ConfigDict(extra="allow")

    nivel: str
    nombre: str
    cantidad: int


class EntidadCitada(BaseModel):
    """Una entidad del vocabulario y cuántos documentos la citan."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    documentos: int


class CoherenciaFechas(BaseModel):
    """Fechas extremas declaradas del fondo frente a las de sus documentos."""

    model_config = ConfigDict(extra="allow")

    declaradas: str | None
    documentos: str
    coinciden: bool


class ResumenFondo(BaseModel):
    """Resumen del fondo: composición, productores, lugares, formas, archivos y fechas."""

    model_config = ConfigDict(extra="allow")

    niveles: list[ConteoNivel]
    descripciones: int
    archivos: int
    productores: list[EntidadCitada]
    lugares: list[EntidadCitada]
    formas: list[EntidadCitada]
    fechas: CoherenciaFechas | None


# --- Índice de términos ---------------------------------------------------------------------------


class DescripcionIndice(BaseModel):
    """Una descripción a la que lleva un término del índice."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    nivel: str


class EntradaIndice(BaseModel):
    """Un término del índice con los documentos visibles que lo citan."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    subtipo: str | None
    documentos: int
    descripciones: list[DescripcionIndice]


class LetraIndice(BaseModel):
    """Los términos de un tipo que empiezan por una misma letra."""

    model_config = ConfigDict(extra="allow")

    letra: str
    entidades: list[EntradaIndice]


class GrupoIndice(BaseModel):
    """Los términos de un mismo tipo de entidad, en orden alfabético."""

    model_config = ConfigDict(extra="allow")

    clase: str
    total: int
    letras: list[LetraIndice]


class IndiceTerminos(BaseModel):
    """Índice de términos del fondo por tipo y en orden alfabético."""

    model_config = ConfigDict(extra="allow")

    fondo: FondoBreve
    grupos: list[GrupoIndice]


# --- Inventario FUID y guía -----------------------------------------------------------------------


class ColumnaFuid(BaseModel):
    """Una columna del Formato Único de Inventario Documental."""

    model_config = ConfigDict(extra="allow")

    clave: str
    nombre: str
    obligatoria: bool


class FilaFuid(BaseModel):
    """Un renglón del inventario: valores, campos obligatorios pendientes y si es restringido."""

    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    valores: dict[str, Any]
    pendientes: list[str]
    restringido: bool


class AlertaPendientes(BaseModel):
    """Alerta abierta por campos obligatorios del FUID sin dato."""

    model_config = ConfigDict(extra="allow")

    id: str
    mensaje: str


class VistaPreviaInventario(BaseModel):
    """Inventario FUID armado en pantalla, con sus pendientes y la alerta si la hay."""

    model_config = ConfigDict(extra="allow")

    nivel: Miga
    fondo: FondoBreve
    columnas: list[ColumnaFuid]
    filas: list[FilaFuid]
    pendientes: int
    pendientes_por_campo: dict[str, int]
    alerta: AlertaPendientes | None


class BorradorGuia(BaseModel):
    """Borrador de la nota de presentación de la guía del fondo."""

    model_config = ConfigDict(extra="allow")

    texto: str
    redactado_por_motor: bool
    aviso: str | None


# --- Datos abiertos -------------------------------------------------------------------------------


class FilaLey1712(BaseModel):
    """Un documento o archivo del índice de información clasificada y reservada."""

    model_config = ConfigDict(extra="allow")

    categoria: str
    titulo: str
    idioma: str | None
    soporte: str | None
    fecha_generacion: str | None
    responsable_produccion: str | None
    responsable_informacion: str
    objetivo: str | None
    fundamento: str | None
    excepcion: str
    fecha_calificacion: str
    plazo: str
    estado: str


class IndiceLey1712(BaseModel):
    """Índice de información clasificada y reservada del fondo (Ley 1712, art. 20)."""

    model_config = ConfigDict(extra="allow")

    fondo: str
    columnas: list[ClaveNombre]
    filas: list[FilaLey1712]
