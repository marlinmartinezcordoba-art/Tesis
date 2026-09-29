"""M2 · Cola de preprocesamiento: poner un archivo en la cola, saber si ya
está en ella, reconocer un trabajo perdido y saber si hay un trabajador
atendiendo. Las vistas solo hablan con este módulo; las tareas de Celery
viven en `ric.tasks`.

Garantías:
- Un archivo no entra dos veces a la cola mientras su trabajo siga vivo.
- Cada envío lleva un número de intento; si un trabajo viejo reaparece
  (reentrega del broker después de un reintento manual) se descarta solo.
- Si el broker no responde, el archivo queda en «error» con la causa en
  lenguaje claro, nunca en «en cola» para siempre.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.utils import timezone

from .models import Instantiation

log = logging.getLogger(__name__)

EstadoProceso = Instantiation.EstadoProceso
ACTIVOS = (EstadoProceso.EN_COLA, EstadoProceso.PROCESANDO)
PREPROCESAR = "preprocesar"
ANALIZAR = "analizar"


class ColaNoDisponible(Exception):
    """El broker (Redis) no aceptó el trabajo."""


def perdido(inst, ahora=None):
    """Un trabajo activo que lleva más del límite sin terminar: el
    trabajador murió o se reinició el servidor. Se puede reintentar."""
    if inst.estado_proceso not in ACTIVOS:
        return False
    ahora = ahora or timezone.now()
    desde = inst.proceso_iniciado or inst.proceso_encolado
    return desde is None or ahora - desde > timedelta(minutes=settings.RICORA_MINUTOS_TRABAJO_PERDIDO)


def puede_enviarse(inst):
    return inst.estado_proceso not in ACTIVOS or perdido(inst)


def encolar(inst, usuario, tarea=PREPROCESAR):
    """Marca el archivo en cola y entrega el trabajo al broker. Devuelve
    True si quedó en cola (o, sin Redis, ya se procesó), False si ya
    estaba en cola. Lanza ColaNoDisponible si el broker falla."""
    from . import tasks
    from .auditoria_acciones import registrar_accion
    from .models import RegistroAuditoria

    if not puede_enviarse(inst):
        return False
    ahora = timezone.now()
    # Actualización condicional: si dos personas pulsan a la vez, solo una gana.
    ganadas = Instantiation.objects.filter(pk=inst.pk, intentos=inst.intentos).update(
        estado_proceso=EstadoProceso.EN_COLA, progreso=0, etapa="En cola", mensaje_proceso="",
        proceso_encolado=ahora, proceso_iniciado=None, proceso_terminado=None, intentos=F("intentos") + 1,
    )
    if not ganadas:
        return False
    inst.refresh_from_db()
    registrar_accion(
        RegistroAuditoria.Accion.MODIFICAR, inst, usuario=usuario,
        detalle={"cola": tarea, "intento": inst.intentos, "mensaje": "Enviado a la cola de procesamiento."},
    )
    funcion = tasks.analizar_instanciacion if tarea == ANALIZAR else tasks.preprocesar_instanciacion
    try:
        funcion.delay(inst.pk, getattr(usuario, "pk", None), inst.intentos)
    except Exception as e:  # kombu.OperationalError, redis.ConnectionError...
        log.exception("La cola no aceptó el trabajo de la instanciación %s", inst.pk)
        Instantiation.objects.filter(pk=inst.pk).update(
            estado_proceso=EstadoProceso.ERROR, etapa="",
            mensaje_proceso="La cola de procesamiento no está disponible en este momento. Intente de nuevo en unos minutos; "
            "si persiste, avise al administrador (servicio Redis o trabajador detenido).",
            proceso_terminado=timezone.now(),
        )
        inst.refresh_from_db()
        raise ColaNoDisponible(str(e)) from e
    inst.refresh_from_db()
    return True


def trabajadores_activos():
    """Cuántos trabajadores responden. Sin Redis el procesamiento corre en
    el mismo proceso, así que siempre hay uno. Se guarda 15 s en caché
    para no hacer ping en cada consulta de estado de la pantalla."""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return 1
    guardado = cache.get("ricora_trabajadores_activos")
    if guardado is not None:
        return guardado
    from config.celery import app

    try:
        total = len(app.control.ping(timeout=0.5) or [])
    except Exception:
        log.warning("No fue posible consultar a los trabajadores de la cola", exc_info=True)
        total = 0
    cache.set("ricora_trabajadores_activos", total, 15)
    return total
