"""
Salud del sistema (brechas RF-OPS-001 y NFR-10): qué tan bien está cada
pieza, en un formato que un monitor externo gratuito puede consultar cada
pocos minutos sin sesión.

- base de datos: responde y tiene las migraciones al día;
- almacén de archivos: existe, se puede escribir y le queda espacio;
- trabajador: dejó su latido hace poco (procesa la ingesta, verifica la
  integridad, hace los respaldos);
- respaldo: el último respaldo con simulacro correcto no está atrasado;
- conexión: la dirección pública usa HTTPS (lote 3, NFR-01). Si el despliegue
  tuvo que quedarse en HTTP, se dice aquí y no solo en su registro.

Solo la base de datos decide el código HTTP (503 si no responde): sin ella
nada funciona. Lo demás deja el estado en «degradado» con el motivo, sin
tumbar el servicio. No dice rutas, versiones ni datos del archivo.
"""

import os
import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora

ARCHIVO_LATIDO = ".latido-trabajador"
LATIDO_MAXIMO_S = 180
ESPACIO_MINIMO = 0.05  # fracción libre del disco del almacén


def latir() -> None:
    """La llama el trabajador en cada vuelta: toca un archivo en el almacén,
    que comparte con la aplicación (mismo volumen)."""
    try:
        ruta = Path(settings.directorio_almacenamiento) / ARCHIVO_LATIDO
        ruta.touch(exist_ok=True)
        os.utime(ruta, None)
    except OSError:
        pass  # si el almacén no se puede escribir, la salud lo dirá


def _base(db: Session) -> dict:
    try:
        db.execute(text("SELECT 1"))
        version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return {"ok": True, "migracion": version}
    except Exception:  # noqa: BLE001 — cualquier fallo de la base es «no responde»
        return {"ok": False, "motivo": "La base de datos no responde."}


def _almacen() -> dict:
    raiz = Path(settings.directorio_almacenamiento)
    if not raiz.is_dir():
        return {"ok": False, "motivo": "El almacén de archivos no existe."}
    try:
        with tempfile.NamedTemporaryFile(dir=raiz, prefix=".salud-"):
            pass
    except OSError:
        return {"ok": False, "motivo": "No se puede escribir en el almacén de archivos."}
    uso = shutil.disk_usage(raiz)
    libre = uso.free / uso.total if uso.total else 0
    if libre < ESPACIO_MINIMO:
        return {"ok": False, "libre": round(libre * 100, 1), "motivo": f"Queda {libre:.0%} de espacio en el disco."}
    return {"ok": True, "libre": round(libre * 100, 1)}


def _trabajador() -> dict:
    ruta = Path(settings.directorio_almacenamiento) / ARCHIVO_LATIDO
    if not ruta.exists():
        return {"ok": False, "motivo": "El trabajador no ha dado señales de vida."}
    hace = int(time.time() - ruta.stat().st_mtime)
    if hace > LATIDO_MAXIMO_S:
        return {"ok": False, "hace_segundos": hace, "motivo": f"El trabajador no responde desde hace {hace // 60} min."}
    return {"ok": True, "hace_segundos": hace}


def _respaldo(db: Session) -> dict:
    from app.servicios import parametros, respaldo

    try:
        probado = respaldo.ultimo_probado(db)
        horas = int(parametros.leer(db, "respaldo_frecuencia_horas"))
    except Exception:  # noqa: BLE001
        return {"ok": False, "motivo": "No se pudo consultar el último respaldo."}
    if probado is None:
        return {"ok": False, "motivo": "Todavía no hay un respaldo con simulacro de restauración correcto."}
    atraso = ahora() - probado.iniciado_en
    if atraso > timedelta(hours=horas * 2):
        return {"ok": False, "hace_horas": int(atraso.total_seconds() // 3600),
                "motivo": "El último respaldo probado está atrasado."}
    return {"ok": True, "hace_horas": int(atraso.total_seconds() // 3600)}


LOCALES = {"localhost", "127.0.0.1", "::1"}


def _conexion() -> dict:
    url = urlsplit(settings.url_publica)
    if url.scheme == "https":
        return {"ok": True, "cifrada": True}
    if (url.hostname or "") in LOCALES:
        return {"ok": True, "cifrada": False, "nota": "Instalación local, sin HTTPS."}
    return {"ok": False, "cifrada": False,
            "motivo": "RICORA se publica sin HTTPS: no cargue documentos clasificados o reservados."}


def estado(db: Session) -> tuple[int, dict]:
    base = _base(db)
    piezas = {"base_de_datos": base, "conexion": _conexion()}
    if base["ok"]:
        piezas |= {"almacen": _almacen(), "trabajador": _trabajador(), "respaldo": _respaldo(db)}
    else:
        piezas |= {"almacen": _almacen(), "trabajador": _trabajador()}
    if not base["ok"]:
        general = "caido"
    elif all(p["ok"] for p in piezas.values()):
        general = "ok"
    else:
        general = "degradado"
    return (503 if general == "caido" else 200), {"estado": general, "fecha": ahora().isoformat(), **piezas}
