"""
Enlaces de un solo uso para definir contraseña. La invitación a una
cuenta nueva y la recuperación de contraseña usan el mismo mecanismo;
solo cambian el tipo y la vigencia.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import correo
from app.core.config import settings
from app.core.seguridad import huella, secreto_aleatorio
from app.db.base import ahora
from app.models.token_acceso import TokenUnUso
from app.models.usuario import Usuario


def vigencia(tipo: str) -> timedelta:
    if tipo == "invitacion":
        return timedelta(hours=settings.horas_token_invitacion)
    return timedelta(minutes=settings.minutos_token_recuperacion)


def url_de(token: str) -> str:
    return f"{settings.url_publica}/acceso/{token}"


def crear(db: Session, usuario: Usuario, tipo: str, *, ip: str | None = None) -> str:
    """Crea un enlace nuevo y anula los anteriores del mismo usuario que no
    se usaron: solo el último enlace enviado sirve."""
    momento = ahora()
    db.execute(
        update(TokenUnUso)
        .where(TokenUnUso.usuario_id == usuario.id, TokenUnUso.usado_en.is_(None), TokenUnUso.anulado_en.is_(None))
        .values(anulado_en=momento)
    )
    token = secreto_aleatorio()
    db.add(TokenUnUso(
        usuario_id=usuario.id,
        tipo=tipo,
        huella=huella(token),
        creado_en=momento,
        vence_en=momento + vigencia(tipo),
        ip_solicitud=ip,
    ))
    return token


def vigente(db: Session, token: str) -> tuple[TokenUnUso, Usuario] | None:
    """El enlace sirve si existe, no se ha usado, no fue anulado, no ha
    vencido y la cuenta está activa."""
    registro = db.scalar(select(TokenUnUso).where(TokenUnUso.huella == huella(token)))
    if registro is None or registro.usado_en or registro.anulado_en or ahora() >= registro.vence_en:
        return None
    usuario = db.get(Usuario, registro.usuario_id)
    if usuario is None or not usuario.activo:
        return None
    return registro, usuario


@dataclass
class Entrega:
    enviado: bool
    mensaje: str
    # Solo cuando el correo no salió: el enlace se le muestra una única vez
    # al administrador para que lo haga llegar por otro medio.
    enlace: str | None = None


def entregar(usuario: Usuario, tipo: str, token: str) -> Entrega:
    enlace = url_de(token)
    try:
        if tipo == "invitacion":
            correo.enviar_invitacion(usuario.nombre, usuario.correo, enlace, settings.horas_token_invitacion)
        else:
            correo.enviar_recuperacion(usuario.nombre, usuario.correo, enlace, settings.minutos_token_recuperacion)
    except correo.CorreoNoConfigurado:
        return Entrega(False, "El envío de correo aún no está configurado. Copie el enlace y entrégueselo a la persona.", enlace)
    except correo.CorreoFallido:
        return Entrega(False, "El correo no se pudo enviar. Copie el enlace y entrégueselo a la persona.", enlace)
    return Entrega(True, f"Se envió el enlace a {usuario.correo}.")
