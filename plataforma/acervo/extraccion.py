"""Extracción de texto de los documentos del acervo.

Es el primer paso de la automatización asistida: la clasificación, la
descripción, la valoración y el control de acceso trabajan sobre este texto.

Estrategia:
- archivos de texto: se leen directamente;
- PDF: se usa la capa de texto; las páginas escaneadas (sin texto) pasan por OCR;
- imágenes (JPG, PNG, TIFF): OCR con Tesseract en español.

Cada extracción queda en la bitácora con el método, la herramienta, su versión
y la confianza media del OCR, para que la persona archivista sepa cuánto
confiar en el texto y cuándo revisarlo.
"""

from pathlib import Path

import pytesseract
from PIL import Image, ImageSequence
from pypdf import PdfReader

from .models import EventoPreservacion, registrar_evento

IDIOMA_OCR = "spa"
EXT_TEXTO = {".txt", ".csv", ".xml", ".md"}
EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
MIN_CARACTERES_PAGINA = 20  # por debajo, la página se considera escaneada


class FormatoNoSoportado(Exception):
    pass


def _ocr_imagen(imagen):
    """Devuelve (texto, lista de confianzas por palabra)."""
    imagen = imagen.convert("L")
    datos = pytesseract.image_to_data(
        imagen, lang=IDIOMA_OCR, output_type=pytesseract.Output.DICT
    )
    confianzas = [
        float(c) for c, palabra in zip(datos["conf"], datos["text"])
        if palabra.strip() and float(c) >= 0
    ]
    texto = pytesseract.image_to_string(imagen, lang=IDIOMA_OCR)
    return texto.strip(), confianzas


def _leer_texto(ruta):
    datos = ruta.read_bytes()
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return datos.decode("latin-1")


def _extraer_imagen(ruta):
    textos, confianzas = [], []
    with Image.open(ruta) as img:
        for pagina in ImageSequence.Iterator(img):  # TIFF multipágina
            t, c = _ocr_imagen(pagina)
            textos.append(t)
            confianzas += c
    return "\n\n".join(textos), confianzas, len(textos), len(textos)


def _extraer_pdf(ruta):
    textos, confianzas, paginas_ocr = [], [], 0
    reader = PdfReader(ruta)
    for pagina in reader.pages:
        texto = (pagina.extract_text() or "").strip()
        if len(texto) < MIN_CARACTERES_PAGINA and pagina.images:
            paginas_ocr += 1
            partes = []
            for imagen in pagina.images:
                t, c = _ocr_imagen(imagen.image)
                partes.append(t)
                confianzas += c
            texto = "\n".join(partes)
        textos.append(texto)
    return "\n\n".join(textos), confianzas, len(reader.pages), paginas_ocr


def extraer_texto(documento, agente="sistema"):
    ruta = Path(documento.archivo.path)
    extension = ruta.suffix.lower()

    if extension in EXT_TEXTO:
        texto, confianzas, paginas, paginas_ocr = _leer_texto(ruta), [], 1, 0
    elif extension == ".pdf":
        texto, confianzas, paginas, paginas_ocr = _extraer_pdf(ruta)
    elif extension in EXT_IMAGEN:
        texto, confianzas, paginas, paginas_ocr = _extraer_imagen(ruta)
    else:
        raise FormatoNoSoportado(f"No se puede extraer texto de archivos {extension}")

    confianza = round(sum(confianzas) / len(confianzas), 1) if confianzas else None
    detalle = {
        "metodo": "ocr" if paginas_ocr else "lectura_directa",
        "paginas": paginas,
        "paginas_ocr": paginas_ocr,
        "caracteres": len(texto),
        "confianza_ocr": confianza,
    }
    if paginas_ocr:
        detalle["herramienta"] = f"Tesseract {pytesseract.get_tesseract_version()} ({IDIOMA_OCR})"

    documento.texto_extraido = texto
    if documento.publicado:
        # El texto cambió: la revisión de datos personales ya no aplica y
        # el documento sale del portal hasta que se revise de nuevo.
        detalle["publicacion_retirada"] = True
    documento.publicado = False
    documento.texto_publico = ""
    documento.save(update_fields=["texto_extraido", "publicado", "texto_publico"])
    registrar_evento(documento, EventoPreservacion.Tipo.EXTRACCION, agente=agente, detalle=detalle)
    return texto, detalle
