"""
Lectura de una TRD, una TVD o un CCD en cualquier estructura, con el motor de análisis.

Las tablas de retención cambian de forma con los años: columnas en otro orden, encabezados
girados, celdas combinadas, el código de la dependencia en el encabezado de la página. Cuando
la lectura por reglas (cuadro.py) no saca filas limpias, el texto del archivo pasa al motor,
que devuelve las filas en la estructura de la plantilla del sistema. No inventa: lo que no
está en el documento queda vacío, y la archivista revisa cada fila antes de crear nada
(el mismo paso 2 de siempre). Una TRD no lleva datos personales; aun así el texto pasa por
el mismo filtro de identificadores que la descripción.
"""

import io

from app.servicios import motor as servicio_motor

MAX_CARACTERES = 80_000

INSTRUCCION = """Eres un archivista colombiano experto en Tablas de Retención Documental (TRD), Tablas de Valoración
Documental (TVD) y Cuadros de Clasificación Documental (CCD) según el Acuerdo 004 de 2019 del AGN.
Recibes el texto de un archivo (extraído de un PDF, Excel o Word; puede venir desordenado, con encabezados
girados o al revés, celdas combinadas y saltos de línea). Devuelve una fila por cada serie o subserie.

Reglas:
1. La sección es la dependencia productora («Oficina productora», «Dependencia»); su código suele estar en el
   encabezado o como primer número del código de la serie (p. ej. 1000 en 1000-12.3). Repite la sección en cada fila.
2. El código de la serie y de la subserie va como aparece (p. ej. «12» y «12.3», o «1000-12» y «1000-12.3»).
3. Los tipos documentales van en una lista; si no hay, lista vacía.
4. Retención: años en archivo de gestión (ag) y en archivo central (ac); números enteros o null si no hay.
5. Disposición final: marca ct (conservación total), e (eliminación), s (selección), m (microfilmación o
   digitalización) según las X o marcas de cada fila; pueden ir varias.
6. El procedimiento va completo, como texto.
7. Ignora encabezados, títulos, firmas, convenciones, fechas de aprobación y notas al pie: no son filas.
8. No inventes. Si un dato no está en el texto, déjalo vacío o null."""

ESQUEMA = {
    "type": "OBJECT",
    "properties": {"filas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "codigo_seccion": {"type": "STRING"}, "seccion": {"type": "STRING"},
        "codigo_subseccion": {"type": "STRING"}, "subseccion": {"type": "STRING"},
        "codigo_serie": {"type": "STRING"}, "serie": {"type": "STRING"},
        "codigo_subserie": {"type": "STRING"}, "subserie": {"type": "STRING"},
        "tipos": {"type": "ARRAY", "items": {"type": "STRING"}},
        "ag": {"type": "INTEGER", "nullable": True}, "ac": {"type": "INTEGER", "nullable": True},
        "ct": {"type": "BOOLEAN"}, "e": {"type": "BOOLEAN"}, "s": {"type": "BOOLEAN"}, "m": {"type": "BOOLEAN"},
        "procedimiento": {"type": "STRING"},
    }, "required": ["seccion", "serie"]}}},
    "required": ["filas"],
}


def disponible() -> bool:
    return servicio_motor.motor_activo() is not None


