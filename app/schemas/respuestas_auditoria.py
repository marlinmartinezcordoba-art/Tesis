"""
Esquemas de respuesta (solo documentación OpenAPI) del módulo de auditoría
y del segundo factor de la cuenta propia.

No se usan como response_model: describen lo que ya devuelven las rutas,
sin filtrar ni validar la salida. Cada modelo admite campos adicionales.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


# --- Trazabilidad -------------------------------------------------------------------------------


class AccionDisponible(BaseModel):
    """Tipo de acción registrada que sirve para filtrar la trazabilidad."""
    model_config = ConfigDict(extra="allow")

    accion: str
    modulo: str
    etiqueta: str


class PropiedadRicO(BaseModel):
    """Propiedad de RiC-O que representa un cambio o una relación."""
    model_config = ConfigDict(extra="allow")

    nombre: str | None = None
    estado: str | None = None
    codigo_cm: str | None = None


class CambioEvento(BaseModel):
    """Un campo con su valor antes y después del evento."""
    model_config = ConfigDict(extra="allow")

    campo: str
    antes: Any = None
    despues: Any = None
    propiedad_rico: PropiedadRicO | None = None


class EventoAuditoria(BaseModel):
    """Un evento del registro de auditoría, con sus cambios."""
    model_config = ConfigDict(extra="allow")

    id: int
    fecha: str
    usuario_id: str | None
    usuario: str | None
    modulo: str
    accion: str
    etiqueta: str
    entidad_tipo: str | None
    entidad_id: str | None
    detalle: str | None
    propiedad_rico: PropiedadRicO | None
    cambios: list[CambioEvento]


class TrazabilidadPropiaOut(BaseModel):
    """Página de las acciones propias, con el total y el cursor siguiente."""
    model_config = ConfigDict(extra="allow")

    eventos: list[EventoAuditoria]
    total: int
    siguiente: int | None


class TrazabilidadEntidadOut(BaseModel):
    """Historial de auditoría de una entidad."""
    model_config = ConfigDict(extra="allow")

    entidad_tipo: str
    entidad_id: str
    solo_propias: bool
    eventos: list[EventoAuditoria]


# --- Panel consolidado ----------------------------------------------------------------------------


class SemanaConsolidado(BaseModel):
    """Límites de la semana consultada y enlaces a la anterior y la siguiente."""
    model_config = ConfigDict(extra="allow")

    lunes: str
    domingo: str
    anterior: str
    siguiente: str | None
    zona_horaria: str


class FilaConsolidado(BaseModel):
    """Días, horas conectadas y acciones de una persona en la semana."""
    model_config = ConfigDict(extra="allow")

    usuario_id: str
    nombre: str
    rol: str
    rol_nombre: str | None
    activo: bool
    dias_trabajados: int
    dias_habiles_trabajados: int
    dias_fin_de_semana: int
    dias_habiles: int
    segundos_conectado: int
    sesiones: int
    en_curso: bool
    acciones: dict[str, int]


class RevisionSemana(BaseModel):
    """Constancia de que alguien revisó el registro de la semana."""
    model_config = ConfigDict(extra="allow")

    fecha: str
    por: str | None
    nota: str | None


class ConsolidadoOut(BaseModel):
    """Panel semanal por persona, con las constancias de revisión."""
    model_config = ConfigDict(extra="allow")

    semana: SemanaConsolidado
    filas: list[FilaConsolidado]
    revisiones: list[RevisionSemana]


class RevisionesOut(BaseModel):
    """Constancias de revisión de la semana tras registrar una nueva."""
    model_config = ConfigDict(extra="allow")

    revisiones: list[RevisionSemana]


class UsuarioBreve(BaseModel):
    """Identificador y nombre de una persona."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str


class SesionDesglose(BaseModel):
    """Una sesión de trabajo de la persona y las acciones hechas en ella."""
    model_config = ConfigDict(extra="allow")

    sesion_id: str
    inicio: str
    fin: str
    en_curso: bool
    motivo: str | None
    segundos: int
    acciones: dict[str, int]


class DesgloseOut(BaseModel):
    """Desglose sesión por sesión de una persona en la semana."""
    model_config = ConfigDict(extra="allow")

    usuario: UsuarioBreve
    semana: str
    sesiones: list[SesionDesglose]
    segundos_conectado: int


