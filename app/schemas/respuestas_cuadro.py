"""
Esquemas de respuesta (solo documentación OpenAPI) del cuadro de
clasificación (CCD) y la tabla de retención (TRD). Admiten campos adicionales.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class NodoCuadroLeido(BaseModel):
    """Un nivel leído del archivo: código propio y nombre."""
    model_config = ConfigDict(extra="allow")

    codigo: str | None
    nombre: str


class FilaCuadroOut(BaseModel):
    """Una serie o subserie leída, con su retención, sus tipos documentales y lo que no se entendió."""
    model_config = ConfigDict(extra="allow")

    fila: int
    seccion: NodoCuadroLeido | None
    subseccion: NodoCuadroLeido | None
    serie: NodoCuadroLeido | None
    subserie: NodoCuadroLeido | None
    tipos: list[str]
    gestion: int | None
    central: int | None
    disposicion: str | None
    otras_disposiciones: list[str]
    procedimiento: str | None
    funcion: str | None
    problemas: list[str]
    codigos: dict[str, str | None]


class VistaPreviaCuadro(BaseModel):
    """Lo que el sistema entendió del archivo, sin crear nada."""
    model_config = ConfigDict(extra="allow")

    origen: str
    filas: list[FilaCuadroOut]
    resumen: dict[str, int]


class InformeCuadro(BaseModel):
    """Lo que se creó, lo que ya existía y los avisos."""
    model_config = ConfigDict(extra="allow")

    creados: dict[str, int]
    reutilizados: int
    reglas: int
    tipos_documentales: int
    funciones: int
    avisos: list[str]


class NodoCuadro(BaseModel):
    """Un nivel del cuadro con su código, su regla de retención y cuántos expedientes tiene."""
    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    codigo: str | None
    titulo: str
    regla: dict[str, Any] | None
    expedientes: int
    hijos: list["NodoCuadro"]


class ValidacionRico(BaseModel):
    """El cuadro armado como grafo RiC-O 1.1 y validado (OWL y SHACL)."""
    conforme: bool
    ontologia: str
    tripletas: int
    por_clase: dict[str, int]
    problemas_owl: list[str]
    resultados_shacl: list[dict[str, Any]]


class PruebaCuadro(BaseModel):
    """Lo que se crearía (o se creó) y su validación RiC-O."""
    creado: bool
    informe: InformeCuadro
    validacion: ValidacionRico


class FondoConfigurado(BaseModel):
    """El fondo configurado desde su cuadro de clasificación (o lo que se crearía)."""
    creado: bool
    fondo: dict[str, Any] | None
    informe: InformeCuadro
    validacion: ValidacionRico
