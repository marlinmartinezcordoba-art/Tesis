"""El recorrido de un documento por los seis pasos del mapa de flujo:
ingesta → preproceso → motor de análisis → modelado de relaciones →
revisión archivística → catálogo. Aquí se calcula en qué paso está cada
documento (Record) a partir de datos reales, para que cada pantalla y el
panel de indicadores muestren lo mismo."""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Max, Min, Q

from . import tipos
from .models import Instantiation, PropuestaRiC, Record, RelacionRiC

_MODELO_A_RIC_ID = {v: k for k, v in tipos.RIC_ID_A_MODELO_NOMBRE.items()}

SIN_TEXTO = "sin_texto"
SIN_ANALIZAR = "sin_analizar"
EN_ANALISIS = "en_analisis"
EN_REVISION = "en_revision"
PUBLICADO = "publicado"

ETIQUETAS = {
    SIN_TEXTO: "Pendiente de preprocesamiento",
    SIN_ANALIZAR: "Listo para el motor de análisis",
    EN_ANALISIS: "En análisis (propuestas por decidir)",
    EN_REVISION: "En revisión archivística",
    PUBLICADO: "Publicado en el catálogo",
}
ESTADOS_VALIDADOS = (RelacionRiC.Estado.ACEPTADA, RelacionRiC.Estado.MODIFICADA)


def _ct(modelo):
    return ContentType.objects.get_for_model(modelo)


def propuestas_de(record):
    return PropuestaRiC.objects.filter(origen_content_type=_ct(Record), origen_object_id=record.pk)


def pendientes_de(record):
    return propuestas_de(record).filter(estado=PropuestaRiC.Estado.PENDIENTE)


def relaciones_de(record, solo_validadas=True):
    """Las relaciones del documento en ambos sentidos: las que salen de él
    (R027 has creator -> agente) y las que llegan a él desde una entidad
    (R080 is creation date of: fecha -> documento, como lo define RiC-CM)."""
    ct = _ct(Record)
    qs = RelacionRiC.objects.filter(
        Q(origen_content_type=ct, origen_object_id=record.pk) | Q(destino_content_type=ct, destino_object_id=record.pk)
    )
    if solo_validadas:
        qs = qs.filter(estado__in=ESTADOS_VALIDADOS)
    return qs.select_related("origen_content_type", "destino_content_type", "validado_por", "evidencia")


def otro_lado(relacion, record):
    """La entidad con la que `record` se relaciona, esté el documento como
    origen o como destino de la relación."""
    es_origen = relacion.origen_content_type_id == _ct(Record).pk and relacion.origen_object_id == record.pk
    return relacion.destino if es_origen else relacion.origen


def series_trd_de(record):
    """Las series de la TRD que aplican a este documento: las actividades
    (funciones) con las que quedó relacionado y que tienen su Mandato con
    retención y disposición (especificación v3). Es de ahí, y no de la
    forma documental, de donde la revisión lee cuánto se conserva."""
    from .models import Activity

    series = []
    for rel in relaciones_de(record):
        otro = otro_lado(rel, record)
        if isinstance(otro, Activity) and otro.mandato_id and otro.mandato.es_serie_trd:
            if all(s["actividad"].pk != otro.pk for s in series):
                series.append({"actividad": otro, "mandato": otro.mandato, "relacion": rel})
    return series


def instanciacion_principal(record):
    """La instanciación con más texto extraído (misma regla que el motor de
    análisis usa para elegir qué texto leer)."""
    instanciaciones = list(record.instanciaciones.all())
    if not instanciaciones:
        return None
    return max(instanciaciones, key=lambda i: len(i.texto_extraido))


_TIPOS_AGENTE = {"E07", "E08", "E09", "E10", "E11", "E12", "E13"}


def clases_faltantes(record):
    """CC-02 (completitud de las clases mínimas): toda descripción debe
    tener al menos una forma documental, un agente y una fecha — propuestos
    o ya confirmados. Devuelve las que faltan; vacío si está completa."""
    faltan = []
    if not record.forma_documental_id and not record.tipo_forma_documental:
        faltan.append("forma documental")
    tipos_propuestos = set(propuestas_de(record).exclude(estado=PropuestaRiC.Estado.RECHAZADA).values_list("entidad_tipo", flat=True))
    tipos_confirmados = set()
    for rel in relaciones_de(record):
        otro = otro_lado(rel, record)
        if otro is not None:
            nombre = type(otro).__name__
            tipos_confirmados.add(_MODELO_A_RIC_ID.get(nombre, ""))
    presentes = tipos_propuestos | tipos_confirmados
    if not presentes & _TIPOS_AGENTE:
        faltan.append("agente")
    if "E18" not in presentes:
        faltan.append("fecha")
    return faltan


def estado_documento(record):
    if record.publicado:
        return PUBLICADO
    if pendientes_de(record).exists():
        return EN_ANALISIS
    if relaciones_de(record).exists():
        return EN_REVISION
    if Instantiation.objects.filter(record_resource=record, paginas__isnull=False).exists():
        return SIN_ANALIZAR
    return SIN_TEXTO


def documentos_con_estado(queryset=None):
    filas = []
    for record in (queryset if queryset is not None else Record.objects.all()).order_by("-fecha_registro"):
        estado = estado_documento(record)
        filas.append({"record": record, "estado": estado, "etiqueta": ETIQUETAS[estado]})
    return filas


def descripcion_en(record, momento):
    """RF-M7-03: cómo estaba la descripción del documento (sus relaciones)
    en un instante anterior. Cada RelacionRiC guarda en VersionRiC una
    fotografía de cómo estaba ANTES de cada cambio, así que el estado en
    `momento` es: la primera fotografía tomada después de ese instante si
    la hay, o el registro actual si nada cambió desde entonces."""
    from .models import VersionRiC

    ct_relacion = _ct(RelacionRiC)
    filas = []
    for rel in relaciones_de(record, solo_validadas=False).filter(fecha_creacion__lte=momento).order_by("fecha_creacion"):
        version = (
            VersionRiC.objects.filter(content_type=ct_relacion, object_id=rel.pk, fecha__gt=momento)
            .order_by("fecha").first()
        )
        datos = version.datos_anteriores if version else None
        filas.append({
            "relacion": rel,
            "relacion_id": datos["relacion_id"] if datos else rel.relacion_id,
            "estado": datos["estado"] if datos else rel.estado,
            "destino": otro_lado(rel, record),
            "reconstruida": version is not None,
        })
    return filas


def pendientes_por_documento():
    """{record_pk: {"total": n, "desde": fecha de la propuesta pendiente
    más antigua}} — lo que alimenta la alerta de RF-M10-04."""
    filas = (
        PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE, origen_content_type=_ct(Record))
        .values("origen_object_id")
        .annotate(desde=Min("fecha_creacion"), ultima=Max("fecha_creacion"))
    )
    return {f["origen_object_id"]: f for f in filas}
