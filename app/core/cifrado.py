"""
Cifrado de datos secretos que el sistema necesita leer de vuelta (hoy, la
clave del segundo factor). Las contraseñas y los códigos de respaldo no pasan
por aquí: de ellos solo se guarda la huella, que no se puede revertir.

- AES-256-GCM (cifrado autenticado): alterar el valor guardado hace fallar el
  descifrado, no lo cambia en silencio.
- La clave sale de RICORA_CLAVE_CIFRADO, que el despliegue genera una vez y
  guarda solo en el .env del servidor: no está en la base ni en el paquete de
  recuperación. Quien se lleva un volcado de la base o un respaldo no puede
  leer los secretos. Sin esa variable (desarrollo y pruebas), la clave se
  deriva de RICORA_SECRET_KEY.
- Cada valor dice con qué clave se cifró (huella corta de la clave): con otra
  clave, el error lo dice en vez de devolver basura.
- El dato asociado ata el valor a su columna y a su fila: copiar el secreto
  cifrado de una cuenta a otra no sirve.

Formato guardado: «c1:<huella de la clave>:<base64 de nonce + cifrado>».
"""

import base64
import hashlib
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

VERSION = "c1"


class ErrorCifrado(Exception):
    pass


def _material() -> str:
    return settings.clave_cifrado or settings.secret_key


def _clave() -> bytes:
    material = _material()
    if len(material) < 32:
        raise ErrorCifrado("Falta RICORA_CLAVE_CIFRADO (o RICORA_SECRET_KEY) de al menos 32 caracteres.")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"ricora/datos-cifrados/v1").derive(material.encode("utf-8"))


def huella_clave() -> str:
    return hashlib.sha256(_clave()).hexdigest()[:8]


def cifrado(valor: str | None) -> bool:
    return bool(valor) and valor.startswith(VERSION + ":")


def cifrar(texto: str, contexto: str) -> str:
    nonce = secrets.token_bytes(12)
    datos = AESGCM(_clave()).encrypt(nonce, texto.encode("utf-8"), contexto.encode("utf-8"))
    return f"{VERSION}:{huella_clave()}:{base64.b64encode(nonce + datos).decode('ascii')}"


def descifrar(valor: str, contexto: str) -> str:
    try:
        version, huella, cuerpo = valor.split(":", 2)
    except ValueError as exc:
        raise ErrorCifrado("El valor no está cifrado con el formato del sistema.") from exc
    if version != VERSION:
        raise ErrorCifrado(f"Versión de cifrado desconocida: {version}.")
    if huella != huella_clave():
        raise ErrorCifrado("El valor se cifró con otra clave: revise RICORA_CLAVE_CIFRADO en el .env.")
    crudo = base64.b64decode(cuerpo)
    try:
        return AESGCM(_clave()).decrypt(crudo[:12], crudo[12:], contexto.encode("utf-8")).decode("utf-8")
    except InvalidTag as exc:
        raise ErrorCifrado("El valor cifrado fue alterado o no corresponde a este registro.") from exc
