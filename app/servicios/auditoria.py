"""
Función única de registro de auditoría. Todos los módulos la importan y
la llaman; ninguno escribe su propio registro en paralelo.

El evento se agrega a la misma transacción de la acción que lo produce:
si la acción falla y se revierte, el evento también; si la acción se
guarda, el evento queda guardado con ella. Así no puede existir una
acción sin su evento, ni un evento de algo que no ocurrió.
"""

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.auditoria import RegistroAuditoria

# Módulos del sistema, tal como aparecen en la auditoría.
MODULOS = ("autenticacion", "ingesta", "descripcion", "vocabularios", "instrumentos", "preservacion", "auditoria", "sistema",
           "evaluacion")


class Accion:
    """Acciones de autenticación. Cada módulo agrega aquí las suyas."""

    INICIO_SESION = "inicio_sesion"
    CIERRE_SESION = "cierre_sesion"
    INGRESO_FALLIDO = "ingreso_fallido"
    INGRESO_BLOQUEADO = "ingreso_bloqueado"
    SOLICITUD_RECUPERACION = "solicitud_recuperacion"
    CONTRASENA_DEFINIDA = "contrasena_definida"  # por enlace de invitación o recuperación
    CONTRASENA_CAMBIADA = "contrasena_cambiada"  # desde Mi perfil
    USUARIO_CREADO = "usuario_creado"
    USUARIO_EDITADO = "usuario_editado"  # nombre o rol
    USUARIO_DESACTIVADO = "usuario_desactivado"
    USUARIO_REACTIVADO = "usuario_reactivado"
    ENLACE_ENVIADO = "enlace_enviado"  # invitación o recuperación generada por el administrador
    SESIONES_REVOCADAS = "sesiones_revocadas"
    CUENTA_ADMINISTRADORA_RESTABLECIDA = "cuenta_administradora_restablecida"
    SEGUNDO_FACTOR_ACTIVADO = "segundo_factor_activado"
    SEGUNDO_FACTOR_DESACTIVADO = "segundo_factor_desactivado"
    SEGUNDO_FACTOR_RESTABLECIDO = "segundo_factor_restablecido"  # por el administrador (teléfono perdido)
    CODIGO_RESPALDO_USADO = "codigo_respaldo_usado"


def ip_de(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def registrar(
    db: Session,
    *,
    modulo: str,
    accion: str,
    usuario_id: uuid.UUID | None = None,
    entidad_tipo: str | None = None,
    entidad_id: Any = None,
    anterior: dict | None = None,
    nuevo: dict | None = None,
    detalle: str | None = None,
    request: Request | None = None,
    ip: str | None = None,
) -> RegistroAuditoria:
    if modulo not in MODULOS:
        raise ValueError(f"Módulo de auditoría desconocido: {modulo}")
    evento = RegistroAuditoria(
        usuario_id=usuario_id,
        modulo=modulo,
        accion=accion,
        entidad_tipo=entidad_tipo,
        entidad_id=str(entidad_id) if entidad_id is not None else None,
        valor_anterior=anterior,
        valor_nuevo=nuevo,
        detalle=detalle,
        ip=ip or ip_de(request),
    )
    db.add(evento)
    return evento


# --- Cadena de huellas (brecha RF-AUD-002) --------------------------------------------------------

def verificar_cadena(db: Session) -> dict:
    """Recalcula en la base de datos la huella de cada evento con la del
    anterior (la misma función que usa el disparador) y dice dónde se rompe
    la cadena, si se rompe. El último eslabón es el sello que se guarda
    fuera del sistema: con él se demuestra que nada se cambió hasta ahí."""
    from sqlalchemy import text

    fila = db.execute(text("""
        WITH c AS (
            SELECT r.id, r.orden, r.fecha, r.huella, r.huella_anterior,
                   lag(r.huella) OVER (ORDER BY r.orden) AS previa,
                   lag(r.orden) OVER (ORDER BY r.orden) AS orden_previo,
                   auditoria_huella(r, lag(r.huella) OVER (ORDER BY r.orden)) AS calculada
            FROM registro_auditoria r WHERE r.orden IS NOT NULL)
        SELECT (SELECT count(*) FROM c) AS total,
               (SELECT orden FROM c WHERE huella IS DISTINCT FROM calculada
                   OR huella_anterior IS DISTINCT FROM previa
                   OR orden <> coalesce(orden_previo, 0) + 1 ORDER BY orden LIMIT 1) AS roto_en,
               (SELECT count(*) FROM registro_auditoria WHERE orden IS NULL) AS sin_encadenar,
               (SELECT orden FROM c ORDER BY orden DESC LIMIT 1) AS ultimo_orden,
               (SELECT huella FROM c ORDER BY orden DESC LIMIT 1) AS ultima_huella,
               (SELECT fecha FROM c ORDER BY orden DESC LIMIT 1) AS ultima_fecha
    """)).mappings().one()
    integra = fila["roto_en"] is None and fila["sin_encadenar"] == 0
    return {"integra": integra, "eventos": fila["total"], "roto_en": fila["roto_en"],
            "sin_encadenar": fila["sin_encadenar"],
            "sello": {"orden": fila["ultimo_orden"], "huella": fila["ultima_huella"],
                      "fecha": fila["ultima_fecha"].isoformat() if fila["ultima_fecha"] else None}}

