"""M10 · Indicadores del panel, calculados siempre con los datos vigentes y
para un periodo elegido (última semana, último mes, trimestre, año o todo).

Cada cifra tiene detrás un filtro (`documentos_de`) que devuelve exactamente
los documentos que la componen: al hacer clic en el indicador se llega a esa
lista, no a un número estático (historia de usuario 10).

Definiciones (para que nadie tenga que adivinar qué mide cada número):
- Ingestados: documentos (Record) registrados en el periodo.
- Validados: de esos, los publicados (descripción revisada y aprobada, M6).
- Tiempo de revisión: para los documentos publicados en el periodo, desde
  que el análisis terminó (última entidad aceptada en M3/M4) hasta la
  publicación. Se muestra también el ciclo completo (carga → publicación).
- Pendientes de revisión: documentos sin publicar con propuestas del motor
  por decidir o con fichas aceptadas que el revisor aún no confirmó (M6).
- Atrasados (RF-M10-04): pendientes que esperan desde hace más días que el
  límite configurado en Administración → Parámetros.
"""

import datetime

from django.db.models import Count, Max, Min
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from . import flujo
from .models import Instantiation, PropuestaRiC, Record, RelacionRiC

PERIODOS = [
    ("7", "Última semana"),
    ("30", "Último mes"),
    ("90", "Último trimestre"),
    ("365", "Último año"),
    ("todo", "Todo"),
]
PERIODO_POR_DEFECTO = "30"


def periodo_valido(valor):
    return valor if valor in dict(PERIODOS) else PERIODO_POR_DEFECTO


def desde(periodo):
    """Inicio del periodo (inclusive), o None para «todo»."""
    if periodo == "todo":
        return None
    hoy = timezone.localdate()
    inicio = hoy - datetime.timedelta(days=int(periodo) - 1)
    return timezone.make_aware(datetime.datetime.combine(inicio, datetime.time.min))


def _en_periodo(qs, campo, periodo):
    inicio = desde(periodo)
    return qs.filter(**{f"{campo}__gte": inicio}) if inicio else qs


# --- RF-M10-01 --------------------------------------------------------------

def ingestados(periodo):
    return _en_periodo(Record.objects.all(), "fecha_registro", periodo)


def serie_ingesta(periodo):
    """Barras de ingreso: por día (semana, mes), por semana (trimestre) o por
    mes (año, todo). [{etiqueta, total, porcentaje}]."""
    hoy = timezone.localdate()
    if periodo in ("7", "30"):
        dias = int(periodo)
        claves = [hoy - datetime.timedelta(days=dias - 1 - i) for i in range(dias)]
        trunc, formato, titulo = TruncDate, "%d/%m", "por día"
    elif periodo == "90":
        lunes = hoy - datetime.timedelta(days=hoy.weekday())
        claves = [lunes - datetime.timedelta(weeks=12 - i) for i in range(13)]
        trunc, formato, titulo = TruncWeek, "sem. %d/%m", "por semana"
    else:
        primero = hoy.replace(day=1)
        meses = 12
        if periodo == "todo":
            primera = Record.objects.aggregate(m=Min("fecha_registro"))["m"]
            if primera:
                p = timezone.localtime(primera).date()
                meses = max(1, (primero.year - p.year) * 12 + primero.month - p.month + 1)
        claves = []
        for i in range(meses - 1, -1, -1):
            anio, mes = primero.year, primero.month - i
            while mes <= 0:
                mes += 12
                anio -= 1
            claves.append(datetime.date(anio, mes, 1))
        trunc, formato, titulo = TruncMonth, "%m/%Y", "por mes"
    conteos = {}
    for fecha, total in (
        Record.objects.filter(fecha_registro__date__gte=claves[0])
        .annotate(p=trunc("fecha_registro")).values("p").annotate(total=Count("pk")).values_list("p", "total")
    ):
        clave = fecha.date() if isinstance(fecha, datetime.datetime) else fecha
        conteos[clave] = conteos.get(clave, 0) + total
    serie = [{"etiqueta": c.strftime(formato), "total": conteos.get(c, 0)} for c in claves]
    maximo = max((d["total"] for d in serie), default=0) or 1
    for d in serie:
        d["porcentaje"] = round(d["total"] / maximo * 100)
    return {"titulo": titulo, "serie": serie, "total": sum(d["total"] for d in serie)}


# --- RF-M10-02 --------------------------------------------------------------

def validados(periodo):
    return ingestados(periodo).filter(publicado=True)


def porcentaje_validado(periodo):
    total = ingestados(periodo).count()
    publicados = validados(periodo).count()
    return {"total": total, "publicados": publicados, "porcentaje": round(publicados / total * 100) if total else None}


