"""
Esquemas de respuesta (solo documentación OpenAPI) de la evaluación ciega
del motor frente a archivistas.

No se usan como response_model: describen lo que ya devuelven las rutas,
sin filtrar ni validar la salida. Cada modelo admite campos adicionales.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class EvaluacionOut(BaseModel):
    """Evaluación ciega con su estado y el número de documentos."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    protocolo: str | None
    estado: str
    umbral_similitud: float
    creada_en: str
    iniciada_en: str | None
    cerrada_en: str | None
    documentos: int
    con_propuesta: int


class PropuestasGeneradasOut(BaseModel):
    """Cuántas propuestas del motor se generaron y los avisos de las que faltaron."""
    model_config = ConfigDict(extra="allow")

    generadas: int
    avisos: list[str]
    evaluacion: EvaluacionOut


class EstadoAnotacion(BaseModel):
    """Identificador y estado de una anotación propia."""
    model_config = ConfigDict(extra="allow")

    id: str
    estado: str


class TareaEvaluacion(BaseModel):
    """Un documento de la evaluación y lo que la persona ya hizo con él."""
    model_config = ConfigDict(extra="allow")

    instanciacion_id: str
    nombre: str
    ciega: EstadoAnotacion | None
    asistida: EstadoAnotacion | None
    puede_ciega: bool
    calificado: bool


class TareasOut(BaseModel):
    """La evaluación y las tareas de la persona en ella."""
    model_config = ConfigDict(extra="allow")

    evaluacion: EvaluacionOut
    tareas: list[TareaEvaluacion]


class DescripcionEvaluada(BaseModel):
    """Una descripción en RiC (de una archivista o del motor): título,
    alcance, entidades con su clase y relaciones con su propiedad de RiC-O."""
    model_config = ConfigDict(extra="allow")

    titulo: str | None = None
    alcance: str | None = None
    entidades: list[dict[str, Any]] = []
    relaciones: list[dict[str, Any]] = []


class ConformidadRic(BaseModel):
    """Si la descripción es RiC válida (mapeo único y OWL oficial de RiC-O 1.1) y por qué no."""
    model_config = ConfigDict(extra="allow")

    conforme: bool
    relaciones: int
    relaciones_validas: int
    problemas: list[str]


class PropiedadRic(BaseModel):
    """Una relación de RiC-O disponible para describir y los extremos que admite."""
    model_config = ConfigDict(extra="allow")

    codigo: str
    rico: str
    papel: str
    etiqueta: str
    codigo_cm: str | None
    origen: list[str]
    destino: list[str]


