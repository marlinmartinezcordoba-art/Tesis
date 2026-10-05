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