# --- RF-M10-03 --------------------------------------------------------------

def publicados_en(periodo):
    return _en_periodo(Record.objects.filter(publicado=True, fecha_publicacion__isnull=False), "fecha_publicacion", periodo)


def tiempos_de_revision(periodo):
    """Promedios en días, sobre los documentos publicados en el periodo."""
    revision, ciclo = [], []
    for record in publicados_en(periodo):
        fin_analisis = (
            flujo.relaciones_de(record).exclude(revision=RelacionRiC.Revision.NO_APLICA)
            .aggregate(m=Max("fecha_validacion"))["m"]
        )
        if fin_analisis and fin_analisis <= record.fecha_publicacion:
            revision.append((record.fecha_publicacion - fin_analisis).total_seconds())
        primera = record.instanciaciones.aggregate(m=Min("fecha_registro"))["m"]
        if primera:
            ciclo.append((record.fecha_publicacion - primera).total_seconds())

    def promedio(valores):
        if not valores:
            return None
        horas = sum(valores) / len(valores) / 3600
        return {"horas": round(horas, 1), "dias": round(horas / 24, 1), "documentos": len(valores)}

    return {"revision": promedio(revision), "ciclo": promedio(ciclo)}


# --- RF-M10-04 --------------------------------------------------------------

def esperando_revision():
    """{record_pk: fecha desde la que espera} para los documentos sin publicar
    con algo por decidir: propuestas del motor o fichas sin revisar (M6)."""
    ct_record = flujo._ct(Record)
    espera = {}
    for fila in (
        PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE, origen_content_type=ct_record)
        .values("origen_object_id").annotate(desde=Min("fecha_creacion"))
    ):
        espera[fila["origen_object_id"]] = fila["desde"]
    for campo in ("origen", "destino"):
        for fila in (
            RelacionRiC.objects.filter(
                estado__in=flujo.ESTADOS_VALIDADOS, revision=RelacionRiC.Revision.PENDIENTE,
                **{f"{campo}_content_type": ct_record},
            ).values(f"{campo}_object_id").annotate(desde=Min("fecha_validacion"))
        ):
            pk, fecha = fila[f"{campo}_object_id"], fila["desde"]
            if fecha and (pk not in espera or fecha < espera[pk]):
                espera[pk] = fecha
    publicados = set(Record.objects.filter(pk__in=espera, publicado=True).values_list("pk", flat=True))
    return {pk: f for pk, f in espera.items() if pk not in publicados}


def atrasados(limite_dias):
    """[{record, dias, desde}] de los que superan el límite, el más antiguo primero."""
    ahora = timezone.now()
    espera = esperando_revision()
    records = {r.pk: r for r in Record.objects.filter(pk__in=espera)}
    filas = [{"record": records[pk], "desde": f, "dias": (ahora - f).days}
             for pk, f in espera.items() if pk in records and (ahora - f).days >= limite_dias]
    return sorted(filas, key=lambda f: -f["dias"])


# --- Listas que componen cada cifra -----------------------------------------

FILTROS = {
    "ingestados": "Documentos ingestados",
    "validados": "Documentos con descripción validada y publicada",
    "publicados": "Documentos publicados en el periodo (base del tiempo de revisión)",
    "pendientes": "Documentos pendientes de revisión",
    "atrasados": "Documentos con la revisión atrasada",
    "incompletos": "Documentos con descripción incompleta",
    "sin_texto": "Documentos sin texto extraído",
}


def documentos_de(filtro, periodo, limite_dias):
    """El queryset de documentos que compone la cifra `filtro`."""
    if filtro == "ingestados":
        return ingestados(periodo)
    if filtro == "validados":
        return validados(periodo)
    if filtro == "publicados":
        return publicados_en(periodo)
    if filtro == "pendientes":
        return Record.objects.filter(pk__in=esperando_revision().keys())
    if filtro == "atrasados":
        return Record.objects.filter(pk__in=[f["record"].pk for f in atrasados(limite_dias)])
    if filtro == "incompletos":
        en_curso = Record.objects.filter(publicado=False)
        return Record.objects.filter(pk__in=[r.pk for r in en_curso if flujo.estado_documento(r) in (flujo.EN_ANALISIS, flujo.EN_REVISION) and flujo.clases_faltantes(r)])
    if filtro == "sin_texto":
        con_texto = Instantiation.objects.filter(paginas__isnull=False).values_list("record_resource_id", flat=True)
        return Record.objects.exclude(pk__in=con_texto)
    return Record.objects.none()
