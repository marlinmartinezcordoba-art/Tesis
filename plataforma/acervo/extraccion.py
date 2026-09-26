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

Las funciones de esta primera sección trabajan por página y no dependen de
un `Documento` de `acervo`: las reutiliza `ric.extraccion` para poblar
`PaginaTexto` de una `Instantiation`, así la evidencia (RiC-CM: "página,
fragmento") puede señalar la página exacta, no solo el documento entero.
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


def ocr_imagen(imagen):
    """Devuelve (texto, lista de confianzas por palabra) de una sola imagen."""
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


def leer_texto(ruta):
    datos = ruta.read_bytes()
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return datos.decode("latin-1")


def herramienta_ocr():
    return f"Tesseract {pytesseract.get_tesseract_version()} ({IDIOMA_OCR})"


def paginas_de_imagen(ruta):
    """Una imagen (o un TIFF multipágina) como lista de páginas:
    [{"texto": str, "confianzas": [float, ...], "ocr": True}, ...]."""
    paginas = []
    with Image.open(ruta) as img:
        for cuadro in ImageSequence.Iterator(img):
            texto, confianzas = ocr_imagen(cuadro)
            paginas.append({"texto": texto, "confianzas": confianzas, "ocr": True})
    return paginas


def paginas_de_pdf(ruta):
    """Un PDF como lista de páginas; cada página usa su capa de texto si la
    tiene, o OCR sobre sus imágenes si no."""
    paginas = []
    reader = PdfReader(ruta)
    for pagina in reader.pages:
        texto = (pagina.extract_text() or "").strip()
        confianzas, uso_ocr = [], False
        if len(texto) < MIN_CARACTERES_PAGINA and pagina.images:
            uso_ocr = True
            partes = []
            for imagen in pagina.images:
                t, c = ocr_imagen(imagen.image)
                partes.append(t)
                confianzas += c
            texto = "\n".join(partes)
        paginas.append({"texto": texto, "confianzas": confianzas, "ocr": uso_ocr})
    return paginas


def paginas_de_texto_plano(ruta):
    return [{"texto": leer_texto(ruta), "confianzas": [], "ocr": False}]


def extraer_paginas(ruta):
    """Despacha por extensión y devuelve la lista de páginas (ver
    `paginas_de_pdf`/`paginas_de_imagen`/`paginas_de_texto_plano`).
    Lanza `FormatoNoSoportado` si la extensión no se reconoce."""
    ruta = Path(ruta)
    extension = ruta.suffix.lower()
    if extension in EXT_TEXTO:
        return paginas_de_texto_plano(ruta)
    if extension == ".pdf":
        return paginas_de_pdf(ruta)
    if extension in EXT_IMAGEN:
        return paginas_de_imagen(ruta)
    raise FormatoNoSoportado(f"No se puede extraer texto de archivos {extension}")


def resumir_paginas(paginas):
    """A partir de la lista de páginas, arma el mismo `detalle` que registraba
    la versión anterior de `extraer_texto` (método, páginas, confianza, ...)."""
    texto = "\n\n".join(p["texto"] for p in paginas)
    confianzas = [c for p in paginas for c in p["confianzas"]]
    paginas_ocr = sum(1 for p in paginas if p["ocr"])
    confianza = round(sum(confianzas) / len(confianzas), 1) if confianzas else None
    detalle = {
        "metodo": "ocr" if paginas_ocr else "lectura_directa",
        "paginas": len(paginas),
        "paginas_ocr": paginas_ocr,
        "caracteres": len(texto),
        "confianza_ocr": confianza,
    }
    if paginas_ocr:
        detalle["herramienta"] = herramienta_ocr()
    return texto, detalle


def extraer_texto(documento, agente="sistema"):
    paginas = extraer_paginas(documento.archivo.path)
    texto, detalle = resumir_paginas(paginas)

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
