"""
Esquemas de respuesta del buscador unificado y de la salud del sistema,
para documentar la API en OpenAPI y para la prueba de contrato.

Solo documentan: las rutas no los usan como response_model, así que no
filtran ni cambian lo que se responde. Admiten campos adicionales.
"""

from pydantic import BaseModel, ConfigDict

# --- Búsqueda (RF-SEARCH-001 y RF-SEARCH-002) -------------------------------------------------


class FondoHallado(BaseModel):
    """El fondo al que pertenece un documento hallado."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str


class DocumentoHallado(BaseModel):
    """Una descripción hallada, con los motivos y el fragmento que coincidió."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    nivel: str
    codigo_referencia: str | None
    fechas: str | None
    fondo: FondoHallado
    ruta: list[str]
    motivos: list[str]
    fragmento: str | None
    borrador: bool
    puntaje: float


class EjemploAutoridad(BaseModel):
    """Un documento visible que cita la autoridad hallada."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    nivel: str


class AutoridadHallada(BaseModel):
    """Una autoridad del vocabulario hallada por nombre o identificador."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    clase: str
    subtipo: str | None
    fondo_id: str
    motivo: str | None
    documentos: int
    ejemplos: list[EjemploAutoridad]


class ArchivoSinDescribir(BaseModel):
    """Un archivo cuyo texto coincidió y que todavía no está descrito."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    fondo_id: str
    fondo: str


class FacetaFondo(BaseModel):
    """Cuántos resultados hay en cada fondo."""
    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str
    total: int


class FacetaAgente(BaseModel):
    """Un agente que citan los resultados, para afinar la búsqueda."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    documentos: int


class FacetasBusqueda(BaseModel):
    """Facetas para afinar: niveles, fondos, agentes y años extremos."""
    model_config = ConfigDict(extra="allow")

    niveles: dict[str, int]
    fondos: list[FacetaFondo]
    agentes: list[FacetaAgente]
    anios: list[int] | None


class ResultadoBusquedaOut(BaseModel):
    """Resultados del buscador unificado, paginados y con sus facetas."""
    model_config = ConfigDict(extra="allow")

    q: str
    total: int
    pagina: int
    por_pagina: int
    documentos: list[DocumentoHallado]
    autoridades: list[AutoridadHallada]
    archivos_sin_describir: list[ArchivoSinDescribir]
    facetas: FacetasBusqueda
    alcance_reserva: str


# --- Salud del sistema (RF-OPS-001 y NFR-10) ---------------------------------------------------


class PiezaSalud(BaseModel):
    """El estado de una pieza del sistema y, si falla, el motivo."""
    model_config = ConfigDict(extra="allow")

    ok: bool
    motivo: str | None = None


class SaludOut(BaseModel):
    """Salud del sistema: base de datos, almacén, trabajador, respaldo y conexión."""
    model_config = ConfigDict(extra="allow")

    estado: str
    fecha: str
    base_de_datos: PiezaSalud
    conexion: PiezaSalud
    almacen: PiezaSalud
    trabajador: PiezaSalud
    respaldo: PiezaSalud | None = None
    grafo_rdf: PiezaSalud | None = None

class CantidadOut(BaseModel):
    que: str
    cantidad: int


class InventarioReinicioOut(BaseModel):
    """Lo que hay hoy y lo que se borraría."""
    model_config = ConfigDict(extra="allow")

    frase: str
    se_borra: list[CantidadOut]
    tesauros: int
    se_conserva: list[str]
    sin_clasificar: list[str]


class ReinicioOut(BaseModel):
    """Lo que se borró, el respaldo que lo guarda y dónde quedaron los archivos."""
    model_config = ConfigDict(extra="allow")

    borrado: list[CantidadOut]
    respaldo: dict
    archivos_apartados: dict
    aviso_grafos: str | None
    tesauros_borrados: bool


class EstadoAsistenteOut(BaseModel):
    """Si el asistente con IA está disponible (hay motor de análisis configurado)."""
    model_config = ConfigDict(extra="allow")

    disponible: bool
    modelo: str | None
    aviso: str


class RespuestaAsistenteOut(BaseModel):
    """La respuesta del asistente a la última pregunta."""
    model_config = ConfigDict(extra="allow")

    respuesta: str
    modelo: str
