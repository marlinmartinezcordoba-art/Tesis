"""
Almacenamiento físico de los archivos ingestados, bajo
DIRECTORIO_ALMACENAMIENTO. Cada archivo recibe un nombre propio (su
identificador), nunca el nombre que traía, para que dos archivos con el
mismo nombre no se pisen y ningún nombre externo pueda salirse de la
carpeta.
"""

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings

TAMANO_BLOQUE = 1024 * 1024


class ExcedeLimite(Exception):
    pass


def raiz() -> Path:
    return settings.directorio_almacenamiento


def ruta_absoluta(relativa: str) -> Path:
    destino = (raiz() / relativa).resolve()
    if raiz().resolve() not in destino.parents:
        raise ValueError("Ruta fuera del almacenamiento.")
    return destino


def extension_segura(nombre: str) -> str:
    sufijo = Path(nombre).suffix.lower()
    return sufijo if sufijo and len(sufijo) <= 10 and sufijo[1:].isalnum() else ""


def guardar(origen: BinaryIO, fondo_id: uuid.UUID, instanciacion_id: uuid.UUID, nombre: str,
            limite_bytes: int) -> tuple[str, int]:
    """Copia el archivo por bloques (sin cargarlo entero en memoria) y
    devuelve (ruta relativa, bytes escritos). Si pasa el límite, borra lo
    escrito y lanza ExcedeLimite."""
    hoy = datetime.now(timezone.utc)
    relativa = f"{fondo_id}/{hoy:%Y}/{hoy:%m}/{instanciacion_id}{extension_segura(nombre)}"
    destino = ruta_absoluta(relativa)
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritos = 0
    try:
        with open(destino, "xb") as salida:
            while bloque := origen.read(TAMANO_BLOQUE):
                escritos += len(bloque)
                if escritos > limite_bytes:
                    raise ExcedeLimite()
                salida.write(bloque)
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    return relativa, escritos


def borrar(relativa: str) -> None:
    """Solo para la cancelación de un duplicado o el descarte de un error:
    el archivo nunca llegó a integrarse al fondo."""
    ruta_absoluta(relativa).unlink(missing_ok=True)


def copiar_a(relativa: str, destino: Path) -> None:
    shutil.copyfile(ruta_absoluta(relativa), destino)