class DocumentoAnotado(BaseModel):
    """Documento que se describe, con su texto extraído."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    texto: str | None


class AnotacionOut(BaseModel):
    """Descripción de una archivista, ciega o asistida."""
    model_config = ConfigDict(extra="allow")

    id: str
    condicion: str
    estado: str
    datos: DescripcionEvaluada
    conformidad: ConformidadRic | None = None
    iniciada_en: str
    enviada_en: str | None
    documento: DocumentoAnotado


class CalificadoOut(BaseModel):
    """Constancia de que la propuesta quedó calificada."""
    model_config = ConfigDict(extra="allow")

    calificado: bool


class EstadoAnulacionOut(BaseModel):
    """Estado de la anotación después de anularla."""
    model_config = ConfigDict(extra="allow")

    estado: str


class Metricas(BaseModel):
    """Verdaderos y falsos positivos, falsos negativos, precisión, exhaustividad y F1."""
    model_config = ConfigDict(extra="allow")

    vp: int
    fp: int
    fn: int
    precision: float | None
    exhaustividad: float | None
    f1: float | None


class TablaMetricas(BaseModel):
    """Métricas por tipo de entidad, en total (micro) y su F1 promedio (macro)."""
    model_config = ConfigDict(extra="allow")

    por_tipo: dict[str, Metricas]
    micro: Metricas
    macro_f1: float | None


class MotorUsado(BaseModel):
    """Motor y versión de la instrucción con que se generaron las propuestas."""
    model_config = ConfigDict(extra="allow")

    motor: str | None
    version_prompt: str | None


class TiempoCondicion(BaseModel):
    """Tiempos de descripción en una condición (ciega o asistida)."""
    model_config = ConfigDict(extra="allow")

    n: int
    mediana_minutos: float | None
    media_minutos: float | None


class RubricaCriterio(BaseModel):
    """Calificaciones de un criterio de la rúbrica y su acuerdo entre evaluadores."""
    model_config = ConfigDict(extra="allow")

    n: int
    media: float | None
    pares: int
    kappa_ponderado: float | None


class DocumentoResultado(BaseModel):
    """Resultado de la evaluación para un documento."""
    model_config = ConfigDict(extra="allow")

    instanciacion_id: str
    nombre: str
    entidades_motor: int
    relaciones_motor: int
    referencias_ciegas: int
    f1_flexible: float | None
    f1_relaciones_flexible: float | None
    motor_conforme: bool
    descrito_durante_la_evaluacion: bool


class Confusion(BaseModel):
    """Mismos extremos, otra propiedad: lo que dijo el motor y lo que dijo la archivista."""
    model_config = ConfigDict(extra="allow")

    motor: str
    archivista: str
    veces: int


class ResultadoRelaciones(BaseModel):
    """Métricas de las relaciones RiC por propiedad, acuerdo y confusiones."""
    model_config = ConfigDict(extra="allow")

    estricto: TablaMetricas
    flexible: TablaMetricas
    acuerdo_entre_archivistas: Metricas | None
    confusiones: list[Confusion]
    propiedades: dict[str, str]


class ProblemaFrecuente(BaseModel):
    """Un problema de conformidad y cuántas veces aparece."""
    model_config = ConfigDict(extra="allow")

    problema: str
    veces: int


class ResumenConformidad(BaseModel):
    """Conformidad RiC-O de las descripciones de un mismo origen (motor, ciega, asistida)."""
    model_config = ConfigDict(extra="allow")

    descripciones: int
    conformes: int
    relaciones: int
    relaciones_validas: int
    tasa_relaciones_validas: float | None
    problemas: list[ProblemaFrecuente]


class ConteoAnotaciones(BaseModel):
    """Cuántas anotaciones ciegas y asistidas se enviaron, y por cuántas personas."""
    model_config = ConfigDict(extra="allow")

    ciegas: int
    asistidas: int
    evaluadores: int


class CondicionGlobal(BaseModel):
    """Una condición del criterio que vale para todos los tipos (conformidad asistida, rúbrica)."""
    model_config = ConfigDict(extra="allow")

    valor: float | dict | None
    exigido: float
    cumple: bool


class VeredictoTipo(BaseModel):
    """El criterio de comparabilidad aplicado a un tipo de entidad."""
    model_config = ConfigDict(extra="allow")

    tipo: str
    casos: int
    f_motor: float | None
    techo: float | None
    diferencia: float | None
    estado: str
    motivos: list[str]


class ComparabilidadOut(BaseModel):
    """Respuesta a la pregunta de investigación según el criterio fijado antes de iniciar."""
    model_config = ConfigDict(extra="allow")

    criterio: dict[str, float]
    condiciones: dict[str, CondicionGlobal]
    tipos: list[VeredictoTipo]
    comparables: list[str]
    no_comparables: list[str]
    sin_decidir: list[str]


class IntervaloF(BaseModel):
    """Intervalo de confianza del 95 % de la F, por remuestreo de documentos."""
    model_config = ConfigDict(extra="allow")

    documentos: int
    remuestreos: int
    inferior: float | None
    superior: float | None


class PruebaWilcoxon(BaseModel):
    """Prueba de rangos con signo de Wilcoxon de los tiempos pareados."""
    model_config = ConfigDict(extra="allow")

    n: int
    w_mas: float | None
    w_menos: float | None
    z: float | None
    p: float | None
    nota: str | None


class SupervisionOut(BaseModel):
    """Qué hizo la archivista con cada propuesta del motor en la condición asistida."""
    model_config = ConfigDict(extra="allow")

    por_tipo: dict[str, dict[str, int]]
    total: dict[str, int]
    propuestas: int
    pct_aceptadas: float | None
    pct_corregidas: float | None
    pct_rechazadas: float | None
    pct_agregadas: float | None


class ResumenErrores(BaseModel):
    """Clasificación de los desacuerdos con la taxonomía de errores y el acuerdo entre clasificadoras."""
    model_config = ConfigDict(extra="allow")

    desacuerdos: int
    clasificados: int
    pendientes_consenso: int
    sin_clasificar: int
    clasificadoras: int
    pares: int
    kappa: float | None
    distribucion: list[dict]
    por_clase: dict[str, int]


class Desacuerdo(BaseModel):
    """Una diferencia entre el motor y una referencia ciega."""
    model_config = ConfigDict(extra="allow")

    clave: str
    documento: str | None
    clase: str
    clase_nombre: str
    tipo: str
    motor: str | None
    archivista: str | None
    mia: str | None
    otra: str | None
    otra_clasifico: bool
    consenso: str | None
    requiere_consenso: bool


class DesacuerdosOut(BaseModel):
    """Los desacuerdos de una evaluación, con la clasificación de quien consulta."""
    model_config = ConfigDict(extra="allow")

    estado: str
    tipos_error: dict[str, str]
    clases: dict[str, str]
    resumen: ResumenErrores
    desacuerdos: list[Desacuerdo]


class ClasificadoOut(BaseModel):
    """Confirmación de una clasificación."""
    model_config = ConfigDict(extra="allow")

    clasificado: bool


class ResultadosOut(BaseModel):
    """Precisión, exhaustividad, F1, acuerdo, tiempos y rúbrica de la evaluación."""
    model_config = ConfigDict(extra="allow")

    evaluacion: EvaluacionOut
    umbral: float
    motores: list[MotorUsado]
    estricto: TablaMetricas
    flexible: TablaMetricas
    relaciones: ResultadoRelaciones
    conformidad: dict[str, ResumenConformidad]
    acuerdo_entre_archivistas: Metricas | None
    tiempos: dict[str, TiempoCondicion]
    rubrica: dict[str, RubricaCriterio]
    documentos: list[DocumentoResultado]
    anotaciones: ConteoAnotaciones
    comparabilidad: ComparabilidadOut
    intervalos: dict[str, IntervaloF]
    prueba_tiempos: PruebaWilcoxon
    supervision: SupervisionOut
    errores: ResumenErrores
    acuerdo_por_tipo: dict[str, Metricas]
    tiempos_por_documento: list[dict]
