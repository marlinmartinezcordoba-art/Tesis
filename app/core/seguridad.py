"""
Piezas criptográficas de la autenticación: contraseñas con bcrypt (vía
passlib), tokens de acceso JWT firmados con la clave del sistema, y
secretos aleatorios para renovación y enlaces de un solo uso, de los que
en la base de datos solo se guarda la huella SHA-256.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_contexto = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

ALGORITMO_JWT = "HS256"

# Hash fijo para comparar cuando el correo no existe: así el inicio de
# sesión tarda lo mismo exista o no la cuenta y el tiempo de respuesta no
# revela qué correos están registrados.
_HASH_SEÑUELO = _contexto.hash("contraseña-señuelo-que-nunca-coincide")


def cifrar_contrasena(contrasena: str) -> str:
    return _contexto.hash(contrasena)


def verificar_contrasena(contrasena: str, hash_guardado: str | None) -> bool:
    if not hash_guardado:
        _contexto.verify(contrasena, _HASH_SEÑUELO)
        return False
    try:
        return _contexto.verify(contrasena, hash_guardado)
    except ValueError:
        return False


# --- Reglas mínimas de contraseña -------------------------------------------
# Las mismas reglas se muestran en la interfaz mientras la persona escribe
# (frontend/src/lib/contrasena.ts); aquí se vuelven a verificar porque el
# backend nunca confía en lo que dice el navegador.

LONGITUD_MINIMA = 10
LONGITUD_MAXIMA = 72  # bcrypt solo usa los primeros 72 bytes

_COMUNES = {
    "contraseña", "contrasena", "password", "1234567890", "0123456789",
    "qwertyuiop", "administrador", "archivista", "colombia2024", "colombia2025",
    "colombia2026", "contraseña1", "password123", "abc1234567",
}


def problemas_contrasena(contrasena: str, correo: str | None = None) -> list[str]:
    problemas = []
    if len(contrasena) < LONGITUD_MINIMA:
        problemas.append(f"Debe tener al menos {LONGITUD_MINIMA} caracteres.")
    if len(contrasena.encode("utf-8")) > LONGITUD_MAXIMA:
        problemas.append(f"No puede superar {LONGITUD_MAXIMA} caracteres.")
    if not any(c.isalpha() for c in contrasena):
        problemas.append("Debe incluir al menos una letra.")
    if not any(c.isdigit() for c in contrasena):
        problemas.append("Debe incluir al menos un número.")
    minuscula = contrasena.lower()
    if minuscula in _COMUNES:
        problemas.append("Es una contraseña demasiado común.")
    if correo:
        usuario_correo = correo.split("@")[0].lower()
        if len(usuario_correo) >= 4 and usuario_correo in minuscula:
            problemas.append("No puede contener la parte inicial de su correo.")
    return problemas


# --- Secretos aleatorios ------------------------------------------------------


def secreto_aleatorio() -> str:
    return secrets.token_urlsafe(32)


def huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# --- Token de acceso (JWT) ----------------------------------------------------


class TokenInvalido(Exception):
    pass


@dataclass
class DatosToken:
    usuario_id: uuid.UUID
    sesion_id: uuid.UUID
    rol: str


def crear_token_acceso(usuario_id: uuid.UUID, sesion_id: uuid.UUID, rol: str) -> tuple[str, int]:
    """Devuelve (token, segundos de vigencia)."""
    ahora = datetime.now(timezone.utc)
    vigencia = timedelta(minutes=settings.minutos_token_acceso)
    carga = {
        "sub": str(usuario_id),
        "sid": str(sesion_id),
        "rol": rol,
        "typ": "acceso",
        "iat": ahora,
        "exp": ahora + vigencia,
    }
    return jwt.encode(carga, settings.secret_key, algorithm=ALGORITMO_JWT), int(vigencia.total_seconds())


def leer_token_acceso(token: str) -> DatosToken:
    try:
        carga = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITMO_JWT],
            options={"require": ["exp", "sub", "sid", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenInvalido("expirado") from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalido("invalido") from exc
    if carga.get("typ") != "acceso":
        raise TokenInvalido("invalido")
    try:
        return DatosToken(uuid.UUID(carga["sub"]), uuid.UUID(carga["sid"]), carga.get("rol", ""))
    except (ValueError, TypeError) as exc:
        raise TokenInvalido("invalido") from exc
