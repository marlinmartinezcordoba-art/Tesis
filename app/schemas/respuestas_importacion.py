"""Esquemas de respuesta (solo documentación OpenAPI) de la importación de RiC-O. Admiten campos adicionales."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.respuestas_cuadro import ValidacionRico


class VistaPreviaRico(BaseModel):
    """Lo que se importaría: el fondo, sus niveles, las entidades, las filas del cuadro y lo que se omite."""
    model_config = ConfigDict(extra="allow")

    fondo: str | None
    niveles: dict[str, int]
    entidades: dict[str, int]
    filas_cuadro: int
    filas_con_problemas: int
    series_sin_seccion: int
    productor_sugerido: str | None
    omitidas: dict[str, int]
    problemas: list[str]
    trd: dict[str, Any] | None = None
    filas: list[dict[str, Any]]
    huella: str


class ImportacionRico(BaseModel):
    """El fondo importado (o lo que se crearía), con su validación RiC-O."""
    model_config = ConfigDict(extra="allow")

    creado: bool
    fondo: dict[str, Any] | None
    cuadro: dict[str, Any]
    parametrizacion: dict[str, int] | None
    contenido: dict[str, Any]
    omitidas: dict[str, int]
    validacion: ValidacionRico
    version: dict[str, str] | None