def _tesseract(imagen, *opciones: str, segundos: int = 120) -> str:
    import os
    import subprocess

    from app.servicios.texto import ENTORNO_TESSERACT

    try:
        r = subprocess.run(["tesseract", str(imagen), "-", *opciones], capture_output=True, timeout=segundos,
                           env=os.environ | ENTORNO_TESSERACT, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""


def _giro(imagen) -> int:
    """Grados que hay que girar la página escaneada (0, 90, 180 o 270), según la detección de
    orientación de Tesseract. Las TRD antiguas se escanean a menudo de lado."""
    import re

    salida = _tesseract(imagen, "--psm", "0", segundos=60)
    m = re.search(r"Rotate:\s*(\d+)", salida)
    return int(m.group(1)) % 360 if m else 0


def _ocr_pdf(contenido: bytes) -> str:
    """El texto de un PDF escaneado (imágenes sin texto). Cada página se endereza si vino de lado
    y se lee conservando la disposición de las filas (cada fila de la tabla en su renglón, con
    sus espacios), para que la IA pueda rearmar las columnas. Se lee una copia temporal: el
    original no se modifica, así su huella y su autenticidad se conservan."""
    import tempfile
    from pathlib import Path

    import pypdfium2 as pdfium

    from app.core.config import settings

    partes = []
    documento = pdfium.PdfDocument(contenido)
    try:
        with tempfile.TemporaryDirectory(prefix="ricora-trd-ocr-") as tmp:
            ruta = Path(tmp) / "pagina.png"
            for i in range(len(documento)):
                imagen = documento[i].render(scale=settings.dpi_ocr / 72, grayscale=True).to_pil()
                imagen.save(ruta)
                giro = _giro(ruta)
                if giro:
                    imagen.rotate(-giro, expand=True).save(ruta)
                imagen.close()
                texto = _tesseract(ruta, "-l", settings.idioma_ocr, "--psm", "6", "-c", "preserve_interword_spaces=1")
                partes.append(f"[Página {i + 1}]\n{texto.strip()}")
                if sum(len(x) for x in partes) > MAX_CARACTERES:
                    break
    finally:
        documento.close()
    return "\n\n".join(partes)


def es_escaneado(contenido: bytes) -> bool:
    """Si el PDF casi no trae texto: son imágenes y hay que pasarle OCR."""
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            paginas = len(pdf.pages) or 1
            caracteres = 0
            for p in pdf.pages:
                caracteres += len((p.extract_text() or "").strip())
                p.close()
    except Exception:  # noqa: BLE001 — un PDF que ni se abre no es «escaneado»
        return False
    return caracteres < 40 * paginas


def texto_de(contenido: bytes, nombre: str, hojas: list | None = None) -> str:
    """El texto del archivo: el de cada página de un PDF (con OCR si es escaneado); en Excel,
    Word o CSV, sus celdas por fila."""
    if nombre.lower().endswith(".pdf") and es_escaneado(contenido):
        return _ocr_pdf(contenido)[:MAX_CARACTERES]
    if nombre.lower().endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            partes = []
            for i, p in enumerate(pdf.pages, start=1):
                partes.append(f"[Página {i}]\n{p.extract_text() or ''}")
                p.close()  # libera la memoria de la página
                if sum(len(x) for x in partes) > MAX_CARACTERES:
                    break
            texto = "\n\n".join(partes)
    else:
        texto = "\n".join(" | ".join(c for c in fila if c) for hoja in (hojas or []) for fila in hoja)
    return texto[:MAX_CARACTERES]


def extraer(contenido: bytes, nombre: str, hojas: list | None = None):
    """Las filas de la tabla leídas por el motor, ya en la estructura de la plantilla (FilaCuadro)."""
    from app.servicios import cuadro
    from app.servicios.datos_personales import anonimizar_para_motor

    m = servicio_motor.motor_activo()
    if m is None:
        return []
    texto = texto_de(contenido, nombre, hojas)[: getattr(m, "max_caracteres", MAX_CARACTERES)]
    if len(texto.strip()) < 40:
        return []
    datos = m.estructurar(INSTRUCCION, f"Archivo: {nombre}\n\n{anonimizar_para_motor(texto)[0]}", ESQUEMA)
    cabecera = [n for n, _ in cuadro.PLANTILLA]
    claves = [k for _, k in cuadro.PLANTILLA]
    filas = [cabecera]
    for f in datos.get("filas") or []:
        valor = {
            **{k: str(f.get(k) or "").strip() for k in ("codigo_seccion", "seccion", "codigo_subseccion", "subseccion",
                                                       "codigo_serie", "serie", "codigo_subserie", "subserie",
                                                       "procedimiento")},
            "tipos": "; ".join(t.strip() for t in (f.get("tipos") or []) if t and t.strip()),
            "ag": "" if f.get("ag") is None else str(f["ag"]), "ac": "" if f.get("ac") is None else str(f["ac"]),
            **{k: "X" if f.get(k) else "" for k in ("ct", "e", "s", "m")},
            "funcion": "",
        }
        filas.append([valor.get(k, "") for k in claves])
    return cuadro._desde_plantilla(filas, 0) if len(filas) > 1 else []
