"""
Comandos de administración del servidor.

    python -m app.cli cuenta-administradora
    python -m app.cli probar-motor
    python -m app.cli probar-preservacion

Crea o restablece la cuenta administradora a partir de las variables
RICORA_ADMIN_CORREO (o RICORA_ADMIN_USER), RICORA_ADMIN_PASSWORD y RICORA_ADMIN_NOMBRE (el
despliegue las toma de los secretos de GitHub). Se ejecuta en cada
despliegue: es la vía para recuperar el acceso si esa cuenta perdió el
rol, quedó desactivada u olvidó la contraseña sin correo configurado.
"""

import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
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
        # Brecha NFR-01 (lote 3): la contraseña del secreto solo se aplica al
        # crear la cuenta o si se pide expresamente (RICORA_ADMIN_RESTABLECER=1,
        # p. ej. si nadie recuerda la contraseña). Antes cada despliegue
        # deshacía el cambio hecho en «Mi perfil».
        restablecer = os.getenv("RICORA_ADMIN_RESTABLECER", "0") == "1"
        cambio_contrasena = (not usuario.contrasena_hash or (
            restablecer and not verificar_contrasena(contrasena, usuario.contrasena_hash)))
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
    print(f"  Cuenta administradora {accion}" + ("." if accion == "creada" else " (contraseña restablecida por RICORA_ADMIN_RESTABLECER)."
                                                  if cambio_contrasena else " (su contraseña no se toca: la cambia la persona en «Mi perfil»)."))
    return 0


def probar_motor() -> int:
    """Consulta el motor de análisis con un texto corto de prueba e informa
    si responde (nunca muestra la clave)."""
    from app.servicios import motor

    activo = motor.motor_activo()
    if activo is None:
        print("  Motor de análisis: no configurado (falta GEMINI_API_KEY). La descripción funciona a mano.")
        return 0
    prueba = motor.Documento(id=uuid.uuid4(), nombre="prueba.txt",
                             texto="Acta del Concejo Municipal de Tunja, sesión del 20 de julio de 1948.")
    propuesta = motor.proponer([prueba], "unidad_documental")
    if propuesta.disponible:
        print(f"  Motor de análisis: responde ({activo.nombre}), {len(propuesta.entidades)} entidad(es) en la prueba.")
    else:
        print(f"  Motor de análisis: NO responde ({activo.nombre}): {propuesta.aviso}")
    return 0


def probar_preservacion() -> int:
    """Convierte un PDF generado en el momento a PDF/A-2b con Ghostscript y
    lo identifica con Siegfried: confirma que la migración automática
    funciona en este servidor (no toca ningún documento del fondo)."""
    import io
    import tempfile
    from pathlib import Path

    from PIL import Image

    from app.servicios import formato, preservacion

    with tempfile.TemporaryDirectory() as carpeta:
        entrada, salida = Path(carpeta) / "prueba.pdf", Path(carpeta) / "prueba_pdfa.pdf"
        buffer = io.BytesIO()
        Image.new("RGB", (200, 100), (240, 235, 220)).save(buffer, format="PDF")
        entrada.write_bytes(buffer.getvalue())
        try:
            herramienta = preservacion.CONVERSORES["ghostscript_pdfa"].ejecutar(entrada, salida)
            f = formato.identificar(salida)
        except Exception as exc:  # se informa, no se oculta
            print(f"Preservación: la conversión a PDF/A NO funciona: {exc}")
            return 1
    ok = f.puid in preservacion.DESTINOS["pdfa_2b"].puids
    print(f"Preservación: {herramienta} → {f.nombre} ({f.puid}) {'correcto' if ok else 'NO es PDF/A'}")
    return 0 if ok else 1


def restaurar_paquete(ruta: str) -> int:
    """Levanta RICORA en un servidor nuevo desde un paquete de recuperación
    (NFR-07): restaura la base en DATABASE_URL (que debe estar vacía) y los
    archivos en DIRECTORIO_ALMACENAMIENTO (vacío), y lo verifica todo."""
    from app.servicios import recuperacion

    paquete = Path(ruta)
    if not paquete.is_file():
        print(f"  No existe el paquete {ruta}.")
        return 1
    try:
        informe = recuperacion.restaurar(paquete, settings.database_url, Path(settings.directorio_almacenamiento))
    except recuperacion.ErrorRecuperacion as exc:
        print(f"  La restauración NO sirve: {exc}")
        return 1
    print(f"  Restauración completa y verificada en {informe['segundos']} s: {informe['archivos_verificados']} de "
          f"{informe['archivos']} archivos con su huella, cadena de la auditoría íntegra (evento {informe['auditoria']['orden']}).")
    print("  Siga con: alembic upgrade head (si el código es más nuevo que la migración " + informe["migracion"] + ") y levante el servicio.")
    return 0


COMANDOS = {"cuenta-administradora": cuenta_administradora, "probar-motor": probar_motor,
            "probar-preservacion": probar_preservacion}
CON_ARGUMENTO = {"restaurar-paquete": restaurar_paquete}

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in CON_ARGUMENTO:
        sys.exit(CON_ARGUMENTO[sys.argv[1]](sys.argv[2]))
    if len(sys.argv) != 2 or sys.argv[1] not in COMANDOS:
        print("Uso: python -m app.cli " + "|".join(COMANDOS) + " | restaurar-paquete <paquete.tar>")
        sys.exit(2)
    sys.exit(COMANDOS[sys.argv[1]]())
