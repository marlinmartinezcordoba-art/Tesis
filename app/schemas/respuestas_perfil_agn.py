"""
Esquemas de respuesta de la completitud de la descripción (reglas del AGN).

Solo documentan en OpenAPI lo que devuelven las rutas (se declaran con
`responses=`, no con `response_model=`): no filtran ni validan la salida.
"""

from pydantic import BaseModel, ConfigDict


class CatalogoCorrespondencias(BaseModel):
    """Correspondencias AGN, RiC-CM, RiC-O y RICORA, con fuentes, capas y erratas."""

    model_config = ConfigDict(extra="allow")

    fuentes: dict[str, dict]
    capas: dict[str, str]
    estados: dict[str, str]
    niveles: dict[str, str]
    filas: list[dict]
    resumen: dict[str, int]
    erratas: list[dict]
    codigos_agn_incorrectos: int


class CriterioCalidad(BaseModel):
    """Criterio del perfil: a qué nivel pertenece, si aplica y si se cumple."""

    model_config = ConfigDict(extra="allow")

    clave: str
    fila: str
    elemento: str
    nivel: str
    aplica: bool
    cumple: bool | None


class AvanceNivel(BaseModel):
    """Cuántos criterios de un nivel aplican y cuántos se cumplen."""

    model_config = ConfigDict(extra="allow")

    aplican: int
    cumplen: int
    porcentaje: int | None


class CalidadDescripcion(BaseModel):
    """Qué datos tiene y cuáles le faltan a una descripción, por nivel."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str | None
    nivel: str
    criterios: list[CriterioCalidad]
    por_nivel: dict[str, AvanceNivel]
    avisos: list[str]
    incoherencias: list[str]
    porcentaje: int | None
    nivel_alcanzado: str | None


class FondoResumen(BaseModel):
    """Fondo al que se refiere el resumen."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str | None


class CriterioFondo(BaseModel):
    """Cumplimiento de un criterio sobre las descripciones del fondo a las que aplica."""

    model_config = ConfigDict(extra="allow")

    clave: str
    fila: str
    elemento: str
    nivel: str
    aplican: int
    cumplen: int
    porcentaje: int


class IncoherenciaDescripcion(BaseModel):
    """Descripción con datos incoherentes (p. ej. datos sensibles con acceso público)."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str | None
    detalle: list[str]


class DescripcionPendiente(BaseModel):
    """Descripción que aún no cumple todos sus criterios."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str | None
    nivel: str
    porcentaje: int


class CalidadFondo(BaseModel):
    """Completitud de las descripciones del fondo, por criterio y por nivel."""

    model_config = ConfigDict(extra="allow")

    fondo: FondoResumen
    descripciones: int
    truncado: bool
    criterios: list[CriterioFondo]
    nivel_alcanzado: dict[str, int]
    incoherencias: list[IncoherenciaDescripcion]
    pendientes: list[DescripcionPendiente]
