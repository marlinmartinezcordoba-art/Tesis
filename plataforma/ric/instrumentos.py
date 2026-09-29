"""Precarga de los instrumentos archivísticos en M5 (insumo obligatorio
antes de encender el motor de análisis, según la especificación): la
Tabla de Retención Documental alimenta las formas documentales con su
serie y sus tiempos de retención y disposición final; el Cuadro de
Clasificación Documental alimenta las actividades/funciones y su
dependencia responsable; el organigrama alimenta las entidades
corporativas con su jerarquía. Sin esto, CC-05 no tiene contra qué
verificar y el motor propondría una función o un agente nuevo por
documento.

Los tres se cargan como CSV (separador , o ;) con encabezados en
español; cada fila es idempotente: se busca por nombre y se actualiza,
nunca se duplica."""

import csv
import io
import unicodedata

from django.db import transaction
from django.utils import timezone

from .models import Activity, CorporateBody, EventoRiC, FormaDocumental, RelacionRiC, registrar_evento

# Relaciones RiC-CM verificadas (ric_matrix.json) que materializan cada instrumento.
R_ACTIVIDAD_EJECUTADA_POR = "R060"  # Activity -> Agent "is or was performed by"
R_SUBORDINADO = "R045"  # Agent -> Agent "has or had subordinate"

COLUMNAS = {
    "trd": {
        "obligatorias": ("forma_documental", "serie"),
        "opcionales": ("definicion", "retencion_gestion", "retencion_central", "disposicion_final"),
    },
    "ccd": {"obligatorias": ("funcion",), "opcionales": ("tipo", "dependencia", "descripcion")},
    "organigrama": {"obligatorias": ("dependencia",), "opcionales": ("dependencia_superior", "sigla")},
}
_DISPOSICIONES = {
    "conservacion total": "conservacion_total", "ct": "conservacion_total",
    "eliminacion": "eliminacion", "e": "eliminacion",
    "seleccion": "seleccion", "s": "seleccion",
    "digitalizacion": "digitalizacion", "d": "digitalizacion", "m/d": "digitalizacion",
}


class ErrorDeImportacion(Exception):
    pass


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.strip().lower().replace(" ", "_").replace("/", "_")


def leer_csv(contenido):
    """Filas como dicts con claves normalizadas (sin tildes, minúsculas,
    espacios -> _). Detecta el separador (; o ,)."""
    if isinstance(contenido, bytes):
        try:
            contenido = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            contenido = contenido.decode("latin-1")
    muestra = contenido[:2048]
    separador = ";" if muestra.count(";") > muestra.count(",") else ","
    lector = csv.DictReader(io.StringIO(contenido), delimiter=separador)
    filas = []
    for fila in lector:
        limpia = {_normalizar(k): (v or "").strip() for k, v in fila.items() if k}
        if any(limpia.values()):
            filas.append(limpia)
    return filas


def _validar_columnas(filas, tipo):
    if not filas:
        raise ErrorDeImportacion("El archivo no tiene filas con datos.")
    faltan = [c for c in COLUMNAS[tipo]["obligatorias"] if c not in filas[0]]
    if faltan:
        raise ErrorDeImportacion(
            f"Faltan las columnas obligatorias: {', '.join(faltan)}. "
            f"Columnas esperadas: {', '.join(COLUMNAS[tipo]['obligatorias'] + COLUMNAS[tipo]['opcionales'])}."
        )


def _entero(valor):
    try:
        return int(float(valor.replace(",", "."))) if valor else None
    except ValueError:
        return None


def _relacion_manual(origen, destino, relacion_id, usuario):
    ya = RelacionRiC.objects.filter(
        relacion_id=relacion_id,
        origen_content_type__model=type(origen).__name__.lower(), origen_object_id=origen.pk,
        destino_content_type__model=type(destino).__name__.lower(), destino_object_id=destino.pk,
    ).exists()
    if ya:
        return False
    rel = RelacionRiC(relacion_id=relacion_id, origen=origen, destino=destino, validado_por=usuario, fecha_validacion=timezone.now())
    rel.save()
    rel.estado = RelacionRiC.Estado.ACEPTADA
    rel.save()
    return True


