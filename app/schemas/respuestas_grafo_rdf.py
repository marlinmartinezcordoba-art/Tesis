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


class DiferenciaGrafo(BaseModel):
    tabla: str
    id: str
    columna: str | None
    problema: str


class CoherenciaGrafo(BaseModel):
    """Si las tablas coinciden con el grafo RiC-O guardado (la fuente de verdad)."""
    coinciden: bool
    diferencias: list[DiferenciaGrafo]


class ReconstruccionGrafo(BaseModel):
    """Lo que se rehízo en las tablas desde el grafo."""
    filas: dict[str, int]
    corregidas: int
    sobrantes: list[DiferenciaGrafo]
    diferencias_despues: list[DiferenciaGrafo]


class CriterioNativo(BaseModel):
    """Uno de los siete criterios de un sistema nativo en RiC, con su evidencia medida."""
    model_config = ConfigDict(extra="allow")

    numero: int
    criterio: str
    estado: str
    evidencia: list[str]
    verificacion: str
    prueba: str
    motivo: str | None
    en_uso: bool  # el acervo ya tiene casos que ejercen la capacidad


class AdopcionRicOut(BaseModel):
    """Nivel de adopción de RiC del sistema, evaluado en vivo contra los siete criterios."""
    model_config = ConfigDict(extra="allow")

    nivel: dict
    niveles: list[dict]
    cumplidos: int
    criterios: list[CriterioNativo]
    conformidad: dict
    cobertura: dict
    perfil_agn: dict
    consultas: list[dict]
