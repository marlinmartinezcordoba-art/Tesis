"""
Esquemas de respuesta (solo documentación OpenAPI) de la evaluación del rendimiento del motor con
la medida F1.

No se usan como response_model: describen lo que ya devuelven las rutas, sin filtrar ni validar la
salida. Cada modelo admite campos adicionales.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Abierto(BaseModel):
    model_config = ConfigDict(extra="allow")


class EvaluacionOut(_Abierto):
    """Evaluación con su estado, sus conjuntos y sus umbrales."""
    id: str
    nombre: str
    protocolo: str | None
    estado: str
    creada_en: str
    iniciada_en: str | None
    cerrada_en: str | None
    documentos: int
    desarrollo: int
    prueba: int
    semilla: int | None
    criterio: dict[str, float]
    version_congelada: dict[str, Any] | None


class DocumentoOut(_Abierto):
    instanciacion_id: str
    nombre: str
    anio: str
    conjunto: str | None
    publicado: bool


class SorteoOut(_Abierto):
    semilla: int
    desarrollo: int
    prueba: int
    estratos: dict[str, int]


class Intervalo(_Abierto):
    inferior: float | None
    superior: float | None
    remuestreos: int


class MedidaDictamen(_Abierto):
    umbral: float | None
    valor: float | None
    limite_inferior: float | None
    cumple: bool | None


class ResultadosOut(_Abierto):
    """Medidas globales (sin textos libres) y por tipo, intervalos del 95 %, dictamen frente a los
    umbrales, acuerdo entre validadoras y causas de error."""
    metricas: dict[str, Any]
    dictamen: dict[str, Any]
    criterio: dict[str, float]
    acuerdo: dict[str, Any]
    causas: list[dict[str, Any]]
    documentos: list[dict[str, Any]]
    decisiones: int
    avisos: list[str]
    version_congelada: dict[str, Any] | None


class PropuestaControl(_Abierto):
    evento_id: int
    tipo: str
    tipo_nombre: str
    propuesto: str | None
    confianza: float | None
    mi_decision: str | None


class ControlOut(_Abierto):
    documento: dict[str, Any]
    propuestas: list[PropuestaControl]


class ErrorOut(_Abierto):
    evento_id: int
    documento: str | None
    tipo: str
    tipo_nombre: str
    decision: str
    propuesto: str | None
    final: str | None
    causa: str | None
    nota: str | None


class HechoOut(_Abierto):
    ok: bool


class AutomaticaOut(_Abierto):
    """La evaluación que calcula cada descripción publicada: las revisadas una a una (con dictamen) y todas."""
    revisadas_una_a_una: dict[str, Any]
    todas: dict[str, Any]
    criterio: dict[str, Any]
    documentos: list[dict[str, Any]]
    versiones: list[dict[str, Any]]
    decisiones: int
    avisos: list[str]