# --- Cadena de huellas ----------------------------------------------------------------------------


class SelloCadena(BaseModel):
    """Último eslabón de la cadena de huellas: el sello que se guarda fuera."""
    model_config = ConfigDict(extra="allow")

    orden: int | None
    huella: str | None
    fecha: str | None


class CadenaOut(BaseModel):
    """Resultado de verificar la cadena de huellas del registro."""
    model_config = ConfigDict(extra="allow")

    integra: bool
    eventos: int
    roto_en: int | None
    sin_encadenar: int
    sello: SelloCadena


# --- Decisiones de IA -----------------------------------------------------------------------------


class ConteosDecisiones(BaseModel):
    """Conteos y porcentajes de las decisiones frente a las propuestas del motor."""
    model_config = ConfigDict(extra="allow")

    aceptada: int
    corregida: int
    rechazada: int
    agregada: int
    propuestas: int
    pct_aceptadas: float | None
    pct_corregidas: float | None
    pct_rechazadas: float | None
    pct_cobertura: float | None


class ConteosPorTipo(ConteosDecisiones):
    """Conteos de las decisiones de un tipo de dato."""

    tipo_nombre: str


class DocumentoDecision(BaseModel):
    """Documento sobre el que se tomó la decisión."""
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    titulo: str | None = None


class FilaDecision(BaseModel):
    """Una propuesta del motor frente a lo que quedó confirmado."""
    model_config = ConfigDict(extra="allow")

    id: int
    fecha: str
    documento: DocumentoDecision
    tipo: str | None = None
    tipo_nombre: str | None = None
    clase_rico: str | None = None
    propiedad_rico: PropiedadRicO | None = None
    decision: str | None = None
    propuesto: str | None = None
    final: str | None = None
    confianza: Any = None
    modelo: str | None = None
    version_prompt: str | None = None
    version_etiqueta: str | None = None
    por: str | None = None


class DecisionesIAOut(BaseModel):
    """Decisiones de validación asistida, con sus conteos generales y por tipo."""
    model_config = ConfigDict(extra="allow")

    resumen: ConteosDecisiones
    por_tipo: list[ConteosPorTipo]
    modelos: list[str]
    versiones_prompt: list[str]
    etiquetas_version: dict[str, str]
    total: int
    filas: list[FilaDecision]


# --- Hallazgos y versiones de la instrucción ------------------------------------------------------


class HallazgoOut(BaseModel):
    """Hallazgo de conformidad con RiC."""
    model_config = ConfigDict(extra="allow")

    id: str
    numero: int
    referencia: str | None
    titulo: str
    descripcion: str
    componentes: list[str]
    estado: str
    estado_nombre: str
    abierto_en: str
    cerrado_en: str | None
    accion: str | None
    creado_en: str
    actualizado_en: str | None


class HallazgosOut(BaseModel):
    """Hallazgos filtrados, con el conteo por estado total y filtrado."""
    model_config = ConfigDict(extra="allow")

    hallazgos: list[HallazgoOut]
    conteo: dict[str, int]
    conteo_filtrado: dict[str, int]


class VersionPromptOut(BaseModel):
    """Versión de la instrucción del motor, con su etiqueta legible si la tiene."""
    model_config = ConfigDict(extra="allow")

    version: str
    decisiones: int
    primera: str | None
    ultima: str | None
    etiqueta: str | None
    vigente: bool


# --- Segundo factor de la cuenta propia -----------------------------------------------------------


class EstadoDobleFactorOut(BaseModel):
    """Si la cuenta usa segundo factor, desde cuándo y si su rol lo exige."""
    model_config = ConfigDict(extra="allow")

    activo: bool
    activado_en: str | None
    requerido: bool
    codigos_respaldo: int


class ClaveDobleFactorOut(BaseModel):
    """Clave y enlace otpauth para la aplicación de autenticación."""
    model_config = ConfigDict(extra="allow")

    clave: str
    uri: str


class CodigosRespaldoOut(BaseModel):
    """Códigos de respaldo que se entregan una sola vez al activar el segundo factor."""
    model_config = ConfigDict(extra="allow")

    codigos_respaldo: list[str]
