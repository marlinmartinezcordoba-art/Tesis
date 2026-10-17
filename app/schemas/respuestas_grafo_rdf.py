"""Respuestas del grafo RiC-O persistente (estado del almacén y de cada grafo)."""

from pydantic import BaseModel, ConfigDict


class AlmacenGrafo(BaseModel):
    model_config = ConfigDict(extra="allow")
    ok: bool
    motor: str | None = None
    grafos: int | None = None
    tripletas: int | None = None
    persistente: bool | None = None
    motivo: str | None = None


class GrafoFondo(BaseModel):
    fondo_id: str
    fondo: str
    alcance: str
    nombre: str
    al_dia: bool
    version_datos: int
    version_sincronizada: int
    sincronizado_en: str | None
    tripletas: int | None
    huella: str | None
    conforme: bool | None
    problemas_owl: int | None
    resultados_shacl: int | None
    error: str | None


class EstadoGrafoRdf(BaseModel):
    almacen: AlmacenGrafo
    grafos: list[GrafoFondo]
