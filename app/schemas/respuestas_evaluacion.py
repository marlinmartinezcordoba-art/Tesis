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
    """Título, alcance y entidades de una descripción o de una propuesta del motor."""
    model_config = ConfigDict(extra="allow")

    titulo: str | None = None
    alcance: str | None = None
    entidades: list[dict[str, Any]] = []


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
    referencias_ciegas: int
    f1_flexible: float | None
    descrito_durante_la_evaluacion: bool


class ConteoAnotaciones(BaseModel):
    """Cuántas anotaciones ciegas y asistidas se enviaron, y por cuántas personas."""
    model_config = ConfigDict(extra="allow")

    ciegas: int
    asistidas: int
    evaluadores: int


class ResultadosOut(BaseModel):
    """Precisión, exhaustividad, F1, acuerdo, tiempos y rúbrica de la evaluación."""
    model_config = ConfigDict(extra="allow")

    evaluacion: EvaluacionOut
    umbral: float
    motores: list[MotorUsado]
    estricto: TablaMetricas
    flexible: TablaMetricas
    acuerdo_entre_archivistas: Metricas | None
    tiempos: dict[str, TiempoCondicion]
    rubrica: dict[str, RubricaCriterio]
    documentos: list[DocumentoResultado]
    anotaciones: ConteoAnotaciones
