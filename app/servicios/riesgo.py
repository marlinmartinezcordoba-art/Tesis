"""
Clasificación del riesgo de obsolescencia de un formato (módulo 5).

Parte del formato ya identificado en la ingesta contra PRONOM (PUID y tipo
MIME) y lo traduce a un nivel (bajo, medio, alto) con la razón escrita en
lenguaje natural y una recomendación. Nunca una etiqueta sin argumento.

Es una tabla de reglas, no inteligencia artificial: el mismo formato da
siempre el mismo resultado y cualquiera puede leer por qué (decisión
documentada en documentacion/modulo-5-preservacion.md).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Riesgo:
    nivel: str  # bajo | medio | alto
    razon: str
    recomendacion: str | None
    destino_sugerido: str | None = None  # clave de DESTINOS en servicios/preservacion.py


PDFA = {"fmt/95", "fmt/354", "fmt/476", "fmt/477", "fmt/478", "fmt/479", "fmt/480", "fmt/481"}
TIFF = {"fmt/353", "fmt/7", "fmt/8", "fmt/9", "fmt/10"}
PNG = {"fmt/11", "fmt/12", "fmt/13"}
JPEG2000 = {"x-fmt/392"}

_BAJO_PUID = [
    (PDFA, "Es PDF/A (ISO 19005), la versión de PDF pensada para conservación a largo plazo: incrusta fuentes "
           "y perfiles de color y no depende de programas externos."),
    (TIFF, "TIFF es un formato de imagen abierto, sin pérdida y ampliamente usado por archivos para "
           "másteres de digitalización."),
    (PNG, "PNG es un formato de imagen abierto (ISO/IEC 15948), sin pérdida y bien documentado."),
    (JPEG2000, "JPEG 2000 (ISO/IEC 15444) es un estándar abierto usado para conservación de imágenes."),
]

# (prefijo MIME, nivel, razón, recomendación, destino sugerido)
_POR_MIME = [
    ("text/plain", "bajo", "El texto plano no depende de ningún programa para leerse.", None, None),
    ("text/csv", "bajo", "CSV es texto plano estructurado, legible sin programas específicos.", None, None),
    ("application/xml", "bajo", "XML es un estándar abierto y autodescriptivo.", None, None),
    ("text/xml", "bajo", "XML es un estándar abierto y autodescriptivo.", None, None),
    ("application/vnd.oasis.opendocument", "bajo", "OpenDocument (ISO/IEC 26300) es un formato abierto.", None, None),
    ("application/pdf", "medio",
     "Es PDF, pero no PDF/A: puede depender de fuentes no incrustadas, contenido externo o funciones que "
     "no se garantiza que se lean igual en el futuro.",
     "Migrar a PDF/A-2b, que conserva la apariencia del documento y es el formato de conservación de texto.",
     "pdfa_2b"),
    ("image/jpeg", "medio",
     "JPEG comprime con pérdida: cada nueva edición o conversión degrada la imagen, y no es un formato "
     "de máster de preservación.",
     "Migrar a TIFF sin pérdida para conservar un máster que no se degrade.", "tiff"),
    ("image/gif", "medio", "GIF está limitado a 256 colores y no es adecuado como máster de imagen.",
     "Migrar a TIFF sin pérdida.", "tiff"),
    ("image/bmp", "medio", "BMP es un formato de un solo fabricante, sin compresión ni metadatos adecuados.",
     "Migrar a TIFF sin pérdida.", "tiff"),
    ("image/webp", "medio", "WebP es un formato reciente, con poca adopción en archivos de conservación.",
     "Migrar a TIFF sin pérdida.", "tiff"),
    ("application/vnd.openxmlformats-officedocument", "medio",
     "Office Open XML es un estándar (ISO/IEC 29500), pero su lectura fiel depende en la práctica de un "
     "programa comercial y de sus versiones.",
     "Migrar a PDF/A para fijar la apariencia (con una herramienta externa; ver configuración).", "pdfa_2b"),
    ("application/msword", "alto",
     "Formato binario antiguo de Microsoft Word (.doc), cerrado y ya reemplazado por el propio fabricante.",
     "Migrar a PDF/A u ODT con una herramienta externa y cargar el resultado.", "pdfa_2b"),
    ("application/vnd.ms-excel", "alto",
     "Formato binario antiguo de Microsoft Excel (.xls), cerrado y ya reemplazado por el propio fabricante.",
     "Migrar a ODS o CSV con una herramienta externa y cargar el resultado.", "csv"),
    ("application/vnd.ms-powerpoint", "alto",
     "Formato binario antiguo de Microsoft PowerPoint (.ppt), cerrado y ya reemplazado por el fabricante.",
     "Migrar a PDF/A con una herramienta externa y cargar el resultado.", "pdfa_2b"),
    ("application/vnd.wordperfect", "alto", "WordPerfect es un formato en desuso, con pocos programas que lo lean.",
     "Migrar a PDF/A u ODT con una herramienta externa.", "pdfa_2b"),
]


def evaluar(puid: str | None, mime: str | None, identificado: bool) -> Riesgo:
    if not identificado or not puid:
        return Riesgo("alto", "El formato no se pudo identificar contra el registro PRONOM: no se puede planificar "
                              "su conservación sin saber qué es.",
                      "Revisar el archivo a mano, identificar su formato y, si hace falta, migrarlo cargando "
                      "una versión convertida.")
    for puids, razon in _BAJO_PUID:
        if puid in puids:
            return Riesgo("bajo", razon, None)
    mime = (mime or "").lower()
    for prefijo, nivel, razon, recomendacion, destino in _POR_MIME:
        if mime.startswith(prefijo):
            return Riesgo(nivel, razon, recomendacion, destino)
    return Riesgo("medio", f"El formato ({puid}) está identificado, pero todavía no tiene una evaluación en la tabla "
                           "de riesgo del sistema.",
                  "Revisar si es un formato adecuado para conservación a largo plazo.")
