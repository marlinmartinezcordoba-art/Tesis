"""
Envío de correo transaccional por SMTP (decisión documentada en
documentacion/modulo-autenticacion.md). El mismo código sirve para Gmail
con contraseña de aplicación o para el relevo SMTP de un proveedor
transaccional (Brevo, por ejemplo): solo cambian las variables EMAIL_*.
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("ricora.correo")


class CorreoNoConfigurado(Exception):
    pass


class CorreoFallido(Exception):
    pass


def enviar(destinatario: str, asunto: str, texto: str, html: str | None = None) -> None:
    if not settings.correo_configurado:
        raise CorreoNoConfigurado()
    mensaje = EmailMessage()
    mensaje["From"] = settings.remitente
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(texto)
    if html:
        mensaje.add_alternative(html, subtype="html")
    contexto = ssl.create_default_context()
    try:
        if settings.correo_puerto == 465:
            with smtplib.SMTP_SSL(settings.correo_servidor, 465, context=contexto,
                                  timeout=settings.correo_tiempo_espera) as smtp:
                smtp.login(settings.correo_usuario, settings.correo_contrasena)
                smtp.send_message(mensaje)
        else:
            with smtplib.SMTP(settings.correo_servidor, settings.correo_puerto,
                              timeout=settings.correo_tiempo_espera) as smtp:
                smtp.starttls(context=contexto)
                smtp.login(settings.correo_usuario, settings.correo_contrasena)
                smtp.send_message(mensaje)
    except (smtplib.SMTPException, OSError) as exc:
        # Nunca se registra la contraseña ni el enlace, solo el tipo de fallo.
        log.warning("No se pudo enviar el correo a %s: %s", destinatario, type(exc).__name__)
        raise CorreoFallido(type(exc).__name__) from exc


def _html(saludo: str, parrafo: str, enlace: str, boton: str, nota: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#e6eaf0;font-family:Inter,Arial,sans-serif;color:#1c2333">
<div style="max-width:480px;margin:32px auto;background:#f7f8fa;border:1px solid #cfd6e1;border-radius:12px;padding:28px">
<div style="font-family:'Source Serif 4',Georgia,serif;font-size:20px;font-weight:600">RICORA</div>
<div style="font-size:11px;color:#5b6477;text-transform:uppercase;letter-spacing:.09em;margin-bottom:22px">Archivo histórico</div>
<p>{saludo}</p><p>{parrafo}</p>
<p style="margin:26px 0"><a href="{enlace}" style="background:#2f5fd0;color:#fff;text-decoration:none;padding:11px 18px;border-radius:7px;font-weight:600">{boton}</a></p>
<p style="font-size:12px;color:#5b6477">{nota}</p>
<p style="font-size:12px;color:#5b6477;word-break:break-all">Si el botón no abre, copie esta dirección en el navegador:<br>{enlace}</p>
</div></body></html>"""


def enviar_invitacion(nombre: str, correo: str, enlace: str, horas: int) -> None:
    saludo = f"Hola, {nombre}:"
    parrafo = "Se creó una cuenta para usted en RICORA. Para empezar, defina su propia contraseña con el siguiente enlace."
    nota = f"El enlace sirve una sola vez y vence en {horas} horas. Nadie más conoce su contraseña, tampoco el administrador."
    texto = f"{saludo}\n\n{parrafo}\n\n{enlace}\n\n{nota}\n"
    enviar(correo, "Su cuenta en RICORA", texto, _html(saludo, parrafo, enlace, "Definir mi contraseña", nota))


def enviar_recuperacion(nombre: str, correo: str, enlace: str, minutos: int) -> None:
    saludo = f"Hola, {nombre}:"
    parrafo = "Recibimos una solicitud para restablecer la contraseña de su cuenta en RICORA. Si fue usted, defina una nueva con el siguiente enlace."
    nota = (f"El enlace sirve una sola vez y vence en {minutos} minutos. Si usted no lo pidió, ignore este correo: "
            "su contraseña actual sigue igual.")
    texto = f"{saludo}\n\n{parrafo}\n\n{enlace}\n\n{nota}\n"
    enviar(correo, "Restablecer su contraseña de RICORA", texto,
           _html(saludo, parrafo, enlace, "Definir una contraseña nueva", nota))


def enviar_prueba(correo: str) -> None:
    texto = "Este es un correo de prueba de RICORA. Si lo recibió, el envío de invitaciones y recuperaciones funciona."
    enviar(correo, "Prueba de correo de RICORA", texto)
