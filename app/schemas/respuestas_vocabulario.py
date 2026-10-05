"""
Esquemas de respuesta del módulo de vocabularios y control de autoridad.

Solo documentan en OpenAPI lo que devuelven las rutas (se declaran con
`responses=`, no con `response_model=`): no filtran ni validan la salida.
Admiten claves adicionales para no atar la documentación a cada detalle.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class EntidadResumen(BaseModel):
    """Entidad del vocabulario tal como aparece en listados y detalles."""

    model_config = ConfigDict(extra="allow")

    id: str
    clase: str
    subtipo: str | None
    nombre: str
    estado: str
    conexiones: int
    fusionada_en: dict | None = None
    nivel_detalle: str | None = None
    version: str | None = None
    archivos: int | None = None
    acciones: dict[str, int] | None = None


class SugerenciaFusionOut(BaseModel):
    """Candidato a fusión pendiente de revisión, con sus dos entidades."""

    model_config = ConfigDict(extra="allow")

    id: str
    clase: str
    similitud: float
    motivo: str | None
    creada_en: str | None
    entidades: list[EntidadResumen]


class SerieEnlazada(BaseModel):
    """Serie o subserie del fondo que se puede enlazar con una función."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str | None
    nivel: str


class NodoFuncion(BaseModel):
    """Función o subfunción del árbol, con las series que produce."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    series: list[SerieEnlazada]
    especificos: list["NodoFuncion"]


class DocumentoConectado(BaseModel):
    """Descripción que cita la entidad."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str | None
    nivel: str


class EntidadAbsorbida(BaseModel):
    """Entidad que se fusionó en esta."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str


class EventoFusion(BaseModel):
    """Fusión registrada en la auditoría de la entidad."""

    model_config = ConfigDict(extra="allow")

    fecha: str
    por: str | None = None
    detalle: str | None = None
    relaciones_movidas: int | None = None
    origen: Any = None


class AgenteRelacionado(BaseModel):
    """El otro agente de una relación entre agentes."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    subtipo: str | None


class RelacionAgente(BaseModel):
    """Relación del agente con otro (subordinación, sucesión o asociación)."""

    model_config = ConfigDict(extra="allow")

    relacion_id: str
    tipo: str
    codigo_ric: str
    etiqueta: str
    uri_rico: str | None
    con: AgenteRelacionado | None


class ControlFicha(BaseModel):
    """Área de control del registro de autoridad."""

    model_config = ConfigDict(extra="allow")

    identificador_registro: str
    reglas: str | None = None
    nivel_detalle: str | None = None
    estado_elaboracion: str | None = None
    institucion_responsable: str | None = None
    lenguas: list = []
    escrituras: list = []
    notas_mantenimiento: str | None = None
    creada_en: str | None = None
    revisada_en: str | None = None


class FichaEntidad(BaseModel):
    """Ficha de la entidad según su clase (ISAAR-CPF, lugar, función, mandato)."""

    model_config = ConfigDict(extra="allow")

    campos: dict
    nombres: list[dict]
    vinculos: list[dict]
    clase_rico: str
    control: ControlFicha
    identificadores: list[dict] | None = None
    hitos: list[dict] | None = None
    existencia_legible: str | None = None
    falta_version: bool | None = None
    usos_tecnicos: Any = None
    contiene: list[dict] | None = None
    skos: dict | None = None
    actividades: list[dict] | None = None
    contexto: Any = None
    expedicion: Any = None


class DetalleEntidad(BaseModel):
    """Detalle de una entidad: documentos conectados, fusiones y ficha."""

    model_config = ConfigDict(extra="allow")

    entidad: EntidadResumen
    creada_en: str | None
    documentos: list[DocumentoConectado]
    documentos_historicos: list[DocumentoConectado]
    absorbidas: list[EntidadAbsorbida]
    historial: list[EventoFusion]
    relaciones_agente: list[RelacionAgente]
    ficha: FichaEntidad


class Coincidencia(BaseModel):
    """Entidad parecida al valor buscado, con su similitud."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    subtipo: str | None
    similitud: float
    conexiones: int
    forma: str | None = None


class DeteccionFusion(BaseModel):
    """Cuántos candidatos nuevos a fusión se encontraron."""

    model_config = ConfigDict(extra="allow")

    nuevas: int


class ResultadoFusion(BaseModel):
    """Resultado de una fusión: la que queda, la absorbida y las relaciones movidas."""

    model_config = ConfigDict(extra="allow")

    definitiva: str
    absorbida: str
    relaciones_movidas: int


class SugerenciaDescartada(BaseModel):
    """Confirmación de que la sugerencia se descartó."""

    model_config = ConfigDict(extra="allow")

    estado: str
