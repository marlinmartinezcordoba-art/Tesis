"""Módulo 1 · Carga de archivos (RF-M1-01 a RF-M1-04) con la protección que
pide la arquitectura de seguridad (sección F de la auditoría): tipo de
contenido verificado contra la extensión, límite de tamaño y huella
SHA-256 calculada por bloques antes de guardar, para rechazar duplicados.

Capa de acceso a archivos desacoplada: todo se guarda a través del
`FileField` de la instanciación, es decir, del almacenamiento configurado
en `STORAGES["default"]` (hoy el sistema de archivos local). Migrar a un
almacenamiento S3-compatible (MinIO) es cambiar ese backend, no este código
ni el modelo de datos.
"""

import hashlib
import zipfile
from pathlib import Path

from django.conf import settings

from .instrumentos import _relacion_manual
from .models import EventoRiC, Instantiation, Record, registrar_evento

R_INCLUYE = "R024"

# extensión -> tipo MIME (formato técnico, especificación v5)
TIPOS_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".tif": "image/tiff", ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".xml": "application/xml",
}
FORMATOS_SOPORTADOS = sorted(TIPOS_MIME)
_TEXTO = {".txt", ".md", ".csv", ".xml"}


class ArchivoRechazado(Exception):
    """El archivo no se guarda; el mensaje se muestra tal cual en su fila."""


def tamano_maximo_bytes():
    return settings.RICORA_TAMANO_MAXIMO_MB * 1024 * 1024


def _cabecera(archivo, n=8192):
    archivo.seek(0)
    datos = archivo.read(n)
    archivo.seek(0)
    return datos


def _contenido_coincide(archivo, extension):
    """La firma del contenido (los primeros bytes) debe corresponder con la
    extensión: un .pdf que no empieza por %PDF no es un PDF, sea lo que sea."""
    cabecera = _cabecera(archivo)
    if extension == ".pdf":
        return cabecera.startswith(b"%PDF-")
    if extension == ".png":
        return cabecera.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in (".jpg", ".jpeg"):
        return cabecera.startswith(b"\xff\xd8\xff")
    if extension in (".tif", ".tiff"):
        return cabecera[:4] in (b"II*\x00", b"MM\x00*")
    if extension == ".bmp":
        return cabecera.startswith(b"BM")
    if extension == ".docx":
        if not cabecera.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(archivo) as z:
                return "word/document.xml" in z.namelist()
        except zipfile.BadZipFile:
            return False
        finally:
            archivo.seek(0)
    if extension in _TEXTO:
        if b"\x00" in cabecera:
            return False
        if extension == ".xml":
            return cabecera.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")
        return True
    return False


def validar(archivo):
    """RF-M1-03: formato, contenido y tamaño, antes de guardar nada.
    Devuelve (extension, tipo_mime) o lanza ArchivoRechazado."""
    extension = Path(archivo.name).suffix.lower()
    if extension not in TIPOS_MIME:
        raise ArchivoRechazado(
            f"formato {extension or 'sin extensión'} no soportado. Se aceptan {', '.join(FORMATOS_SOPORTADOS)}."
        )
    if archivo.size > tamano_maximo_bytes():
        raise ArchivoRechazado(
            f"pesa {archivo.size / 1024 / 1024:.1f} MB y el máximo es {settings.RICORA_TAMANO_MAXIMO_MB} MB."
        )
    if archivo.size == 0:
        raise ArchivoRechazado("el archivo está vacío.")
    if not _contenido_coincide(archivo, extension):
        raise ArchivoRechazado(
            f"el contenido no corresponde a un archivo {extension}: la extensión no coincide con lo que realmente es."
        )
    return extension, TIPOS_MIME[extension]


def huella(archivo):
    """SHA-256 por bloques (RF-M1-02), sin cargar el archivo en memoria."""
    h = hashlib.sha256()
    archivo.seek(0)
    for bloque in archivo.chunks(1024 * 1024) if hasattr(archivo, "chunks") else iter(lambda: archivo.read(1 << 20), b""):
        h.update(bloque)
    archivo.seek(0)
    return h.hexdigest()


def duplicado_de(sha256):
    return Instantiation.objects.filter(sha256=sha256).select_related("record_resource").first()


def nombre_documento(archivo):
    return Path(archivo.name).stem.replace("_", " ").strip() or archivo.name


def registrar_archivo(archivo, usuario, expediente=None, record=None, nombre_doc="", reemplaza=None):
    """Valida, calcula la huella, rechaza duplicados y guarda el archivo como
    instanciación (RiC-E06) de un documento (RiC-E04) del expediente. Con
    `record`, el archivo es una parte más de ese documento; con `reemplaza`,
    es un reescaneo derivado de otra instanciación (RiC-R015). Devuelve la
    instanciación creada o lanza ArchivoRechazado."""
    _, tipo_mime = validar(archivo)
    sha256 = huella(archivo)
    previa = duplicado_de(sha256)
    if previa is not None:
        raise ArchivoRechazado(
            f"ya fue ingerido antes (misma huella SHA-256) como «{previa.nombre}» del documento «{previa.record_resource}»."
        )
    if reemplaza is not None:
        record = Record.objects.get(pk=reemplaza.record_resource_id)
    if record is None:
        if expediente is None:
            raise ArchivoRechazado("falta el expediente al que pertenece.")
        record = Record.objects.create(
            nombre=nombre_doc or nombre_documento(archivo), record_set=expediente, creado_por=usuario,
            serie_trd=expediente.serie_trd,
        )
        _relacion_manual(expediente, record, R_INCLUYE, usuario)
    instanciacion = Instantiation(
        nombre=archivo.name, record_resource=record, archivo=archivo, creado_por=usuario,
        sha256=sha256, tipo_mime=tipo_mime, instanciacion_origen=reemplaza,
    )
    instanciacion.save()
    detalle = {
        "archivo": archivo.name, "formato": instanciacion.formato, "tipo_mime": tipo_mime,
        "tamano_bytes": instanciacion.tamano_bytes, "sha256": sha256,
    }
    if expediente is not None:
        detalle.update(expediente=expediente.nombre, serie=expediente.serie_trd)
    if reemplaza is not None:
        detalle["reescaneo_de"] = reemplaza.nombre
    # RF-M1-04: usuario, fecha y hora de cada carga, en la bitácora encadenada.
    registrar_evento(instanciacion, EventoRiC.Tipo.INGESTA, agente=usuario, detalle=detalle)
    return instanciacion
