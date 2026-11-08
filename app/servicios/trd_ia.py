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

MAX_CARACTERES = 80_000  # lo que se envía al motor en cada pedido
MAX_TEXTO = 600_000  # lo que se lee de un archivo: una TVD de cien páginas se envía por tramos

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
8. No inventes. Si un dato no está en el texto, déjalo vacío o null.
- El texto puede venir de un PDF escaneado leído con OCR, con errores: códigos sin sus puntos («10001» por «100.01», «1000706» por «100.07.06»), letras por números («130.11.04» donde las demás filas son «100.11.0x»), palabras cortadas o mal escritas. Corrige un código solo cuando el patrón de las demás filas lo hace evidente; si no es evidente, déjalo como está. Nunca inventes una serie, un tiempo de retención ni una disposición que no estén en el texto.
- Si el texto se envía por tramos («tramo 2», «tramo 3»), lee solo las filas de ese tramo, sin repetir encabezados."""

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


_CACHE_OCR: dict[str, tuple[str, bytes]] = {}


def ocr_pdf(contenido: bytes) -> tuple[str, bytes]:
    """El OCR de un PDF escaneado, en una sola pasada: su texto y una copia del PDF con el OCR
    estampado (la imagen de cada página con su capa de texto). Cada página se endereza si vino de
    lado y se lee conservando la disposición de las filas (cada fila de la tabla en su renglón, con
    sus espacios). Con la copia estampada la lectura por reglas encuentra las columnas sin IA; con el
    texto, la IA rearma lo que las reglas no sacan. El original no se modifica: su huella y su
    autenticidad se conservan. Se recuerda el último resultado para no pasar el OCR dos veces."""
    import hashlib
    import os
    import subprocess
    import tempfile
    from pathlib import Path

    import pypdfium2 as pdfium

    from app.core.config import settings
    from app.servicios.texto import ENTORNO_TESSERACT

    huella = hashlib.sha256(contenido).hexdigest()
    if huella in _CACHE_OCR:
        return _CACHE_OCR[huella]
    partes = []
    documento = pdfium.PdfDocument(contenido)
    estampado = pdfium.PdfDocument.new()
    try:
        with tempfile.TemporaryDirectory(prefix="ricora-trd-ocr-") as tmp:
            for i in range(len(documento)):
                ruta = Path(tmp) / f"p{i:05d}.png"
                imagen = documento[i].render(scale=settings.dpi_ocr / 72, grayscale=True).to_pil()
                imagen.save(ruta)
                giro = _giro(ruta)
                if giro:
                    imagen.rotate(-giro, expand=True).save(ruta)
                imagen.close()
                base = Path(tmp) / f"p{i:05d}"
                try:
                    subprocess.run(["tesseract", str(ruta), str(base), "-l", settings.idioma_ocr, "--psm", "6",
                                    "-c", "preserve_interword_spaces=1", "txt", "pdf"], capture_output=True,
                                   timeout=180, env=os.environ | ENTORNO_TESSERACT, check=False)
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
                txt, pdf = base.with_suffix(".txt"), base.with_suffix(".pdf")
                texto = txt.read_text("utf-8", "replace") if txt.exists() else ""
                partes.append(f"[Página {i + 1}]\n{texto.strip()}")
                if pdf.exists() and pdf.stat().st_size:
                    pagina = pdfium.PdfDocument(str(pdf))
                    estampado.import_pages(pagina)
                    pagina.close()
                if sum(len(x) for x in partes) > MAX_TEXTO:
                    break
            salida = io.BytesIO()
            if len(estampado):
                estampado.save(salida)
    finally:
        documento.close()
        estampado.close()
    resultado = ("\n\n".join(partes), salida.getvalue())
    _CACHE_OCR.clear()  # solo el último: un paquete de cien TRD no llena la memoria
    _CACHE_OCR[huella] = resultado
    return resultado


def _ocr_pdf(contenido: bytes) -> str:
    return ocr_pdf(contenido)[0]


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
        return _ocr_pdf(contenido)[:MAX_TEXTO]
    if nombre.lower().endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            partes = []
            for i, p in enumerate(pdf.pages, start=1):
                partes.append(f"[Página {i}]\n{p.extract_text() or ''}")
                p.close()  # libera la memoria de la página
                if sum(len(x) for x in partes) > MAX_TEXTO:
                    break
            texto = "\n\n".join(partes)
    else:
        texto = "\n".join(" | ".join(c for c in fila if c) for hoja in (hojas or []) for fila in hoja)
    return texto[:MAX_TEXTO]


def tramos(texto: str, maximo: int) -> list[str]:
    """El texto en tramos de a lo sumo `maximo` caracteres, cortando entre páginas («[Página n]») o, si una
    página sola no cabe, entre renglones."""
    if len(texto) <= maximo:
        return [texto]
    import re

    paginas = [p for p in re.split(r"(?=\[Página \d+\])", texto) if p.strip()]
    salida, actual = [], ""
    for pagina in paginas:
        while len(pagina) > maximo:  # una página enorme: se parte por renglones
            corte = pagina.rfind("\n", 0, maximo)
            corte = corte if corte > 0 else maximo
            if actual:
                salida.append(actual)
                actual = ""
            salida.append(pagina[:corte])
            pagina = pagina[corte:]
        if len(actual) + len(pagina) > maximo and actual:
            salida.append(actual)
            actual = ""
        actual += pagina
    if actual.strip():
        salida.append(actual)
    return salida


def extraer(contenido: bytes, nombre: str, hojas: list | None = None):
    """Las filas de la tabla leídas por el motor, ya en la estructura de la plantilla (FilaCuadro)."""
    from app.servicios import cuadro
    from app.servicios.datos_personales import anonimizar_para_motor

    m = servicio_motor.motor_activo()
    if m is None:
        return []
    texto = texto_de(contenido, nombre, hojas)
    if len(texto.strip()) < 40:
        return []
    # Un archivo largo (una TVD de cien páginas) va por tramos de páginas: antes se cortaba y se perdían
    # las series del final.
    crudas = []
    for i, tramo in enumerate(tramos(texto, getattr(m, "max_caracteres", MAX_CARACTERES)), start=1):
        aviso = f" (tramo {i})" if i > 1 else ""
        datos = m.estructurar(INSTRUCCION, f"Archivo: {nombre}{aviso}\n\n{anonimizar_para_motor(tramo)[0]}", ESQUEMA)
        crudas += datos.get("filas") or []
    cabecera = [n for n, _ in cuadro.PLANTILLA]
    claves = [k for _, k in cuadro.PLANTILLA]
    filas = [cabecera]
    for f in crudas:
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