def _corporativa(nombre, usuario):
    entidad, creada = CorporateBody.objects.get_or_create(nombre=nombre, defaults={"creado_por": usuario})
    return entidad, creada


@transaction.atomic
def importar_trd(contenido, usuario):
    filas = leer_csv(contenido)
    _validar_columnas(filas, "trd")
    creadas = actualizadas = 0
    for fila in filas:
        nombre = fila["forma_documental"]
        if not nombre:
            continue
        forma, creada = FormaDocumental.objects.get_or_create(nombre=nombre, defaults={"creado_por": usuario})
        forma.serie_trd = fila["serie"] or forma.serie_trd
        forma.definicion = fila.get("definicion") or forma.definicion
        forma.tiempo_retencion_archivo_gestion = _entero(fila.get("retencion_gestion", "")) or forma.tiempo_retencion_archivo_gestion
        forma.tiempo_retencion_archivo_central = _entero(fila.get("retencion_central", "")) or forma.tiempo_retencion_archivo_central
        disposicion = _DISPOSICIONES.get(_normalizar(fila.get("disposicion_final", "")).replace("_", " "))
        if disposicion:
            forma.disposicion_final = disposicion
        forma.modificado_por = usuario
        forma.save()
        creadas += creada
        actualizadas += not creada
    registrar_evento(None, EventoRiC.Tipo.INGESTA, agente=usuario, detalle={"instrumento": "TRD", "creadas": creadas, "actualizadas": actualizadas})
    return {"creadas": creadas, "actualizadas": actualizadas, "filas": len(filas)}


@transaction.atomic
def importar_ccd(contenido, usuario):
    filas = leer_csv(contenido)
    _validar_columnas(filas, "ccd")
    creadas = actualizadas = relaciones = 0
    for fila in filas:
        nombre = fila["funcion"]
        if not nombre:
            continue
        actividad, creada = Activity.objects.get_or_create(nombre=nombre, defaults={"creado_por": usuario})
        tipo = _normalizar(fila.get("tipo", "")).replace("_", " ")
        if tipo:
            actividad.tipo_actividad = tipo
        if fila.get("descripcion"):
            actividad.descripcion_general = fila["descripcion"]
        actividad.modificado_por = usuario
        actividad.save()
        creadas += creada
        actualizadas += not creada
        if fila.get("dependencia"):
            dependencia, _ = _corporativa(fila["dependencia"], usuario)
            relaciones += _relacion_manual(actividad, dependencia, R_ACTIVIDAD_EJECUTADA_POR, usuario)
    registrar_evento(None, EventoRiC.Tipo.INGESTA, agente=usuario, detalle={"instrumento": "CCD", "creadas": creadas, "actualizadas": actualizadas, "relaciones": relaciones})
    return {"creadas": creadas, "actualizadas": actualizadas, "relaciones": relaciones, "filas": len(filas)}


@transaction.atomic
def importar_organigrama(contenido, usuario):
    filas = leer_csv(contenido)
    _validar_columnas(filas, "organigrama")
    creadas = relaciones = 0
    for fila in filas:
        nombre = fila["dependencia"]
        if not nombre:
            continue
        dependencia, creada = _corporativa(nombre, usuario)
        if fila.get("sigla") and not dependencia.identificador:
            dependencia.identificador = fila["sigla"]
            dependencia.modificado_por = usuario
            dependencia.save()
        creadas += creada
        if fila.get("dependencia_superior"):
            superior, _ = _corporativa(fila["dependencia_superior"], usuario)
            relaciones += _relacion_manual(superior, dependencia, R_SUBORDINADO, usuario)
    registrar_evento(None, EventoRiC.Tipo.INGESTA, agente=usuario, detalle={"instrumento": "organigrama", "creadas": creadas, "relaciones": relaciones})
    return {"creadas": creadas, "relaciones": relaciones, "filas": len(filas)}


IMPORTADORES = {"trd": importar_trd, "ccd": importar_ccd, "organigrama": importar_organigrama}
