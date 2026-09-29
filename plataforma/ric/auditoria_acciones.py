"""Módulo transversal de auditoría de acciones humanas (sección 7 del prompt
de desarrollo y sección D de la auditoría de arquitectura): quién hizo qué,
sobre qué, cuándo y con qué valores antes y después.

Es distinto de la bitácora de preservación `EventoRiC` (qué le pasó a cada
documento, encadenada por hash, estilo PREMIS) y del versionado `VersionRiC`
(fotografía de cada entidad antes de cambiar). Aquí se registra la acción de
la persona: inicio y cierre de sesión, intentos fallidos y bloqueos, accesos
denegados por rol, creación, modificación, borrado lógico y restauración de
cualquier entidad del sistema, con el diferencial de campos.

Cómo llega el usuario a las señales de modelo: un middleware guarda la
petición actual en un hilo local; `registrar_accion` la lee si no se le pasa
el usuario de forma explícita (comandos de consola, siembras).
"""

import contextlib
import threading

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db.models.signals import post_save, pre_save
from django.utils import timezone
from django.utils.functional import SimpleLazyObject, empty

_estado = threading.local()

# Campos que cambian solos o que nunca deben quedar en claro en la auditoría.
_CAMPOS_IGNORADOS = {"progreso", "etapa", "proceso_iniciado", "proceso_terminado", "resultado_proceso", "fecha_actualizacion", "fecha_registro", "last_login", "ultima_prueba", "date_joined"}
_CAMPOS_SECRETOS = {"password", "clave_api"}
INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 15


