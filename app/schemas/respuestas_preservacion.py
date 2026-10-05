"""
Esquemas de respuesta de preservación y de exportación RiC-O (solo documentación OpenAPI).

Se declaran en `responses=` de cada ruta, nunca como `response_model`: no
filtran ni validan lo que devuelve el servidor. Las fechas viajan como texto
ISO 8601.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


# --- Piezas comunes -----------------------------------------------------------------------------


class MecanismoPreservacion(BaseModel):
    """Mecanismo (programa) que actuó, con su versión."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    version: str | None


class MigaContexto(BaseModel):
    """Un nivel del camino hasta la descripción a la que pertenece el archivo."""

    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    titulo: str


class InstanciacionBreve(BaseModel):
    """Datos mínimos de una instanciación."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    formato: str | None
    puid: str | None


class DerechosDeclarados(BaseModel):
    """Declaración de derechos de una instanciación o de una descripción."""

    model_config = ConfigDict(extra="allow")

    id: str
    entidad_tipo: str
    entidad_id: str
    nivel: str | None
    titulo: str | None
    base: str
    base_nombre: str
    acceso: str
    acceso_nombre: str
    reproduccion: str
    reproduccion_nombre: str
    fundamento: str
    nota: str | None
    vigente_hasta: str | None
    vencida: bool
    creada_en: str


class DerechosAplicables(DerechosDeclarados):
    """Declaración de derechos que rige el archivo, propia o heredada."""

    heredada: bool
    restringe: bool


# --- Panel y eventos ----------------------------------------------------------------------------


class ResumenPanelPreservacion(BaseModel):
    """Conteo de instanciaciones del fondo por estado de preservación."""

    model_config = ConfigDict(extra="allow")

    total: int
    alerta_integridad: int
    alerta_segunda_copia: int
    riesgo_obsolescencia: int
    buen_estado: int


class AtencionPreservacion(BaseModel):
    """Alerta pendiente sobre una instanciación que requiere atención."""

    model_config = ConfigDict(extra="allow")

    alerta_id: str
    tipo: str
    severidad: str
    mensaje: str
    instanciacion: InstanciacionBreve
    contexto: list[MigaContexto]


class PanelPreservacion(BaseModel):
    """Panel de preservación del fondo: resumen y lo que requiere atención."""

    model_config = ConfigDict(extra="allow")

    resumen: ResumenPanelPreservacion
    atencion: list[AtencionPreservacion]
    frecuencia_dias: int
    ultima_verificacion: Any = None
    sin_segunda_copia: int


class EventoVerificacion(BaseModel):
    """Última ronda de verificación de integridad del fondo."""

    model_config = ConfigDict(extra="allow")

    fecha: str
    resultados: dict[str, int]


class EventoMigracion(BaseModel):
    """Última migración de formato del fondo."""

    model_config = ConfigDict(extra="allow")

    fecha: str
    estado: str
    destino: str
    archivo: str


class EventoRestauracion(BaseModel):
    """Última restauración desde la segunda copia en el fondo."""

    model_config = ConfigDict(extra="allow")

    fecha: str
    estado_previo: str
    archivo: str


class EventoSimulacro(BaseModel):
    """Último simulacro de restauración de la base de datos."""

    model_config = ConfigDict(extra="allow")

    fecha: str
    estado: str | None
    respaldo_en: str
    tablas: Any = None
    descargado_en: str | None


class EventosRecientes(BaseModel):
    """Línea de tiempo de preservación del fondo."""

    model_config = ConfigDict(extra="allow")

    verificacion: EventoVerificacion | None
    migracion: EventoMigracion | None
    restauracion: EventoRestauracion | None
    simulacro_base_de_datos: EventoSimulacro | None


# --- Respaldos de la base de datos --------------------------------------------------------------


class RespaldoBaseDatosOut(BaseModel):
    """Respaldo de la base de datos y su simulacro de restauración."""

    model_config = ConfigDict(extra="allow")

    id: str
    iniciado_en: str
    terminado_en: str | None
    origen: str
    estado: str
    archivo: str | None
    tamano_bytes: int | None
    huella: str | None
    error: str | None
    tablas: Any = None
    simulacro_en: str | None
    simulacro_estado: str | None
    simulacro_diferencias: Any = None
    simulacro_error: Any = None
    descargado_en: str | None
    depurado_en: str | None
    destino: str


class ListaRespaldos(BaseModel):
    """Respaldos recientes de la base de datos y su programación."""

    model_config = ConfigDict(extra="allow")

    respaldos: list[RespaldoBaseDatosOut]
    frecuencia_horas: Any = None
    dias_copia_externa: Any = None


# --- Recuperación ante desastres ----------------------------------------------------------------


class PaqueteRecuperacionOut(BaseModel):
    """Paquete de recuperación ante desastres y su simulacro integral."""

    model_config = ConfigDict(extra="allow")

    id: str
    creado_en: str
    origen: str
    estado: str
    tamano_bytes: int | None
    huella: str | None
    archivos: int | None
    bytes_archivos: int | None
    error: str | None
    simulacro_en: str | None
    simulacro_estado: str | None
    simulacro_segundos: int | None
    simulacro_pasos: Any = None
    archivos_verificados: Any = None
    simulacro_error: Any = None
    ausentes: list[str]
    descargado_en: str | None
    depurado_en: str | None


class ObjetivosRecuperacion(BaseModel):
    """Objetivos de punto (RPO) y tiempo (RTO) de recuperación."""

    model_config = ConfigDict(extra="allow")

    rpo_horas: int
    rto_horas: int
    aprovisionar_horas: float


class EscenarioRecuperacion(BaseModel):
    """Escenario de desastre con lo medido frente a los objetivos."""

    model_config = ConfigDict(extra="allow")

    clave: str
    escenario: str
    mecanismo: str
    rpo: str
    rto: str
    rpo_actual_horas: float | None
    rto_medido_horas: float | None
    cumple: bool


class EstadoRecuperacion(BaseModel):
    """Estado de la recuperación ante desastres por escenario."""

    model_config = ConfigDict(extra="allow")

    objetivos: ObjetivosRecuperacion
    escenarios: list[EscenarioRecuperacion]
    ultimo_paquete: PaqueteRecuperacionOut | None
    paquetes: list[PaqueteRecuperacionOut]
    frecuencia_dias: int


# --- Ficha técnica de la instanciación ----------------------------------------------------------


class FormatoInstanciacion(BaseModel):
    """Formato identificado del archivo y cómo se identificó."""

    model_config = ConfigDict(extra="allow")

    puid: str | None
    nombre: str | None
    version: str | None
    mime: str | None
    identificado: bool
    herramienta: str | None
    mecanismo: MecanismoPreservacion | None
    base: str | None


class RiesgoFormato(BaseModel):
    """Riesgo de obsolescencia del formato y su recomendación."""

    model_config = ConfigDict(extra="allow")

    nivel: str
    razon: str
    recomendacion: str | None
    destino_sugerido: str | None
    mitigado_por: dict | None


class MigradaDesde(BaseModel):
    """Cómo se produjo este archivo cuando salió de una migración."""

    model_config = ConfigDict(extra="allow")

    herramienta: str | None
    modo: str
    mecanismo: MecanismoPreservacion | None


class VerificacionHistorial(BaseModel):
    """Una verificación de integridad del archivo."""

    model_config = ConfigDict(extra="allow")

    fecha: str
    resultado: str
    origen: str
    segunda_copia: str | None
    por: str | None


class CopiaPrimaria(BaseModel):
    """Dónde está la copia primaria del archivo."""

    model_config = ConfigDict(extra="allow")

    ubicacion: str
    ruta: str | None


class SegundaCopiaOut(BaseModel):
    """Estado de la segunda copia del archivo (o «sin_copia»)."""

    model_config = ConfigDict(extra="allow")

    estado: str
    id: str | None = None
    ubicacion: str | None = None
    ruta: str | None = None
    huella: str | None = None
    motivo: str | None = None
    creada_en: str | None = None
    ultima_verificacion_en: str | None = None


class Almacenamiento(BaseModel):
    """Copia primaria y segunda copia del archivo."""

    model_config = ConfigDict(extra="allow")

    primaria: CopiaPrimaria
    segunda_copia: SegundaCopiaOut


class RestauracionHistorial(BaseModel):
    """Una restauración del archivo desde la segunda copia."""

    model_config = ConfigDict(extra="allow")

    fecha: str
    por: str | None
    estado_previo: str
    cuarentena: str | None


class AccionesPreservacion(BaseModel):
    """Acciones de preservación disponibles para el archivo."""

    model_config = ConfigDict(extra="allow")

    restaurar: bool
    reponer_segunda_copia: bool


class MigracionHistorial(BaseModel):
    """Una migración de formato aprobada para el archivo."""

    model_config = ConfigDict(extra="allow")

    id: str
    destino: str
    destino_nombre: str
    modo: str
    estado: str
    herramienta: str | None
    mensaje: str | None
    mecanismo: MecanismoPreservacion | None
    parametros: str | None
    aprobada_por: str | None
    aprobada_en: str
    terminada_en: str | None
    resultado: InstanciacionBreve | None


class DestinoMigracion(BaseModel):
    """Formato al que se puede migrar el archivo."""

    model_config = ConfigDict(extra="allow")

    clave: str
    nombre: str
    automatica: bool
    conversor: str | None


class DetalleInstanciacion(BaseModel):
    """Ficha técnica de preservación de una instanciación."""

    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    fondo_id: str
    formato: FormatoInstanciacion
    tamano_bytes: int | None
    paginas: int | None
    huella: str | None
    algoritmo_huella: str
    cargado_en: str
    estado_integridad: str
    ultima_verificacion_en: str | None
    riesgo: RiesgoFormato
    contexto: list[MigaContexto]
    derivada_de: InstanciacionBreve | None
    migrada_desde: MigradaDesde | None
    verificaciones: list[VerificacionHistorial]
    almacenamiento: Almacenamiento
    restauraciones: list[RestauracionHistorial]
    acciones: AccionesPreservacion
    derechos: DerechosAplicables | None
    aplicacion_creadora: str | None
    migraciones: list[MigracionHistorial]
    destinos: list[DestinoMigracion]


class ComprobacionTecnicaOut(BaseModel):
    """Última comprobación de antivirus o de validación de formato."""

    model_config = ConfigDict(extra="allow")

    tipo: str
    herramienta: str
    resultado: str
    perfil: str | None
    resumen: str | None
    detalle: Any = None
    origen: str
    realizada_en: str


class AreaNdsa(BaseModel):
    """Nivel NDSA alcanzado en un área y lo que falta para el siguiente."""

    model_config = ConfigDict(extra="allow")

    area: str
    nivel: int
    requisitos: list[list[dict]]
    falta_para_el_siguiente: list[str]


class NivelesNdsa(BaseModel):
    """Niveles NDSA 2.0 del sistema por área."""

    model_config = ConfigDict(extra="allow")

    version: str
    regla: str
    areas: list[AreaNdsa]


class ResultadoVerificacion(BaseModel):
    """Resultado de verificar la integridad del archivo ahora."""

    model_config = ConfigDict(extra="allow")

    resultado: str
    fecha: str
    huella_registrada: str | None
    huella_calculada: str | None
    segunda_copia: str | None
    huella_segunda_copia: str | None


class MigracionOut(BaseModel):
    """Migración de formato aprobada o terminada."""

    model_config = ConfigDict(extra="allow")

    id: str
    estado: str
    modo: str
    destino: str
    destino_nombre: str
    mensaje: str | None
    herramienta: str | None
    mecanismo: MecanismoPreservacion | None
    parametros: str | None
    nueva_instanciacion: DetalleInstanciacion | None


# --- Configuración ------------------------------------------------------------------------------


class FormatoSoportado(BaseModel):
    """Fila de la tabla de formatos que se migran de forma automática."""

    model_config = ConfigDict(extra="allow")

    id: str
    origen: str
    origen_mime: list[str]
    destino: str
    conversor: str
    activo: bool


class ConversorDisponible(BaseModel):
    """Programa de conversión que conoce el sistema."""

    model_config = ConfigDict(extra="allow")

    clave: str
    nombre: str
    destino: str


class DestinoDisponible(BaseModel):
    """Formato de conservación que conoce el sistema."""

    model_config = ConfigDict(extra="allow")

    clave: str
    nombre: str


class UbicacionSegundaCopia(BaseModel):
    """Lugar posible para la segunda copia y su estado."""

    model_config = ConfigDict(extra="allow")

    ruta: str
    existe: bool
    escribible: bool
    libre_bytes: int | None
    mismo_disco_que_primaria: bool


class ConfiguracionSegundaCopia(BaseModel):
    """Dónde se guarda la segunda copia y cuántos archivos faltan."""

    model_config = ConfigDict(extra="allow")

    actual: str | None
    primaria: str
    ubicaciones: list[UbicacionSegundaCopia]
    pendientes: int


class ConfiguracionPreservacion(BaseModel):
    """Configuración de preservación: frecuencia, formatos y segunda copia."""

    model_config = ConfigDict(extra="allow")

    frecuencia_dias: int
    formatos: list[FormatoSoportado]
    conversores: list[ConversorDisponible]
    destinos: list[DestinoDisponible]
    herramientas: dict[str, bool]
    segunda_copia: ConfiguracionSegundaCopia


# --- Exportación RiC-O --------------------------------------------------------------------------


class ConformidadOwl(BaseModel):
    """Resultado de la verificación contra el OWL oficial de RiC-O."""

    model_config = ConfigDict(extra="allow")

    conforme: bool
    problemas: list[str]


class ConformidadShacl(BaseModel):
    """Resultado de la validación contra el perfil SHACL del sistema."""

    model_config = ConfigDict(extra="allow")

    conforme: bool
    resultados: list[dict]
    perfil: str
    formas: int


class ConformidadMapeo(BaseModel):
    """Problemas del mapeo del sistema frente al OWL."""

    model_config = ConfigDict(extra="allow")

    problemas: list[str]


class FondoConformidad(BaseModel):
    """Fondo exportado."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str


class ReporteConformidad(BaseModel):
    """Reporte de conformidad de la exportación del fondo con RiC-O 1.1."""

    model_config = ConfigDict(extra="allow")

    conforme: bool
    ontologia: str
    owl: ConformidadOwl
    shacl: ConformidadShacl
    mapeo: ConformidadMapeo
    sin_propiedad: dict[str, str]
    tripletas: int
    por_clase: dict[str, int]
    omitidas: dict[str, int]
    fondo: FondoConformidad
    uri_fondo: str
    uris_publicas: bool
