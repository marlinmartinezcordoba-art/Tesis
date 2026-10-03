"""
Extracción del texto que después usa el motor de descripción.

- Documentos con capa de texto (PDF digital, texto plano, Word, OpenDocument):
  se toma el texto que ya traen.
- Imágenes y PDF escaneados (sin capa de texto): reconocimiento óptico de
  caracteres con Tesseract, página por página. Tesseract devuelve, en la
  misma pasada, el texto y su tabla de palabras con la confianza de cada
  una (0 a 100); la confianza del documento es el promedio de todas sus
  palabras, en todas sus páginas. Sin OCR (capa de texto) la confianza
  queda vacía, no en cero: cero sería una extracción fallida.
- Cualquier otro formato: se acepta sin texto; no es un error.

Un archivo dañado o ilegible lanza ArchivoIlegible con un mensaje en
lenguaje sencillo.
"""

import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

from app.core.config import settings

# Límite de texto guardado por documento (unos 5 millones de caracteres):
# basta para cualquier documento de archivo y protege la base de datos.
MAXIMO_CARACTERES = 5_000_000
# Por debajo de este promedio de caracteres por página, un PDF se considera
# escaneado (sin capa de texto útil) y se le aplica OCR.
MINIMO_CARACTERES_POR_PAGINA = 25

EXT_TEXTO = {".txt", ".csv", ".tsv", ".md", ".xml", ".html", ".htm", ".json", ".eml"}
EXT_IMAGEN = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".jp2", ".j2k"}
EXT_OFFICE = {".docx": "word/document.xml", ".odt": "content.xml"}

Progreso = Callable[[int, str], None]  # (porcentaje dentro del paso, detalle)


class ArchivoIlegible(Exception):
    """El archivo está dañado o no se puede leer."""


class OcrNoDisponible(Exception):
    """Tesseract no está instalado o no responde: problema del servidor."""


@dataclass
class Texto:
    contenido: str | None
    origen: str  # capa_de_texto | ocr | sin_texto
    paginas: int | None = None
    confianza_ocr: float | None = None  # 0 a 100; solo si hubo OCR
    palabras_ocr: int | None = None  # cuántas palabras sostienen ese promedio


@dataclass
class Lectura:
    """Lo que devuelve una pasada de Tesseract sobre una imagen."""

    texto: str
    confianzas: list[float]  # una por palabra reconocida


def promedio(lecturas: list[Lectura]) -> tuple[float | None, int]:
    """Promedio de confianza por palabra de todo el documento. Si el OCR no
    reconoció ninguna palabra, la confianza es 0: la extracción falló."""
    todas = [c for lectura in lecturas for c in lectura.confianzas]
    if not todas:
        return 0.0, 0
    return round(sum(todas) / len(todas), 1), len(todas)


def _confianzas_tsv(tsv: str) -> list[float]:
    """Confianza de cada palabra en la tabla TSV de Tesseract. Las filas de
    página, bloque, párrafo y línea traen -1 y no cuentan; tampoco las
    palabras vacías."""
    salida = []
    for i, linea in enumerate(tsv.splitlines()):
        partes = linea.split("\t")
        if i == 0 or len(partes) < 12 or partes[0] != "5":  # nivel 5 = palabra
            continue
        try:
            conf = float(partes[10])
        except ValueError:
            continue
        if conf >= 0 and partes[11].strip():
            salida.append(conf)
    return salida


def _limpiar(texto: str) -> str:
    texto = texto.replace("\x00", "")
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()[:MAXIMO_CARACTERES]


def _tipo(ruta: Path, mime: str | None) -> str:
    ext = ruta.suffix.lower()
    mime = (mime or "").lower()
    if mime == "application/pdf" or ext == ".pdf":
        return "pdf"
    if ext in EXT_OFFICE:
        return "office"
    if mime.startswith("image/") or ext in EXT_IMAGEN:
        return "imagen"
    if mime.startswith("text/") or ext in EXT_TEXTO:
        return "texto"
    return "otro"


def _texto_plano(ruta: Path) -> Texto:
    datos = ruta.read_bytes()[: MAXIMO_CARACTERES * 4]
    for codificacion in ("utf-8", "cp1252"):
        try:
            return Texto(_limpiar(datos.decode(codificacion)) or None, "capa_de_texto")
        except UnicodeDecodeError:
            continue
    return Texto(_limpiar(datos.decode("latin-1")) or None, "capa_de_texto")


def _office(ruta: Path) -> Texto:
    try:
        with zipfile.ZipFile(ruta) as z:
            xml = z.read(EXT_OFFICE[ruta.suffix.lower()])
        raiz = ElementTree.fromstring(xml)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError) as exc:
        raise ArchivoIlegible("El documento no se pudo abrir; puede estar dañado.") from exc
    parrafos = []
    for elemento in raiz.iter():
        etiqueta = elemento.tag.rsplit("}", 1)[-1]
        if etiqueta in ("p", "h"):  # párrafos de Word y de OpenDocument
            parrafos.append("".join(elemento.itertext()))
    return Texto(_limpiar("\n".join(parrafos)) or None, "capa_de_texto")


