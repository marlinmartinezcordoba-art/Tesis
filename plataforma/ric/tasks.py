"""M2 · Tareas del trabajador de la cola (Celery). Cada una actualiza el
estado del archivo (Instantiation.estado_proceso, progreso y etapa) a
medida que avanza, para que la pantalla de preprocesamiento lo muestre sin
que la persona tenga que esperar con la página abierta.

El estado se escribe con `QuerySet.update()`: no dispara las señales de
auditoría en cada página (el resultado queda en la bitácora de eventos
EventoRiC, que es la trazabilidad archivística del proceso)."""

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import EventoRiC, Instantiation, Record, registrar_evento

log = logging.getLogger(__name__)
Estado = Instantiation.EstadoProceso

# Tramos de la barra de avance: el OCR es lo más largo.
_INICIO_OCR, _FIN_OCR, _IDIOMA, _MOTOR = 5, 85, 88, 92


def _poner(inst_id, **campos):
    Instantiation.objects.filter(pk=inst_id).update(**campos)


def _vigente(inst_id, intento):
    """El trabajo sigue siendo el último pedido (no fue reemplazado por un
    reintento manual): evita procesar dos veces el mismo archivo."""
    return Instantiation.objects.filter(pk=inst_id, intentos=intento).exists()


def _usuario(usuario_id):
    return get_user_model().objects.filter(pk=usuario_id).first() if usuario_id else None


def resumen(resultado):
    """(estado final, mensaje en lenguaje claro) a partir del resultado de
    `ingesta.preprocesar`."""
    from .idioma import nombre_idioma

    if resultado.get("formato_no_soportado"):
        return Estado.LISTO, "No fue posible extraer texto de este formato; el archivo queda preservado con su huella digital."
    partes = [f"{resultado.get('paginas', 0)} página(s)"]
    if resultado.get("confianza_ocr") is not None:
        partes.append(f"confianza OCR {resultado['confianza_ocr']}%")
    if resultado.get("idioma"):
        partes.append(f"idioma {nombre_idioma(resultado['idioma']).lower()}")
    texto = f"Preprocesado: {', '.join(partes)}."
    if resultado.get("calidad_baja"):
        return Estado.CALIDAD_BAJA, (
            f"{texto} {resultado['calidad_baja']} página(s) con calidad de lectura baja: decida si se reescanean "
            "o se aceptan antes de enviar al motor de análisis."
        )
    return Estado.LISTO, f"{texto} {mensaje_motor(resultado.get('analisis'))}".strip()


def mensaje_motor(analisis):
    if analisis is None:
        return ""
    if analisis.get("sin_proveedor"):
        return "Listo, pero no hay un proveedor de IA activo (Administración → Proveedores de IA)."
    if analisis.get("error"):
        return f"El motor de análisis no respondió — {analisis['error']}"
    return f"Enviado al motor de análisis: {analisis.get('propuestas', 0)} propuesta(s) de entidades."


def _fallo(inst_id, usuario, mensaje, detalle):
    _poner(inst_id, estado_proceso=Estado.ERROR, etapa="", mensaje_proceso=mensaje, proceso_terminado=timezone.now())
    inst = Instantiation.objects.filter(pk=inst_id).first()
    if inst is not None:
        registrar_evento(inst, EventoRiC.Tipo.EXTRACCION, agente=usuario or "sistema", detalle=detalle, exitoso=False)


def _a_json(resultado):
    """El resultado se guarda para consultarlo después; solo tipos simples."""
    return {k: v for k, v in resultado.items() if isinstance(v, (str, int, float, bool, dict, type(None)))}


@shared_task(name="ric.preprocesar_instanciacion")
def preprocesar_instanciacion(inst_id, usuario_id, intento):
    from .auditoria_acciones import actuando_como
    from .ingesta import preprocesar

    if not _vigente(inst_id, intento):
        log.info("Trabajo %s/%s descartado: fue reemplazado por un intento posterior", inst_id, intento)
        return
    inst = Instantiation.objects.select_related("record_resource").get(pk=inst_id)
    usuario = _usuario(usuario_id)
    _poner(inst_id, estado_proceso=Estado.PROCESANDO, progreso=2, etapa="Leyendo el archivo", proceso_iniciado=timezone.now())

    ultimo = {"progreso": 2}

    def al_avanzar(hecho, total):
        progreso = _INICIO_OCR + int((_FIN_OCR - _INICIO_OCR) * hecho / max(total, 1))
        if progreso != ultimo["progreso"] or hecho == total:
            ultimo["progreso"] = progreso
            _poner(inst_id, progreso=progreso, etapa=f"Leyendo página {hecho} de {total}")

    def al_cambiar_etapa(nombre):
        if nombre == "idioma":
            _poner(inst_id, progreso=_IDIOMA, etapa="Detectando idioma y calidad")
        elif nombre == "motor":
            _poner(inst_id, progreso=_MOTOR, etapa="Enviando al motor de análisis")

    try:
        with actuando_como(usuario):
            resultado = preprocesar(inst, agente=usuario or "sistema", al_avanzar=al_avanzar, al_cambiar_etapa=al_cambiar_etapa)
    except SoftTimeLimitExceeded:
        _fallo(inst_id, usuario, "El procesamiento superó el tiempo máximo permitido. Reintente; si vuelve a pasar, "
               "divida el archivo en partes más pequeñas.", {"error": "tiempo_limite", "intento": intento})
        return
    except Exception as e:
        log.exception("Falló el preprocesamiento de la instanciación %s", inst_id)
        _fallo(inst_id, usuario, f"No se pudo procesar el archivo: {e}. El original se conserva intacto; puede reintentar.",
               {"error": str(e)[:500], "intento": intento})
        return

    estado, mensaje = resumen(resultado)
    _poner(inst_id, estado_proceso=estado, progreso=100, etapa="", mensaje_proceso=mensaje,
           resultado_proceso=_a_json(resultado), proceso_terminado=timezone.now())


@shared_task(name="ric.analizar_instanciacion")
def analizar_instanciacion(inst_id, usuario_id, intento):
    """Después de "aceptar igual" las páginas de calidad baja: solo falta
    entregar el documento al motor de análisis (M3)."""
    from .auditoria_acciones import actuando_como
    from .motor import enviar_al_motor

    if not _vigente(inst_id, intento):
        return
    inst = Instantiation.objects.get(pk=inst_id)
    usuario = _usuario(usuario_id)
    record = Record.objects.filter(pk=inst.record_resource_id).first()
    _poner(inst_id, estado_proceso=Estado.PROCESANDO, progreso=_MOTOR, etapa="Enviando al motor de análisis",
           proceso_iniciado=timezone.now())
    try:
        with actuando_como(usuario):
            analisis = enviar_al_motor(record, usuario) if record is not None else None
    except SoftTimeLimitExceeded:
        _fallo(inst_id, usuario, "El motor de análisis superó el tiempo máximo permitido. Reintente.",
               {"error": "tiempo_limite", "etapa": "motor", "intento": intento})
        return
    except Exception as e:
        log.exception("Falló el envío al motor de la instanciación %s", inst_id)
        _fallo(inst_id, usuario, f"El motor de análisis falló: {e}. Puede reintentar.",
               {"error": str(e)[:500], "etapa": "motor", "intento": intento})
        return
    anterior = dict(inst.resultado_proceso or {})
    anterior["analisis"] = analisis
    _poner(inst_id, estado_proceso=Estado.LISTO, progreso=100, etapa="",
           mensaje_proceso=mensaje_motor(analisis) or "Listo.", resultado_proceso=anterior,
           proceso_terminado=timezone.now())
