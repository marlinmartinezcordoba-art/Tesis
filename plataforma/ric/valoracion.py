"""Valoración y disposición: la retención de la TRD aplicada a cada
expediente, sin que nadie la escriba a mano.

El expediente hereda el Mandato de su serie (ver ric.clasificacion). Desde
la fecha de cierre del expediente corre la retención en archivo de gestión;
al vencer, corresponde la transferencia primaria al archivo central; al
vencer la retención en central, la disposición final que dice la TRD
(conservación total o selección: transferencia secundaria al archivo
histórico; eliminación; medio tecnológico). RICORA calcula fechas y fases
y arma las listas y el inventario (FUID); la decisión sigue siendo de la
persona archivista y del comité de la entidad.
"""

import csv
import datetime
import io

from .models import Instantiation, Record, RecordSet

ABIERTO = "abierto"
GESTION = "gestion"
CENTRAL = "central"
DISPOSICION = "disposicion"
SIN_TRD = "sin_trd"

ETIQUETAS = {
    ABIERTO: "Abierto (sin fecha de cierre)",
    GESTION: "En archivo de gestión",
    CENTRAL: "Transferencia primaria: pasa al archivo central",
    DISPOSICION: "Retención cumplida: aplicar disposición final",
    SIN_TRD: "Sin retención en la TRD",
}
DIAS_AVISO = 90


def _sumar_anios(fecha, anios):
    if fecha is None or anios is None:
        return None
    try:
        return fecha.replace(year=fecha.year + anios)
    except ValueError:  # 29 de febrero
        return fecha.replace(year=fecha.year + anios, day=28)


def expedientes():
    return (
        RecordSet.objects.filter(tipo_conjunto=RecordSet.Tipo.EXPEDIENTE)
        .select_related("padre", "padre__actividad", "padre__actividad__mandato", "padre__padre")
        .order_by("-fecha_registro")
    )


def resumen(expediente, hoy=None):
    """Todo lo que la pantalla y el inventario necesitan de un expediente."""
    hoy = hoy or datetime.date.today()
    serie = expediente.serie()
    mandato = expediente.mandato()
    fin_gestion = fin_central = None
    fase = SIN_TRD
    if mandato is not None and mandato.es_serie_trd:
        fase = ABIERTO
        if expediente.fecha_cierre:
            fin_gestion = _sumar_anios(expediente.fecha_cierre, mandato.tiempo_retencion_archivo_gestion or 0)
            fin_central = _sumar_anios(fin_gestion, mandato.tiempo_retencion_archivo_central or 0)
            if hoy < fin_gestion:
                fase = GESTION
            elif hoy < fin_central:
                fase = CENTRAL
            else:
                fase = DISPOSICION
    proximo = fin_gestion if fase == GESTION else fin_central if fase == CENTRAL else None
    documentos = Record.objects.filter(record_set=expediente)
    return {
        "expediente": expediente, "serie": serie, "mandato": mandato, "seccion": expediente.seccion(),
        "fase": fase, "etiqueta": ETIQUETAS[fase],
        "fin_gestion": fin_gestion, "fin_central": fin_central,
        "dias": (proximo - hoy).days if proximo else None,
        "pronto": proximo is not None and (proximo - hoy).days <= DIAS_AVISO,
        "disposicion": mandato.disposicion_final_texto() if mandato is not None else "",
        "codigos": mandato.disposicion_final_codigos() if mandato is not None else [],
        "documentos": documentos.count(),
        "folios": sum(i.paginas.count() for i in Instantiation.objects.filter(record_resource__in=documentos)),
        "fecha_inicial": expediente.fecha_apertura or (documentos.order_by("fecha_registro").values_list("fecha_registro", flat=True).first() or expediente.fecha_registro).date(),
        "fecha_final": expediente.fecha_cierre,
    }


def resumenes(hoy=None, queryset=None):
    return [resumen(e, hoy) for e in (queryset if queryset is not None else expedientes())]


def transferencias(hoy=None):
    """Listas de trabajo: transferencia primaria (retención en gestión vencida
    o por vencer) y disposición final (retención en central vencida o por
    vencer), estas últimas agrupadas por lo que manda la TRD."""
    hoy = hoy or datetime.date.today()
    primaria, disposicion = [], []
    for r in resumenes(hoy):
        if r["fase"] == CENTRAL or (r["fase"] == GESTION and r["pronto"]):
            primaria.append(r)
        elif r["fase"] == DISPOSICION or (r["fase"] == CENTRAL and r["pronto"]):
            disposicion.append(r)
    primaria.sort(key=lambda r: r["fin_gestion"])
    disposicion.sort(key=lambda r: r["fin_central"])
    return {"primaria": primaria, "disposicion": disposicion}


def conteo_vencidos(hoy=None):
    listas = transferencias(hoy)
    return len(listas["primaria"]) + len(listas["disposicion"])


COLUMNAS_FUID = [
    "N° de orden", "Entidad productora", "Unidad administrativa", "Oficina productora", "Código",
    "Nombre de la serie / subserie", "Expediente", "Fecha inicial", "Fecha final", "Unidad de conservación",
    "N° de folios", "Soporte", "Frecuencia de consulta", "Retención gestión (años)", "Retención central (años)",
    "Disposición final", "Fase actual", "Notas",
]


def fuid_csv(hoy=None, queryset=None):
    """Formato Único de Inventario Documental (AGN): una fila por expediente."""
    from .clasificacion import conjunto_fondo, entidad_raiz

    raiz = entidad_raiz()
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(COLUMNAS_FUID)
    for orden, r in enumerate(resumenes(hoy, queryset), start=1):
        e, m, seccion = r["expediente"], r["mandato"], r["seccion"]
        superior = seccion.padre if seccion is not None and seccion.padre is not None and seccion.padre.tipo_conjunto != RecordSet.Tipo.FONDO else None
        escritor.writerow([
            orden, raiz.nombre if raiz else "", superior.nombre if superior else "", seccion.nombre if seccion else "",
            e.identificador or (r["serie"].identificador if r["serie"] else ""), r["serie"].nombre if r["serie"] else "",
            e.nombre, r["fecha_inicial"].isoformat() if r["fecha_inicial"] else "", r["fecha_final"].isoformat() if r["fecha_final"] else "",
            "expediente electrónico", r["folios"], m.soporte if m else "", "",
            m.tiempo_retencion_archivo_gestion if m else "", m.tiempo_retencion_archivo_central if m else "",
            r["disposicion"], r["etiqueta"], e.descripcion_general,
        ])
    return salida.getvalue()