def _tesseract(imagen: Path) -> Lectura:
    """Una sola pasada de Tesseract que escribe el texto (txt) y la tabla de
    palabras con su confianza (tsv)."""
    with tempfile.TemporaryDirectory(prefix="ricora-tess-") as tmp:
        base = Path(tmp) / "salida"
        _ejecutar_tesseract(imagen, base)
        texto = base.with_suffix(".txt").read_text("utf-8", "replace") if base.with_suffix(".txt").exists() else ""
        tsv = base.with_suffix(".tsv").read_text("utf-8", "replace") if base.with_suffix(".tsv").exists() else ""
    return Lectura(texto, _confianzas_tsv(tsv))


# Tesseract usa OpenMP: con varios procesos a la vez (trabajador, pruebas en
# paralelo, servidor pequeño) los hilos compiten y una página que tarda dos
# segundos puede pasar del límite de tiempo. Un hilo por proceso lo vuelve
# predecible; es la configuración que recomienda el propio proyecto cuando
# se ejecutan varias instancias.
ENTORNO_TESSERACT = {"OMP_THREAD_LIMIT": "1"}


def _ejecutar_tesseract(imagen: Path, base: Path) -> None:
    try:
        r = subprocess.run(
            ["tesseract", str(imagen), str(base), "-l", settings.idioma_ocr, "txt", "tsv"],
            capture_output=True, timeout=settings.segundos_por_paso, check=False,
            env=os.environ | ENTORNO_TESSERACT,
        )
    except FileNotFoundError as exc:
        raise OcrNoDisponible("No se encontró el programa de OCR (Tesseract).") from exc
    except subprocess.TimeoutExpired as exc:
        raise ArchivoIlegible("El reconocimiento de texto tardó demasiado en una página.") from exc
    if r.returncode != 0:
        error = r.stderr.decode("utf-8", "replace").lower()
        if "failed loading language" in error or "tessdata" in error:
            raise OcrNoDisponible(f"Falta el idioma «{settings.idioma_ocr}» del OCR en el servidor.")
        raise ArchivoIlegible("La imagen no se pudo leer; puede estar dañada o en un formato de imagen no compatible con el OCR.")


def _imagen(ruta: Path, progreso: Progreso) -> Texto:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(ruta) as img:
            paginas = getattr(img, "n_frames", 1)
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        # Formatos que Pillow no abre (p. ej. JPEG 2000 sin soporte) se
        # intentan igual con Tesseract, que tiene sus propios lectores.
        if ruta.suffix.lower() not in (".jp2", ".j2k"):
            raise ArchivoIlegible("La imagen no se pudo leer; puede estar dañada.") from exc
        paginas = 1
    progreso(10, f"Reconociendo texto (OCR) · {paginas} página{'s' if paginas != 1 else ''}")
    lectura = _tesseract(ruta)
    confianza, palabras = promedio([lectura])
    return Texto(_limpiar(lectura.texto) or None, "ocr", paginas, confianza, palabras)


def _pdf(ruta: Path, progreso: Progreso) -> Texto:
    import pypdfium2 as pdfium

    try:
        documento = pdfium.PdfDocument(str(ruta))
    except pdfium.PdfiumError as exc:
        raise ArchivoIlegible("El PDF no se pudo abrir; puede estar dañado o protegido con contraseña.") from exc
    try:
        total = len(documento)
        if total == 0:
            raise ArchivoIlegible("El PDF no tiene páginas.")
        capa = []
        for i in range(total):
            pagina = documento[i]
            capa.append(pagina.get_textpage().get_text_range())
        texto_capa = _limpiar("\n\n".join(capa))
        if len(texto_capa) >= MINIMO_CARACTERES_POR_PAGINA * total:
            return Texto(texto_capa, "capa_de_texto", total)

        # Escaneado: OCR página por página, sin guardar nada en disco más
        # que la imagen temporal de la página en curso.
        partes = []
        escala = settings.dpi_ocr / 72
        with tempfile.TemporaryDirectory(prefix="ricora-ocr-") as tmp:
            for i in range(total):
                progreso(int(100 * i / total), f"Reconociendo texto (OCR) · página {i + 1} de {total}")
                imagen = documento[i].render(scale=escala, grayscale=True).to_pil()
                destino = Path(tmp) / "pagina.png"
                imagen.save(destino)
                imagen.close()
                partes.append(_tesseract(destino))
        confianza, palabras = promedio(partes)
        return Texto(_limpiar("\n\n".join(p.texto for p in partes)) or None, "ocr", total, confianza, palabras)
    finally:
        documento.close()


def extraer(ruta: Path, mime: str | None, progreso: Progreso) -> Texto:
    if ruta.stat().st_size == 0:
        raise ArchivoIlegible("El archivo está vacío.")
    tipo = _tipo(ruta, mime)
    if tipo == "pdf":
        return _pdf(ruta, progreso)
    if tipo == "imagen":
        return _imagen(ruta, progreso)
    if tipo == "office":
        return _office(ruta)
    if tipo == "texto":
        return _texto_plano(ruta)
    return Texto(None, "sin_texto")
