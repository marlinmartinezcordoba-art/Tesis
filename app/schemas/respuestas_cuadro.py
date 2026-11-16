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
    intermedias: list[NodoCuadroLeido] = []
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


class LecturaCuadro(BaseModel):
    """Avance de una lectura en segundo plano: cuántos archivos van y cuántos faltan."""
    model_config = ConfigDict(extra="allow")

    id: str
    estado: str  # leyendo | listo | error
    hechos: int
    total: int
    faltan: int
    actual: str | None
    archivos: list[dict[str, Any]]
    segundos: int
    error: str | None
    codigo: int | None
    resultado: dict[str, Any] | None  # la vista previa, cuando termina


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
    # Lo que la carga configuró en la parametrización: dependencias, series, subseries, tipos y filas de la matriz.
    parametrizacion: dict[str, int | list[str]] | None = None
    version: dict[str, str] | None = None  # la TRD versión 1 del fondo creado: vigente o en borrador


# --- Avance del fondo (Inicio) --------------------------------------------------------------------


class PasoAvance(BaseModel):
    """Un paso del recorrido archivístico del fondo y su siguiente acción."""

    clave: str
    titulo: str
    estado: str  # hecho | en_curso | pendiente
    resumen: str
    accion: str | None
    ruta: str | None
    modulo: str


class AvanceFondo(BaseModel):
    """Dónde va el fondo en el recorrido archivístico y qué sigue."""

    fondo: dict
    pasos: list[PasoAvance]
    siguiente: str | None
    hechos: int
    total: int
    conocimiento: dict | None = None  # cifras RiC del fondo para el panel institucional


class AgrupacionRenombrada(BaseModel):
    """La agrupación con su nombre corregido y cuántas dependencias de la TRD se corrigieron con ella."""
    id: str
    titulo: str
    dependencias_trd_corregidas: int


class ContextoFuncional(BaseModel):
    """Funciones del fondo (rico:ActivityType) con sus actividades, agentes, mandatos, series y documentos."""
    model_config = ConfigDict(extra="allow")

    fondo: dict
    funciones: list[dict]
    actividades_sin_funcion: list[dict]
    totales: dict


class CalidadFondo(BaseModel):
    """Validación semántica y calidad del fondo: hallazgos con su descripción afectada, problema, regla y acción."""
    model_config = ConfigDict(extra="allow")

    fondo: dict
    resumen: list[dict]
    errores: int
    avisos: int
    hallazgos: list[dict]
    descripciones_revisadas: int
    relaciones_revisadas: int


class TablaControlAcceso(BaseModel):
    """TCA del fondo: la condición de acceso de cada serie y subserie, propia o heredada."""
    model_config = ConfigDict(extra="allow")

    fondo: dict
    series: list[dict]
    totales: dict


class GobiernoArchivistico(BaseModel):
    """PGD y PINAR del fondo como mandatos, con los programas, proyectos y acciones que regulan."""
    model_config = ConfigDict(extra="allow")

    fondo: dict
    planes: list[dict]
    faltan: list[str]


class EstructuraOrganica(BaseModel):
    """Dependencias como agentes RiC: su agrupación, su superior y su vigencia."""
    model_config = ConfigDict(extra="allow")

    fondo: dict
    entidad: dict | None
    dependencias: list[dict]
    totales: dict


class ImportacionFuid(BaseModel):
    """Vista previa o resultado de importar un FUID existente."""
    model_config = ConfigDict(extra="allow")
