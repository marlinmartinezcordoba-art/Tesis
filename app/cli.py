"""
Comandos de administración del servidor.

    python -m app.cli cuenta-administradora

Crea o restablece la cuenta administradora a partir de las variables
RICORA_ADMIN_CORREO (o RICORA_ADMIN_USER), RICORA_ADMIN_PASSWORD y RICORA_ADMIN_NOMBRE (el
despliegue las toma de los secretos de GitHub). Se ejecuta en cada
despliegue: es la vía para recuperar el acceso si esa cuenta perdió el
rol, quedó desactivada u olvidó la contraseña sin correo configurado.
"""

import os
import sys
import uuid

from sqlalchemy import select

from app.core.seguridad import cifrar_contrasena, problemas_contrasena, verificar_contrasena
from app.db.base import ahora
from app.db.session import SessionLocal
from app.models.usuario import Usuario
from app.servicios import sesiones
from app.servicios.auditoria import Accion, registrar


def _correo_administrador() -> str:
    """RICORA_ADMIN_CORREO; si no existe, RICORA_ADMIN_USER cuando ya es un
    correo; si no, <usuario>@ricora.local, para que la cuenta de la versión
    anterior (que ingresaba con nombre de usuario) no quede sin acceso."""
    correo = (os.getenv("RICORA_ADMIN_CORREO") or "").strip().lower()
    if correo:
        return correo
    usuario = (os.getenv("RICORA_ADMIN_USER") or "").strip().lower()
    if not usuario:
        return ""
    if "@" in usuario:
        return usuario
    print("  aviso: no hay RICORA_ADMIN_CORREO; la cuenta administradora ingresa con <su usuario>@ricora.local.")
    return f"{usuario}@ricora.local"


def cuenta_administradora() -> int:
    correo = _correo_administrador()
    contrasena = os.getenv("RICORA_ADMIN_PASSWORD") or ""
    nombre = (os.getenv("RICORA_ADMIN_NOMBRE") or "").strip() or "Administración RICORA"
    if not correo or "@" not in correo:
        print("  aviso: faltan RICORA_ADMIN_CORREO y RICORA_ADMIN_USER; no se crea ni restablece la cuenta administradora.")
        return 0
    if not contrasena:
        print("  aviso: falta RICORA_ADMIN_PASSWORD; no se crea ni restablece la cuenta administradora.")
        return 0
    problemas = problemas_contrasena(contrasena)
    if problemas:
        # Se aplica igual, para no dejar el sistema sin administrador, pero
        # se avisa en el registro del despliegue.
        print("  aviso: RICORA_ADMIN_PASSWORD no cumple las reglas mínimas (" + " ".join(problemas)
              + ") — cámbiela en «Mi perfil» o en el secreto de GitHub.")

    with SessionLocal() as db:
        usuario = db.scalar(select(Usuario).where(Usuario.correo == correo))
        anterior = None
        if usuario is None:
            usuario = Usuario(id=uuid.uuid4(), nombre=nombre, correo=correo, rol="administrador", activo=True)
            db.add(usuario)
            accion = "creada"
        else:
            anterior = {"rol": usuario.rol, "activo": usuario.activo}
            accion = "restablecida"
        cambio_contrasena = not usuario.contrasena_hash or not verificar_contrasena(contrasena, usuario.contrasena_hash)
        usuario.rol = "administrador"
        usuario.activo = True
        if cambio_contrasena:
            usuario.contrasena_hash = cifrar_contrasena(contrasena)
            usuario.contrasena_cambiada_en = ahora()
        db.flush()
        if cambio_contrasena and anterior is not None:
            sesiones.cerrar_todas(db, usuario.id, "cambio_contrasena")
        nuevo = {"rol": "administrador", "activo": True, "contrasena_restablecida": cambio_contrasena}
        if anterior != {"rol": "administrador", "activo": True} or cambio_contrasena:
            registrar(db, modulo="sistema", accion=Accion.CUENTA_ADMINISTRADORA_RESTABLECIDA, usuario_id=None,
                      entidad_tipo="usuario", entidad_id=usuario.id, anterior=anterior, nuevo=nuevo,
                      detalle="Despliegue del servidor")
        db.commit()
    print(f"  Cuenta administradora {accion}" + ("." if accion == "creada" else " (contraseña restablecida)." if cambio_contrasena else " (sin cambios de contraseña)."))
    return 0


COMANDOS = {"cuenta-administradora": cuenta_administradora}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMANDOS:
        print("Uso: python -m app.cli " + "|".join(COMANDOS))
        sys.exit(2)
    sys.exit(COMANDOS[sys.argv[1]]())
