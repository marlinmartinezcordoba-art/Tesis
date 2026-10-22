"""
Segundo factor de autenticación (brecha RF-SEC-003): contraseñas de un solo
uso basadas en el tiempo, TOTP (RFC 6238, HMAC-SHA1, 6 dígitos, pasos de
30 s), las mismas que generan aplicaciones libres como Aegis, FreeOTP o
Google Authenticator. Sin dependencias nuevas: es HMAC de la biblioteca
estándar.

- Se acepta el paso actual y uno a cada lado (relojes desfasados).
- Un código ya usado no vuelve a servir (se guarda el último paso aceptado).
- Códigos de respaldo de un solo uso para cuando se pierde el teléfono; se
  guardan solo sus huellas, como las contraseñas.
- La clave se guarda cifrada (app/core/cifrado.py), atada a su cuenta: el
  sistema necesita leerla para calcular el código, así que no basta una huella.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time
import uuid
from urllib.parse import quote

from app.core import cifrado

PASO_S = 30
DIGITOS = 6
VENTANA = 1
EMISOR = "RICORA"
CODIGOS_RESPALDO = 8


def generar_secreto() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _contexto(usuario_id: uuid.UUID) -> str:
    return f"usuarios.mfa_secreto:{usuario_id}"


def guardar(secreto: str, usuario_id: uuid.UUID) -> str:
    """Lo que va en la columna: la clave cifrada y atada a la cuenta."""
    return cifrado.cifrar(secreto, _contexto(usuario_id))


def leer(guardado: str | None, usuario_id: uuid.UUID) -> str:
    """La clave en claro, o vacío si no hay ni se puede leer (otra clave, valor
    alterado o sin cifrar): entonces ningún código de la aplicación sirve y la
    persona entra con un código de respaldo o pide el restablecimiento. La
    migración 0045 cifró las claves que había en claro."""
    if not guardado:
        return ""
    try:
        return cifrado.descifrar(guardado, _contexto(usuario_id))
    except cifrado.ErrorCifrado as exc:
        logging.getLogger(__name__).error("Clave del segundo factor ilegible para %s: %s", usuario_id, exc)
        return ""


def cifrar_en_claro(conexion) -> int:
    """Cifra las claves que quedaron en claro (las de antes de la migración 0045).
    Devuelve cuántas cifró. Recibe una conexión de SQLAlchemy."""
    from sqlalchemy import text

    filas = conexion.execute(text("SELECT id, mfa_secreto FROM usuarios WHERE mfa_secreto IS NOT NULL")).all()
    cifradas = 0
    for ident, valor in filas:
        if not cifrado.cifrado(valor):
            conexion.execute(text("UPDATE usuarios SET mfa_secreto = :v WHERE id = :i"),
                             {"v": guardar(valor, ident), "i": ident})
            cifradas += 1
    return cifradas


def _clave(secreto: str) -> bytes:
    relleno = "=" * (-len(secreto) % 8)
    return base64.b32decode(secreto.upper() + relleno)


def codigo(secreto: str, paso: int) -> str:
    resumen = hmac.new(_clave(secreto), struct.pack(">Q", paso), hashlib.sha1).digest()
    desfase = resumen[-1] & 0x0F
    numero = struct.unpack(">I", resumen[desfase:desfase + 4])[0] & 0x7FFFFFFF
    return str(numero % 10 ** DIGITOS).zfill(DIGITOS)


def paso_actual(instante: float | None = None) -> int:
    return int((time.time() if instante is None else instante) // PASO_S)


def verificar(secreto: str, valor: str, ultimo_paso: int | None, instante: float | None = None) -> int | None:
    """El paso aceptado, o None. Rechaza un paso igual o anterior al último usado."""
    valor = "".join(c for c in (valor or "") if c.isdigit())
    if not secreto or len(valor) != DIGITOS:
        return None
    actual = paso_actual(instante)
    for paso in range(actual - VENTANA, actual + VENTANA + 1):
        if ultimo_paso is not None and paso <= ultimo_paso:
            continue
        if hmac.compare_digest(codigo(secreto, paso), valor):
            return paso
    return None


def uri(secreto: str, cuenta: str) -> str:
    """otpauth:// para escribir a mano o escanear: el emisor y la cuenta, no la contraseña."""
    etiqueta = quote(f"{EMISOR}:{cuenta}", safe=":@")
    return f"otpauth://totp/{etiqueta}?secret={secreto}&issuer={EMISOR}&digits={DIGITOS}&period={PASO_S}"


def huella_respaldo(valor: str) -> str:
    limpio = "".join(c for c in (valor or "").upper() if c.isalnum())
    return hashlib.sha256(limpio.encode("ascii")).hexdigest()


def nuevos_codigos_respaldo() -> list[str]:
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I/L
    return ["-".join("".join(secrets.choice(alfabeto) for _ in range(4)) for _ in range(2))
            for _ in range(CODIGOS_RESPALDO)]
