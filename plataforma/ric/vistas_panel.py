"""M10 · Panel de indicadores (/panel): volumen ingestado por periodo
(RF-M10-01), porcentaje de documentos con descripción validada (RF-M10-02),
tiempo promedio de revisión (RF-M10-03) y alerta sobre documentos
pendientes que superan el límite configurable (RF-M10-04). Todo son datos
reales del sistema — cuando falta el dato, se dice, nunca se inventa."""

import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncDate, TruncWeek
from django.shortcuts import render
from django.utils import timezone

from . import valoracion, auditoria, flujo, roles
from .models import ConfiguracionSistema, EventoRiC, Instantiation, PropuestaRiC, Record, RelacionRiC

_COLORES_DISTRIBUCION = ["#c08a3e", "#2f7d4f", "#a9660a", "#7046d9", "#c0392b", "#1f6f8b"]


def _distribucion_entidades():
    """Cuenta cada tabla concreta de más alto nivel (Agent, no sus subtipos):
    con herencia multitabla, sumar Person+Group+Family+... contaría cada
    agente varias veces; `Agent.objects.count()` es exacto."""
    from .models import Activity, Agent, Date, Place

    filas = [
        {"tipo": "Record", "total": Record.objects.count()},
        {"tipo": "Agent", "total": Agent.objects.count()},
        {"tipo": "Activity", "total": Activity.objects.count()},
        {"tipo": "Instantiation", "total": Instantiation.objects.count()},
        {"tipo": "Date", "total": Date.objects.count()},
        {"tipo": "Place", "total": Place.objects.count()},
    ]
    for fila, color in zip(filas, _COLORES_DISTRIBUCION):
        fila["color"] = color
    return filas


def _gradiente_conico(distribucion):
    total = sum(f["total"] for f in distribucion)
    if not total:
        return "#e6e3dc 0% 100%"
    partes, acumulado = [], 0
    for f in distribucion:
        if not f["total"]:
            continue
        inicio = acumulado / total * 100
        acumulado += f["total"]
        partes.append(f"{f['color']} {inicio:.2f}% {acumulado / total * 100:.2f}%")
    return ", ".join(partes)


def _serie(conteos, claves, etiqueta):
    serie = [{"etiqueta": etiqueta(c), "total": conteos.get(c, 0)} for c in claves]
    maximo = max((d["total"] for d in serie), default=0) or 1
    for d in serie:
        d["porcentaje"] = round(d["total"] / maximo * 100)
    return serie


def _actividad_ultimos_dias(dias=14):
    hoy = timezone.localdate()
    desde = hoy - datetime.timedelta(days=dias - 1)
    conteos = dict(
        Instantiation.objects.filter(fecha_registro__date__gte=desde)
        .annotate(dia=TruncDate("fecha_registro")).values("dia")
        .annotate(total=Count("pk")).values_list("dia", "total")
    )
    claves = [desde + datetime.timedelta(days=i) for i in range(dias)]
    return _serie(conteos, claves, lambda d: d.strftime("%d/%m"))


@login_required
def panel(request):
    """Cifras vigentes para el periodo elegido (selector superior); cada
    cifra enlaza a la lista de documentos que la compone (historia 10)."""
    from . import indicadores

    config = ConfiguracionSistema.actual()
    periodo = indicadores.periodo_valido(request.GET.get("periodo", ""))
    alertas = indicadores.atrasados(config.dias_limite_revision)
    contexto = {
        "periodo": periodo,
        "periodos": indicadores.PERIODOS,
        "periodo_nombre": dict(indicadores.PERIODOS)[periodo],
        "ingestados": indicadores.ingestados(periodo).count(),
        "archivos_periodo": Instantiation.objects.filter(**({"fecha_registro__gte": indicadores.desde(periodo)} if indicadores.desde(periodo) else {})).count(),
        "validado": indicadores.porcentaje_validado(periodo),
        "tiempos": indicadores.tiempos_de_revision(periodo),
        "grafica": indicadores.serie_ingesta(periodo),
        "pendientes_revision": len(indicadores.esperando_revision()),
        "alertas": alertas,
        "total_instanciaciones": Instantiation.objects.count(),
        "relaciones_validadas": RelacionRiC.objects.filter(estado__in=flujo.ESTADOS_VALIDADOS).count(),
        "limite_dias": config.dias_limite_revision,
    }

    if roles.puede(request.user, roles.ARCHIVISTA, roles.REVISOR):
        distribucion = _distribucion_entidades()
        documentos = flujo.documentos_con_estado()
        pendientes_totales = PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE).count()
        conteo_estados = {}
        for fila in documentos:
            conteo_estados[fila["estado"]] = conteo_estados.get(fila["estado"], 0) + 1
        decididas = PropuestaRiC.objects.exclude(estado=PropuestaRiC.Estado.PENDIENTE)
        total_propuestas = PropuestaRiC.objects.count()
        validadas = decididas.filter(estado__in=(PropuestaRiC.Estado.ACEPTADA, PropuestaRiC.Estado.MODIFICADA)).count()
        rechazadas = decididas.filter(estado=PropuestaRiC.Estado.RECHAZADA).count()
        contexto.update({
            "pendientes": pendientes_totales,
            "retencion_vencida": valoracion.conteo_vencidos(),
            # CC-02: documentos en curso a los que falta forma documental, agente o fecha.
            "incompletos": [
                {**f, "faltan": flujo.clases_faltantes(f["record"])}
                for f in documentos if f["estado"] in (flujo.EN_ANALISIS, flujo.EN_REVISION)
                and flujo.clases_faltantes(f["record"])
            ][:8],
            "distribucion_estado": {
                "total": total_propuestas,
                "validadas": validadas, "pendientes": pendientes_totales, "rechazadas": rechazadas,
                "p_validadas": round(validadas / total_propuestas * 100) if total_propuestas else 0,
                "p_pendientes": round(pendientes_totales / total_propuestas * 100) if total_propuestas else 0,
                "p_rechazadas": round(rechazadas / total_propuestas * 100) if total_propuestas else 0,
            },
            "en_analisis": [f for f in documentos if f["estado"] == flujo.EN_ANALISIS][:8],
            "en_revision": [f for f in documentos if f["estado"] == flujo.EN_REVISION][:8],
            "conteo_estados": [(flujo.ETIQUETAS[e], conteo_estados.get(e, 0)) for e in (
                flujo.SIN_TEXTO, flujo.SIN_ANALIZAR, flujo.EN_ANALISIS, flujo.EN_REVISION, flujo.PUBLICADO)],
            "muestras_pendientes": auditoria.MuestraRiC.objects.filter(
                resultado=auditoria.MuestraRiC.Resultado.PENDIENTE).count(),
            "documentos_sin_texto": Instantiation.objects.filter(paginas__isnull=True).distinct().count(),
            "distribucion": distribucion,
            "gradiente_distribucion": _gradiente_conico(distribucion),
            "total_entidades": sum(f["total"] for f in distribucion),
            "actividad_dias": _actividad_ultimos_dias(),
            "eventos_recientes": EventoRiC.objects.select_related("instanciacion").order_by("-id")[:8],
            "documentos_recientes": Instantiation.objects.select_related("record_resource").order_by("-fecha_registro")[:8],
        })
    return render(request, "ric/panel.html", contexto)
