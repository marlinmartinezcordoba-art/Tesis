"""
Identificación del formato técnico contra el registro PRONOM de los
Archivos Nacionales del Reino Unido, con Siegfried (decisión documentada
en documentacion/modulo-1-ingesta.md). No hay identificación casera por
extensión: si Siegfried solo reconoce la extensión, el formato se marca
como no identificado.
"""

import json
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import settings


class IdentificadorNoDisponible(Exception):
    """El programa de identificación no está instalado o no responde. Es
    un problema del servidor, no del archivo."""


@dataclass
class Formato:
    identificado: bool
    puid: str | None
    nombre: str | None
    version: str | None
    mime: str | None
    base: str | None
    herramienta: str


def _ejecutar(argumentos: list[str], timeout: int) -> str:
    try:
        r = subprocess.run(argumentos, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise IdentificadorNoDisponible("No se encontró el programa Siegfried (sf).") from exc
    except subprocess.TimeoutExpired as exc:
        raise IdentificadorNoDisponible("Siegfried no respondió a tiempo.") from exc
    if r.returncode != 0 and not r.stdout:
        raise IdentificadorNoDisponible(r.stderr.decode("utf-8", "replace")[:300])
    return r.stdout.decode("utf-8", "replace")


@lru_cache
def herramienta() -> str:
    """Versión de Siegfried y del archivo de firmas PRONOM, para dejarla
    registrada con cada identificación (trazabilidad PREMIS)."""
    salida = _ejecutar([settings.siegfried_binario, "-home", settings.siegfried_home, "-version"], 30)
    lineas = [l.strip() for l in salida.splitlines() if l.strip()]
    version = lineas[0] if lineas else "siegfried"
    firmas = next((l.split(":", 1)[1].strip() for l in lineas if l.startswith("- pronom:")), "")
    return (f"{version} · PRONOM {firmas}" if firmas else version)[:200]


def identificar(ruta: Path) -> Formato:
    salida = _ejecutar(
        [settings.siegfried_binario, "-home", settings.siegfried_home, "-json", "-nr", str(ruta)],
        settings.segundos_por_paso,
    )
    try:
        datos = json.loads(salida)
        archivo = datos["files"][0]
    except (ValueError, KeyError, IndexError) as exc:
        raise IdentificadorNoDisponible("Respuesta de Siegfried no reconocida.") from exc
    coincidencias = [m for m in archivo.get("matches", []) if m.get("ns") == "pronom"] or archivo.get("matches", [])
    m = coincidencias[0] if coincidencias else {}
    puid = m.get("id") or None
    advertencia = (m.get("warning") or "").lower()
    # Sin identificador, o identificado solo por la extensión del nombre:
    # no es una identificación contra las firmas del registro.
    identificado = bool(puid) and puid.upper() != "UNKNOWN" and "extension only" not in advertencia
    return Formato(
        identificado=identificado,
        puid=puid if puid and puid.upper() != "UNKNOWN" else None,
        nombre=m.get("format") or None,
        version=m.get("version") or None,
        mime=m.get("mime") or None,
        base="; ".join(filter(None, [m.get("basis"), m.get("warning")]))[:500] or None,
        herramienta=herramienta(),
    )
