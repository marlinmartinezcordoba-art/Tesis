"""
Ciclo de vida de una sesión: abrir, renovar, registrar actividad, cerrar
y cerrar las vencidas. Cada apertura y cada cierre, también el cierre por
expiración, deja su evento en la auditoría: de ahí salen las horas
conectadas y los días trabajados del panel consolidado semanal.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.seguridad import huella, secreto_aleatorio
from app.db.base import ahora
from app.models.sesion import Sesion
from app.models.usuario import Usuario
from app.servicios.auditoria import Accion, registrar

# La última actividad se actualiza como mucho una vez por minuto, para no
# escribir en la base de datos en cada clic.
_INTERVALO_ACTIVIDAD = timedelta(seconds=60)


def _inactividad() -> timedelta:
    return timedelta(minutes=settings.minutos_inactividad_sesion)


def vencida(sesion: Sesion, momento: datetime | None = None) -> bool:
    momento = momento or ahora()
    return momento >= sesion.vence_en or momento - sesion.ultima_actividad >= _inactividad()


def valor_galleta(sesion_id: uuid.UUID, secreto: str) -> str:
    return f"{sesion_id}.{secreto}"


def abrir(db: Session, usuario: Usuario, *, ip: str | None, navegador: str | None) -> tuple[Sesion, str]:
    """Abre una sesión y devuelve (sesión, valor de la galleta de renovación)."""
    momento = ahora()
    secreto = secreto_aleatorio()
    sesion = Sesion(
        id=uuid.uuid4(),
        usuario_id=usuario.id,
        huella_renovacion=huella(secreto),
        iniciada_en=momento,
        ultima_actividad=momento,
        vence_en=momento + timedelta(hours=settings.horas_maximas_sesion),
        ip=ip,
        navegador=(navegador or "")[:300] or None,
    )
    db.add(sesion)
    registrar(
        db,
        modulo="autenticacion",
        accion=Accion.INICIO_SESION,
        usuario_id=usuario.id,
        entidad_tipo="sesion",
        entidad_id=sesion.id,
        nuevo={"inicio": momento.isoformat()},
        ip=ip,
    )
    return sesion, valor_galleta(sesion.id, secreto)


def cerrar(db: Session, sesion: Sesion, motivo: str, *, por: uuid.UUID | None = None, ip: str | None = None) -> None:
    """Cierra una sesión abierta. En el cierre por expiración la hora de
    fin es la de la última actividad real, no la del momento en que el
    sistema se dio cuenta: así las horas conectadas no se inflan."""
    if sesion.cerrada_en is not None:
        return
    if motivo == "expiracion":
        fin = min(sesion.ultima_actividad, sesion.vence_en)
    else:
        fin = ahora()
    sesion.cerrada_en = fin
    sesion.motivo_cierre = motivo
    registrar(
        db,
        modulo="autenticacion",
        accion=Accion.CIERRE_SESION,
        usuario_id=sesion.usuario_id,
        entidad_tipo="sesion",
        entidad_id=sesion.id,
        nuevo={
            "inicio": sesion.iniciada_en.isoformat(),
            "fin": fin.isoformat(),
            "motivo": motivo,
            **({"cerrada_por": str(por)} if por and por != sesion.usuario_id else {}),
        },
        ip=ip,
    )


def cerrar_vencidas(db: Session) -> int:
    """Cierra, con su evento de expiración, todas las sesiones que ya
    vencieron sin que nadie las cerrara. Se llama en cada inicio de sesión
    y en cada renovación; con un equipo pequeño eso basta para que ninguna
    quede abierta indefinidamente (ver decisión en la documentación)."""
    momento = ahora()
    limite_inactividad = momento - _inactividad()
    abiertas = db.scalars(
        select(Sesion).where(
            Sesion.cerrada_en.is_(None),
            or_(Sesion.vence_en <= momento, Sesion.ultima_actividad <= limite_inactividad),
        )
    ).all()
    for sesion in abiertas:
        cerrar(db, sesion, "expiracion")
    return len(abiertas)


def cerrar_todas(db: Session, usuario_id: uuid.UUID, motivo: str, *, excepto: uuid.UUID | None = None,
                 por: uuid.UUID | None = None, ip: str | None = None) -> int:
    abiertas = db.scalars(
        select(Sesion).where(Sesion.usuario_id == usuario_id, Sesion.cerrada_en.is_(None))
    ).all()
    n = 0
    for sesion in abiertas:
        if excepto is not None and sesion.id == excepto:
            continue
        cerrar(db, sesion, motivo, por=por, ip=ip)
        n += 1
    return n


def registrar_actividad(db: Session, sesion: Sesion) -> None:
    momento = ahora()
    if momento - sesion.ultima_actividad >= _INTERVALO_ACTIVIDAD:
        sesion.ultima_actividad = momento
        db.commit()


class RenovacionInvalida(Exception):
    pass


def renovar(db: Session, galleta: str | None) -> tuple[Sesion, str]:
    """Valida la galleta de renovación y la rota: el secreto usado deja de
    servir y se entrega uno nuevo. Si alguien presenta un secreto que ya
    fue rotado (señal de que la galleta fue copiada), se cierra la sesión."""
    if not galleta or "." not in galleta:
        raise RenovacionInvalida()
    sid_texto, secreto = galleta.split(".", 1)
    try:
        sid = uuid.UUID(sid_texto)
    except ValueError as exc:
        raise RenovacionInvalida() from exc
    sesion = db.get(Sesion, sid)
    if sesion is None or sesion.cerrada_en is not None:
        raise RenovacionInvalida()
    if sesion.huella_renovacion != huella(secreto):
        cerrar(db, sesion, "reutilizacion_token")
        db.commit()
        raise RenovacionInvalida()
    if vencida(sesion):
        cerrar(db, sesion, "expiracion")
        db.commit()
        raise RenovacionInvalida()
    usuario = db.get(Usuario, sesion.usuario_id)
    if usuario is None or not usuario.activo:
        cerrar(db, sesion, "cuenta_desactivada")
        db.commit()
        raise RenovacionInvalida()
    nuevo = secreto_aleatorio()
    sesion.huella_renovacion = huella(nuevo)
    sesion.ultima_actividad = ahora()
    return sesion, valor_galleta(sesion.id, nuevo)
