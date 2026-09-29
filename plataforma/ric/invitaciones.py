"""M11 (RF-M11-01, paso 3 del flujo): invitación a una cuenta nueva.

La persona recibe un enlace de un solo uso con el que crea su propia
contraseña; el administrador nunca la conoce ni la escribe. El enlace usa el
generador de tokens de Django: deja de servir en cuanto se crea la
contraseña (el token depende de ella) y vence a los días que fija
PASSWORD_RESET_TIMEOUT.

Si el servidor tiene correo configurado (EMAIL_HOST), la invitación se envía
sola; si no, se le entrega el enlace al administrador para que lo haga
llegar por el medio que tenga. Nunca se finge un envío que no ocurrió."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode


def dias_vigencia():
    return max(1, settings.PASSWORD_RESET_TIMEOUT // 86400)


def enlace(request, usuario):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    return request.build_absolute_uri(reverse("invitacion", args=[uid, token]))


def usuario_de(uidb64, token):
    """La cuenta del enlace, o None si el enlace no es válido, ya se usó o venció."""
    from django.contrib.auth.models import User

    try:
        usuario = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None
    if not usuario.is_active or not default_token_generator.check_token(usuario, token):
        return None
    return usuario


def pendiente(usuario):
    """La cuenta todavía no tiene contraseña propia: la invitación no se ha usado."""
    return not usuario.has_usable_password()


def enviar(request, usuario, motivo="invitacion"):
    """Envía (o entrega) el enlace. `motivo`: "invitacion" (cuenta nueva) o
    "restablecer" (olvidó la contraseña). Devuelve (enviado_por_correo, mensaje, url)."""
    url = enlace(request, usuario)
    dias = dias_vigencia()
    if not usuario.email:
        return False, "La cuenta no tiene correo: copie el enlace y envíeselo a la persona.", url
    if not settings.EMAIL_HOST:
        return False, (f"El servidor no tiene correo configurado: copie el enlace de invitación y envíelo a {usuario.email}. "
                       f"Sirve una sola vez y vence en {dias} día(s)."), url
    nombre = usuario.first_name or usuario.username
    if motivo == "restablecer":
        asunto = "Restablecer su contraseña de RICORA"
        cuerpo = (f"Hola {nombre}.\n\nSe pidió restablecer la contraseña de su cuenta «{usuario.username}» en RICORA.\n"
                  f"Para crear una nueva, abra este enlace (sirve una sola vez y vence en {dias} día(s)):\n\n{url}\n\n"
                  "Si usted no lo pidió, ignore este mensaje: su contraseña actual sigue funcionando.\n")
    else:
        asunto = "Invitación a RICORA"
        cuerpo = (f"Hola {nombre}.\n\nSe creó tu cuenta en RICORA con el usuario «{usuario.username}».\n"
                  f"Para entrar, crea tu contraseña en este enlace (sirve una sola vez y vence en {dias} día(s)):\n\n{url}\n")
    try:
        send_mail(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, [usuario.email], fail_silently=False)
    except Exception as e:  # el error real se muestra, no se oculta
        return False, f"No fue posible enviar el correo ({e}). Copie el enlace y envíelo a {usuario.email}.", url
    return True, f"Enlace enviado a {usuario.email}." if motivo == "restablecer" else f"Invitación enviada a {usuario.email}.", url