class UsuarioActualMiddleware:
    """Deja la petición a mano para que las señales de modelo sepan quién actúa."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _estado.request = request
        try:
            return self.get_response(request)
        finally:
            _estado.request = None


def peticion_actual():
    return getattr(_estado, "request", None)


def usuario_actual():
    request = peticion_actual()
    usuario = getattr(request, "user", None) if request is not None else getattr(_estado, "usuario", None)
    return usuario if usuario is not None and getattr(usuario, "is_authenticated", False) else None


@contextlib.contextmanager
def actuando_como(usuario):
    """Fuera de una petición (el trabajador de la cola, M2) los cambios se
    auditan a nombre de quien envió el trabajo, no como anónimos."""
    anterior = getattr(_estado, "usuario", None)
    _estado.usuario = usuario
    try:
        yield
    finally:
        _estado.usuario = anterior


def _ip(request):
    if request is None:
        return ""
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (reenviada.split(",")[0].strip() if reenviada else request.META.get("REMOTE_ADDR", "")) or ""


def _valor(valor):
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if hasattr(valor, "pk"):
        return valor.pk
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)


def instantanea(instancia):
    """Los campos propios de la instancia como dict serializable, con los
    secretos enmascarados (nunca una contraseña ni una clave en la auditoría)."""
    datos = {}
    for campo in instancia._meta.fields:
        if campo.name in _CAMPOS_IGNORADOS:
            continue
        valor = getattr(instancia, campo.attname if campo.is_relation else campo.name, None)
        datos[campo.name] = "***" if campo.name in _CAMPOS_SECRETOS and valor else _valor(valor)
    return datos


def _desenvolver(objeto):
    """request.user llega como SimpleLazyObject; para ContentType hace falta el modelo real."""
    if isinstance(objeto, SimpleLazyObject):
        if objeto._wrapped is empty:
            objeto._setup()
        return objeto._wrapped
    return objeto


def registrar_accion(accion, objeto=None, antes=None, despues=None, detalle=None, usuario=None, exitoso=True):
    from .models import RegistroAuditoria

    request = peticion_actual()
    objeto, usuario = _desenvolver(objeto), _desenvolver(usuario)
    if usuario is None:
        usuario = _desenvolver(usuario_actual())
    if usuario is not None and not getattr(usuario, "pk", None):
        usuario = None
    registro = RegistroAuditoria(
        usuario=usuario, usuario_nombre=usuario.get_username() if usuario is not None else (detalle or {}).get("usuario", "sistema"),
        accion=accion, antes=antes or {}, despues=despues or {}, detalle=detalle or {}, exitoso=exitoso,
        ip=_ip(request), agente_usuario=(request.META.get("HTTP_USER_AGENT", "")[:255] if request is not None else ""),
    )
    if objeto is not None and getattr(objeto, "pk", None):
        registro.content_type = ContentType.objects.get_for_model(type(objeto))
        registro.object_id = objeto.pk
        registro.objeto_texto = str(objeto)[:255]
    registro.save()
    return registro


# --- borrado lógico: cascada y conteo ---------------------------------------

def eliminar_relaciones_de(entidad, usuario, motivo):
    """Al borrar lógicamente una entidad, sus relaciones RiC siguen el mismo
    camino: no se destruyen, quedan marcadas con el mismo motivo."""
    from django.db.models import Q

    from .models import RelacionRiC

    ct = ContentType.objects.get_for_model(type(entidad))
    filtro = Q(origen_content_type=ct, origen_object_id=entidad.pk) | Q(destino_content_type=ct, destino_object_id=entidad.pk)
    n = 0
    for rel in RelacionRiC.objects.filter(filtro):
        rel.eliminar(usuario, motivo=f"Entidad eliminada: {motivo}" if motivo else "Entidad eliminada", auditar=False)
        n += 1
    return n


# --- sesiones: expiración y revocación ---------------------------------------

def cerrar_sesiones_de(usuario, motivo=""):
    """Revoca todas las sesiones abiertas de un usuario (al desactivarlo, al
    restablecer su contraseña o por decisión del administrador). Las
    sesiones viven en la base de datos, así que cerrarlas aquí las invalida
    en todos los procesos del servidor de inmediato."""
    cerradas = 0
    for sesion in Session.objects.filter(expire_date__gte=timezone.now()):
        if str(sesion.get_decoded().get("_auth_user_id")) == str(usuario.pk):
            sesion.delete()
            cerradas += 1
    registrar_accion("sesiones_cerradas", objeto=usuario, detalle={"sesiones": cerradas, "motivo": motivo})
    return cerradas


# --- bloqueo por intentos fallidos --------------------------------------------

def intentos_fallidos(nombre_usuario, minutos=MINUTOS_BLOQUEO):
    from .models import RegistroAuditoria

    desde = timezone.now() - timezone.timedelta(minutes=minutos)
    return RegistroAuditoria.objects.filter(accion="login_fallido", detalle__usuario=nombre_usuario, fecha__gte=desde).count()


def bloqueado(nombre_usuario):
    return bool(nombre_usuario) and intentos_fallidos(nombre_usuario) >= INTENTOS_MAXIMOS


# --- señales -----------------------------------------------------------------

def _modelos_auditados():
    from django.apps import apps

    from .models import BorradoLogico, ConfiguracionSistema

    modelos = [m for m in apps.get_app_config("ric").get_models() if issubclass(m, BorradoLogico) and not m._meta.abstract]
    return modelos + [ConfiguracionSistema, get_user_model()]


def _antes_de_guardar(sender, instance, **kwargs):
    if instance.pk:
        anterior = sender._base_manager.filter(pk=instance.pk).first()
        instance._auditoria_antes = instantanea(anterior) if anterior is not None else None
    else:
        instance._auditoria_antes = None


def _despues_de_guardar(sender, instance, created, **kwargs):
    if getattr(instance, "_auditoria_silenciar", False):
        return
    despues = instantanea(instance)
    if created:
        registrar_accion("crear", objeto=instance, despues=despues)
        return
    antes = getattr(instance, "_auditoria_antes", None) or {}
    cambios_antes = {k: v for k, v in antes.items() if despues.get(k) != v}
    cambios_despues = {k: despues.get(k) for k in cambios_antes}
    if not cambios_antes:
        return
    # El borrado lógico y la restauración se registran aparte, con su motivo.
    if set(cambios_antes) <= {"eliminado", "eliminado_en", "eliminado_por", "motivo_eliminacion"}:
        return
    registrar_accion("modificar", objeto=instance, antes=cambios_antes, despues=cambios_despues)


def _sesion_iniciada(sender, request, user, **kwargs):
    _estado.request = request
    registrar_accion("iniciar_sesion", objeto=user, usuario=user)


def _sesion_cerrada(sender, request, user, **kwargs):
    _estado.request = request
    if user is not None:
        registrar_accion("cerrar_sesion", objeto=user, usuario=user)


def _login_fallido(sender, credentials, request, **kwargs):
    _estado.request = request
    nombre = (credentials or {}).get("username", "")
    registrar_accion("login_fallido", detalle={"usuario": nombre}, exitoso=False)


def conectar_senales():
    for modelo in _modelos_auditados():
        pre_save.connect(_antes_de_guardar, sender=modelo, dispatch_uid=f"auditoria_pre_{modelo.__name__}")
        post_save.connect(_despues_de_guardar, sender=modelo, dispatch_uid=f"auditoria_post_{modelo.__name__}")
    user_logged_in.connect(_sesion_iniciada, dispatch_uid="auditoria_login")
    user_logged_out.connect(_sesion_cerrada, dispatch_uid="auditoria_logout")
    user_login_failed.connect(_login_fallido, dispatch_uid="auditoria_login_fallido")
