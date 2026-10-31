"""
Cuadro de clasificación (CCD) y tabla de retención documental (TRD).

Se cargan desde un archivo y siempre pasan por una vista previa:

- Plantilla Excel del sistema (`plantilla_xlsx`): una fila por serie o
  subserie, con su sección (dependencia) y subsección, los tipos
  documentales, la retención en archivo de gestión (AG) y central (AC), la
  disposición final (CT, E, S, M), el procedimiento y la función.
- Formato habitual de la TRD del AGN, en Excel o en PDF: columnas de código
  D (dependencia), S (serie), Sb (subserie); una columna «Series, subseries
  y tipos documentales» donde la serie va con su código y los tipos
  documentales debajo, sin código; AG, AC; CT, E, M, S; procedimiento. La
  dependencia sale del encabezado de la página («Dependencia productora:…»).

`vista_previa` interpreta el archivo y dice qué entendió y qué no, sin
crear nada. `aplicar` crea (o reutiliza, si ya existe con ese código) la
sección, subsección, serie y subserie con su código compuesto (110 → 110.2),
la regla de retención de la TRD unida a la serie o subserie que regula, los
tipos documentales en el vocabulario, la función que produce la serie y la
dependencia como agente productor. Cada paso queda en la auditoría.
"""

import io
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios.auditoria import registrar

MAX_BYTES = 30 * 1024 * 1024
DISPOSICION = {"ct": "conservacion_total", "s": "seleccion", "m": "medio_tecnico", "e": "eliminacion"}
SOPORTE = {"fisico": "físico", "electronico": "electrónico", "hibrido": "híbrido"}
NOMBRE_DISPOSICION = {"ct": "conservación total", "s": "selección", "m": "medio técnico", "e": "eliminación"}

PLANTILLA = (
    ("Código sección", "codigo_seccion"), ("Sección (dependencia)", "seccion"),
    ("Código subsección", "codigo_subseccion"), ("Subsección", "subseccion"),
    ("Código serie", "codigo_serie"), ("Serie", "serie"),
    ("Código subserie", "codigo_subserie"), ("Subserie", "subserie"),
    ("Tipos documentales", "tipos"), ("Retención AG (años)", "ag"), ("Retención AC (años)", "ac"),
    ("CT", "ct"), ("E", "e"), ("S", "s"), ("M", "m"), ("Procedimiento", "procedimiento"),
    ("Función (tipo de actividad)", "funcion"),
)


class ErrorCuadro(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def _n(texto) -> str:
    sin = "".join(c for c in unicodedata.normalize("NFKD", str(texto or "")) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin).strip().lower()


def _limpio(texto) -> str:
    return " ".join(str(texto or "").split())


@dataclass
class Nodo:
    codigo: str | None
    nombre: str


@dataclass
class FilaCuadro:
    fila: int
    seccion: Nodo | None = None
    # Dependencias entre la sección y la subsección productora (estructuras de
    # tres o más niveles: Secretaría General › Subdirección › Grupo).
    intermedias: list[Nodo] = field(default_factory=list)
    subseccion: Nodo | None = None
    serie: Nodo | None = None
    subserie: Nodo | None = None
    tipos: list[str] = field(default_factory=list)
    gestion: int | None = None
    central: int | None = None
    disposicion: str | None = None  # ct | s | m | e (la principal)
    otras_disposiciones: list[str] = field(default_factory=list)
    procedimiento: str | None = None
    funcion: str | None = None
    soporte: str | None = None  # fisico | electronico | hibrido
    parte: str | None = None  # en un .zip, el archivo del que salió la fila (procedencia)
    problemas: list[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        d = asdict(self)
        d["codigos"] = codigos_compuestos(self)
        return d

    @staticmethod
    def de_dict(d: dict) -> "FilaCuadro":
        nodo = lambda x: Nodo(_limpio(x.get("codigo")) or None, _limpio(x.get("nombre"))) if x and _limpio(x.get("nombre")) else None  # noqa: E731
        f = FilaCuadro(fila=int(d.get("fila") or 0), seccion=nodo(d.get("seccion")),
                       intermedias=[n for n in (nodo(x) for x in d.get("intermedias") or []) if n][:10],
                       subseccion=nodo(d.get("subseccion")),
                       serie=nodo(d.get("serie")), subserie=nodo(d.get("subserie")),
                       tipos=[_limpio(t) for t in d.get("tipos") or [] if _limpio(t)][:200],
                       gestion=d.get("gestion"), central=d.get("central"), disposicion=d.get("disposicion"),
                       otras_disposiciones=[x for x in d.get("otras_disposiciones") or [] if x in DISPOSICION],
                       procedimiento=_limpio(d.get("procedimiento")) or None, funcion=_limpio(d.get("funcion")) or None,
                       soporte=d.get("soporte") if d.get("soporte") in SOPORTE else None,
                       parte=(_limpio(d.get("parte")) or None) if d.get("parte") else None)
        validar(f)
        return f


def _anios(valor, nombre: str, f: FilaCuadro) -> int | None:
    if valor is None or str(valor).strip() in ("", "-", "—"):
        return None
    try:
        n = int(float(str(valor).replace(",", ".").strip()))
    except ValueError:
        f.problemas.append(f"La retención en {nombre} («{valor}») no es un número de años.")
        return None
    if not 0 <= n <= 100:
        f.problemas.append(f"La retención en {nombre} ({n}) está fuera de 0 a 100 años.")
        return None
    return n


def _marcada(valor) -> bool:
    return str(valor or "").strip().lower() not in ("", "-", "—", "no", "0", "none")


def _disposicion(f: FilaCuadro, marcas: dict[str, bool]) -> None:
    elegidas = [k for k in ("ct", "s", "m", "e") if marcas.get(k)]
    if elegidas:
        f.disposicion, f.otras_disposiciones = elegidas[0], elegidas[1:]


def validar(f: FilaCuadro) -> FilaCuadro:
    if f.serie is None:
        f.problemas.append("Falta la serie.")
    if f.subserie is not None and f.serie is None:
        f.problemas.append("Una subserie necesita su serie.")
    if f.seccion is None:
        f.problemas.append("Falta la sección (dependencia productora).")
    for valor, nombre in ((f.gestion, "gestión"), (f.central, "central")):
        if valor is not None and (not isinstance(valor, int) or not 0 <= valor <= 100):
            f.problemas.append(f"La retención en archivo de {nombre} es un entero entre 0 y 100.")
    if f.disposicion is not None and f.disposicion not in DISPOSICION:
        f.problemas.append("La disposición final es CT, E, S o M.")
    if (f.gestion is not None or f.central is not None) and f.disposicion is None:
        f.problemas.append("Tiene retención pero no disposición final (marque CT, E, S o M).")
    f.problemas = list(dict.fromkeys(f.problemas))
    return f


def _compone(superior: str | None, propio: str | None) -> str | None:
    if not propio:
        return None
    if not superior or propio.startswith(superior):
        return propio
    return f"{superior}.{propio}"


def compone_dependencia(superior: str | None, propio: str | None) -> str | None:
    """El código de una dependencia dentro de otra. En la codificación usual de
    las entidades (Acuerdo 004 de 2019) el código de la oficina ya es completo:
    100 › 110, 1000 › 1001, 4000 › 4106 (números del mismo largo). Ese no se
    compone; uno corto o con letras sí (1 › 1.2)."""
    if superior and propio and superior.isdigit() and propio.isdigit() and len(superior) == len(propio):
        return propio
    return _compone(superior, propio)


def codigos_compuestos(f: FilaCuadro) -> dict:
    """El código de cada nivel, compuesto desde el superior: en el CCD, una
    serie 2 de la dependencia 110 es 110.2 y su subserie 1, 110.2.1."""
    sec = f.seccion.codigo if f.seccion else None
    actual = sec
    for n in f.intermedias:
        actual = compone_dependencia(actual, n.codigo) if n.codigo else actual
    sub = compone_dependencia(actual, f.subseccion.codigo) if f.subseccion else None
    base = sub or actual
    serie = _compone(base, f.serie.codigo) if f.serie else None
    subserie = _compone(serie, f.subserie.codigo) if f.subserie else None
    return {"seccion": sec, "subseccion": sub, "serie": serie, "subserie": subserie}


# --- Lectura: filas de celdas desde Excel o PDF ------------------------------------------------------


def _filas_excel(contenido: bytes) -> list[list[list[str]]]:
    from openpyxl import load_workbook

    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ErrorCuadro(f"No se pudo abrir el Excel ({exc}).") from exc
    try:
        return [[["" if v is None else str(v).strip() for v in fila] for fila in hoja.iter_rows(values_only=True)]
                for hoja in libro.worksheets]
    finally:
        libro.close()


def _filas_csv(contenido: bytes) -> list[list[list[str]]]:
    import csv

    for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialecto = csv.Sniffer().sniff(texto[:5000], delimiters=",;\t|")
    except csv.Error:
        dialecto = csv.excel
    return [[[c.strip() for c in fila] for fila in csv.reader(io.StringIO(texto), dialecto)]]


def _filas_word(contenido: bytes) -> list[list[list[str]]]:
    """Las tablas de un .docx (las TRD a veces se aprueban en Word), con la
    dependencia de los párrafos que las anteceden («Dependencia productora: …»)."""
    from docx import Document

    try:
        documento = Document(io.BytesIO(contenido))
    except Exception as exc:  # noqa: BLE001
        raise ErrorCuadro(f"No se pudo abrir el documento de Word ({exc}).") from exc
    filas: list[list[str]] = []
    cuerpo = documento.element.body
    tablas = {t._tbl: t for t in documento.tables}
    for bloque in cuerpo.iterchildren():
        if bloque.tag.endswith("}p"):
            texto = "".join(x.text or "" for x in bloque.iter() if x.tag.endswith("}t"))
            if (dep := _dependencia_en([texto])) is not None:
                filas.append(["__dependencia__", dep.codigo or "", dep.nombre])
        elif bloque in tablas:
            for fila in tablas[bloque].rows:
                celdas, vistas = [], set()
                for celda in fila.cells:  # una celda combinada se repite: se toma una vez por fila
                    celdas.append("" if id(celda._tc) in vistas else celda.text.strip())
                    vistas.add(id(celda._tc))
                filas.append(celdas)
    return [filas]


EXTENSIONES = (".xlsx", ".xlsm", ".pdf", ".csv", ".docx", ".zip")


def _filas_zip(contenido: bytes) -> list[tuple[str, list[list[list[str]]]]]:
    """Una TRD que se publica en un .zip (una tabla por dependencia): se leen
    todos los archivos que el sistema entiende, en orden de nombre."""
    import zipfile

    try:
        paquete = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile as exc:
        raise ErrorCuadro("El .zip está dañado o no es un .zip.") from exc
    salida, total = [], 0
    for info in sorted(paquete.infolist(), key=lambda i: i.filename):
        nombre = info.filename
        if info.is_dir() or "__MACOSX" in nombre or nombre.rsplit("/", 1)[-1].startswith((".", "~$")):
            continue
        if not nombre.lower().endswith(EXTENSIONES) or nombre.lower().endswith(".zip"):
            continue
        total += info.file_size
        if info.file_size > MAX_BYTES or total > 4 * MAX_BYTES:
            raise ErrorCuadro("El .zip descomprimido es demasiado grande para leerlo de una vez: súbalo por partes.", 413)
        try:
            salida.append((nombre, _hojas(paquete.read(info), nombre)))
        except ErrorCuadro:
            salida.append((nombre, []))  # se informa como no leído
    if not salida:
        raise ErrorCuadro("El .zip no trae archivos de Excel, PDF, Word ni CSV.")
    return salida


def _hojas(contenido: bytes, nombre: str) -> list[list[list[str]]]:
    n = nombre.lower()
    if n.endswith((".xlsx", ".xlsm")):
        return _filas_excel(contenido)
    if n.endswith(".pdf"):
        return _filas_pdf(contenido)
    if n.endswith(".csv"):
        return _filas_csv(contenido)
    if n.endswith(".docx"):
        return _filas_word(contenido)
    if n.endswith((".xls", ".doc")):
        raise ErrorCuadro("Es un formato antiguo de Office (.xls o .doc): ábralo y guárdelo como .xlsx o .docx.")
    raise ErrorCuadro("Formatos que se leen: Excel (.xlsx), PDF con texto, Word (.docx), CSV o un .zip con ellos.")


DEPENDENCIA = re.compile(r"dependencia(?:\s+productora)?\s*[:.]?\s*(.+)", re.I)
CODIGO_DEP = re.compile(r"c[oó]digo(?:\s+(?:de\s+la\s+)?dependencia)?\s*[:.]?\s*([0-9][\w.\-]*)", re.I)


def _filas_pdf(contenido: bytes) -> list[list[list[str]]]:
    """Las tablas de cada página, con una fila marcadora de la dependencia
    tomada del encabezado de la página («Dependencia productora: …», «Código: …»)."""
    import pdfplumber

    try:
        pdf = pdfplumber.open(io.BytesIO(contenido))
    except Exception as exc:  # noqa: BLE001
        raise ErrorCuadro(f"No se pudo abrir el PDF ({exc}).") from exc
    filas: list[list[str]] = []
    with pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            nombre = codigo = None
            for linea in texto.splitlines():
                if nombre is None and (m := DEPENDENCIA.search(linea)):
                    nombre = re.split(r"\s{2,}|c[oó]digo", m.group(1), flags=re.I)[0].strip(" :.")
                if codigo is None and (m := CODIGO_DEP.search(linea)):
                    codigo = m.group(1).strip(" .")
            if nombre:
                filas.append(["__dependencia__", codigo or "", nombre])
            for tabla in pagina.extract_tables():
                filas += [["" if c is None else str(c).strip() for c in fila] for fila in tabla]
    if not any(f and f[0] != "__dependencia__" for f in filas):
        raise ErrorCuadro("El PDF no tiene tablas con texto: parece escaneado (una imagen). Pida la TRD en Excel o en "
                          "PDF generado desde el original, o pásela a la plantilla del sistema.")
    return [filas]


# --- Interpretación ------------------------------------------------------------------------------------


def _desde_plantilla(filas: list[list[str]], cabecera: int) -> list[FilaCuadro]:
    nombres = {_n(n): clave for n, clave in PLANTILLA}
    columnas = {nombres[_n(c)]: j for j, c in enumerate(filas[cabecera]) if _n(c) in nombres}
    salida, previo = [], {}
    for i, fila in enumerate(filas[cabecera + 1:], start=cabecera + 2):
        valor = lambda k: fila[columnas[k]].strip() if k in columnas and columnas[k] < len(fila) else ""  # noqa: E731
        if not any(valor(k) for k in columnas):
            continue
        # Celdas combinadas en Excel: la sección, la subsección y la serie se repiten hacia abajo.
        actual = {}
        for clave in ("codigo_seccion", "seccion", "codigo_subseccion", "subseccion", "codigo_serie", "serie"):
            actual[clave] = valor(clave) or ("" if clave.endswith("subseccion") and valor("seccion") else previo.get(clave, ""))
        if valor("serie"):
            actual["codigo_serie"] = valor("codigo_serie")
        previo = actual
        f = FilaCuadro(fila=i)
        if actual["seccion"]:
            f.seccion = Nodo(actual["codigo_seccion"] or None, _limpio(actual["seccion"]))
        if actual["subseccion"]:
            f.subseccion = Nodo(actual["codigo_subseccion"] or None, _limpio(actual["subseccion"]))
        if actual["serie"]:
            f.serie = Nodo(actual["codigo_serie"] or None, _limpio(actual["serie"]))
        if valor("subserie"):
            f.subserie = Nodo(valor("codigo_subserie") or None, _limpio(valor("subserie")))
        f.tipos = [_limpio(t) for t in re.split(r"[;\n]", valor("tipos")) if _limpio(t)]
        f.gestion, f.central = _anios(valor("ag"), "archivo de gestión", f), _anios(valor("ac"), "archivo central", f)
        _disposicion(f, {k: _marcada(valor(k)) for k in DISPOSICION})
        f.procedimiento = _limpio(valor("procedimiento")) or None
        f.funcion = _limpio(valor("funcion")) or None
        salida.append(validar(f))
    return salida


def _columnas_agn(top: list[str], sub: list[str] | None) -> dict[str, int]:
    """Columnas del formato del AGN: el encabezado suele ocupar dos filas
    (CÓDIGO sobre D S Sb; RETENCIÓN sobre AG AC; DISPOSICIÓN FINAL sobre CT E M S)."""
    columnas, arriba = {}, ""
    for j, celda in enumerate(top):
        arriba = _n(celda) or arriba  # celdas combinadas: el título sigue hacia la derecha
        abajo = _n(sub[j]) if sub and j < len(sub) else ""
        if "codigo" in arriba or arriba in ("d", "s", "sb"):
            clave = {"d": "d", "dep": "d", "s": "s", "sb": "sb", "ss": "sb", "subs": "sb"}.get(abajo or arriba)
            columnas.setdefault(clave or "codigo", j)
        elif "serie" in arriba:
            columnas.setdefault("texto", j)
        elif "retencion" in arriba or abajo in ("ag", "ac"):
            if abajo in ("ag", "ac"):
                columnas.setdefault(abajo, j)
            elif "gestion" in arriba:
                columnas.setdefault("ag", j)
            elif "central" in arriba:
                columnas.setdefault("ac", j)
        elif "disposicion" in arriba:
            if abajo in DISPOSICION:
                columnas.setdefault(f"disp_{abajo}", j)
        elif "procedimiento" in arriba:
            columnas.setdefault("procedimiento", j)
        elif abajo in ("ag", "ac"):
            columnas.setdefault(abajo, j)
    return columnas


def _dependencia_en(fila: list[str]) -> Nodo | None:
    """La dependencia anunciada en una fila de encabezado: el marcador que
    deja la lectura del PDF, o una celda «Dependencia productora: …» en Excel."""
    if fila and fila[0] == "__dependencia__":
        return Nodo(fila[1] or None, _limpio(fila[2]))
    texto = " ".join(c for c in fila if c)
    m = DEPENDENCIA.search(texto)
    if not m or "serie" in _n(texto):
        return None
    nombre = re.split(r"\s{2,}|c[oó]digo", m.group(1), flags=re.I)[0].strip(" :.")
    codigo = CODIGO_DEP.search(texto)
    return Nodo(codigo.group(1).strip(" .") if codigo else None, _limpio(nombre)) if nombre else None


def _desde_agn(filas: list[list[str]], cabecera: int) -> list[FilaCuadro]:
    top = filas[cabecera]
    sub = filas[cabecera + 1] if cabecera + 1 < len(filas) else None
    es_sub = sub is not None and any(_n(c) in ("d", "s", "sb", "ag", "ac", "ct", "e", "m") for c in sub)
    col = _columnas_agn(top, sub if es_sub else None)
    if "texto" not in col:
        raise ErrorCuadro("No se encontró la columna «Series, subseries y tipos documentales».")
    inicio = cabecera + (2 if es_sub else 1)
    dependencia: Nodo | None = None
    # La dependencia del encabezado de la primera página.
    for fila in filas[:cabecera]:
        dependencia = _dependencia_en(fila) or dependencia
    salida: list[FilaCuadro] = []
    serie_actual: Nodo | None = None
    actual: FilaCuadro | None = None
    for i, fila in enumerate(filas[inicio:], start=inicio + 1):
        otra = _dependencia_en(fila)
        if otra is not None:
            dependencia = otra
            continue
        celda = lambda k: (fila[col[k]] or "").strip() if k in col and col[k] < len(fila) else ""  # noqa: E731
        if _n(celda("texto")) in ("series, subseries y tipos documentales", "series y tipos documentales") or (
                "serie" in _n(celda("texto")) and "tipos documentales" in _n(celda("texto"))):
            continue  # cabecera repetida en otra página
        d, s, sb = celda("d"), celda("s"), celda("sb")
        if "codigo" in col and not (d or s or sb):
            partes = [p for p in re.split(r"[.\-\s]+", celda("codigo")) if p]
            d, s, sb = (partes + ["", "", ""])[:3] if len(partes) >= 2 else ("", "", "")
        lineas = [_limpio(x) for x in (celda("texto") or "").split("\n") if _limpio(x)]
        if not (d or s or sb or lineas):
            continue
        if s or sb:
            if d and (dependencia is None or (dependencia.codigo and dependencia.codigo != d)):
                dependencia = Nodo(d, dependencia.nombre if dependencia and not dependencia.codigo else f"Dependencia {d}")
            nombre = lineas[0] if lineas else ""
            actual = FilaCuadro(fila=i, seccion=dependencia)
            if sb:
                actual.serie = serie_actual
                actual.subserie = Nodo(sb, nombre)
            else:
                serie_actual = Nodo(s, nombre)
                actual.serie = serie_actual
            actual.tipos = lineas[1:]
            actual.gestion = _anios(celda("ag"), "archivo de gestión", actual)
            actual.central = _anios(celda("ac"), "archivo central", actual)
            _disposicion(actual, {k: _marcada(celda(f"disp_{k}")) for k in DISPOSICION})
            actual.procedimiento = _limpio(celda("procedimiento")) or None
            salida.append(actual)
        elif actual is not None:  # tipos documentales (y procedimiento que sigue) debajo de la serie
            actual.tipos += lineas
            if celda("procedimiento"):
                actual.procedimiento = _limpio(f"{actual.procedimiento or ''} {celda('procedimiento')}")
            if actual.gestion is None and celda("ag"):
                actual.gestion = _anios(celda("ag"), "archivo de gestión", actual)
            if actual.central is None and celda("ac"):
                actual.central = _anios(celda("ac"), "archivo central", actual)
            if actual.disposicion is None:
                _disposicion(actual, {k: _marcada(celda(f"disp_{k}")) for k in DISPOSICION})
    # Una serie con subseries: la fila de la serie sola no lleva retención propia; si no la tiene, no es un error.
    con_subseries = {(id(f.serie)) for f in salida if f.subserie is not None}
    final = []
    for f in salida:
        if f.subserie is None and id(f.serie) in con_subseries and f.gestion is None and f.disposicion is None:
            continue  # la serie se crea igual desde sus subseries
        final.append(validar(f))
    return final


# --- Formato libre: las columnas se reconocen por su nombre ------------------------------------------
#
# Cada entidad arma su CCD y su TRD a su manera: una fila por serie, por
# subserie o por tipo documental; la jerarquía de dependencias en una o en
# varias columnas (sección, subsección 1, 2, 3…); el encabezado en una o dos
# filas (RETENCIÓN sobre AG y AC; DISPOSICIÓN FINAL sobre CT, E, M, S). Aquí
# se reconoce cada columna por lo que dice su encabezado, esté donde esté.

CORTAS = {"ag": "ag", "ac": "ac", "ct": "ct", "e": "e", "m": "m", "s": "s", "d": "d", "sb": "sb", "ss": "sb",
          "c.t.": "ct", "c.t": "ct", "dt": "m", "mt": "m", "sel": "s", "el": "e", "dig": "m"}


def _clase_columna(texto: str, abajo: str = "") -> str | None:
    t, b = _n(texto).strip(" :./"), _n(abajo).strip(" :/")
    if b in CORTAS and CORTAS[b] not in ("d", "sb"):
        return CORTAS[b]
    if not t:
        return None
    if t in ("fondo", "subfondo", "periodo", "item", "no", "no.", "n°", "#", "consecutivo", "soporte", "observaciones"):
        return None
    codigo = t.startswith("cod") or t in ("d", "s", "sb", "ss")
    if "tipo" in t and "serie" not in t:
        return "tipos"
    if "subserie" in t or t in ("sb", "ss"):
        return "codigo_subserie" if codigo else "subserie"
    if "serie" in t or t == "s":
        if "tipo" in t or "subserie" in t:
            return None  # columna combinada del formato del AGN
        return "codigo_serie" if codigo else "serie"
    if any(x in t for x in ("seccion", "dependencia", "oficina", "unidad", "area", "grupo")) or t == "d":
        return "codigo_dependencia" if codigo else "nivel"
    if codigo:
        return "codigo"  # «CÓDIGO» suelto: se ubica por su vecina
    if "procedimiento" in t:
        return "procedimiento"
    if "funcion" in t or "proceso" in t:
        return "funcion"
    if "gestion" in t or t == "ag":
        return "ag"
    if "central" in t or t == "ac":
        return "ac"
    if "conservacion" in t or t == "ct":
        return "ct"
    if "eliminacion" in t or t == "e":
        return "e"
    if "seleccion" in t or t == "s":
        return "s"
    if "medio tecnico" in t or "microfilm" in t or "digitaliz" in t or t == "m":
        return "m"
    return None


def _tipos_en(celda: str) -> list[str]:
    """Los tipos documentales de una celda: separados por «;» o uno por renglón.
    Un renglón que empieza en minúscula sigue al anterior (el PDF partió la línea)."""
    tipos = []
    for parte in re.split(r";", celda or ""):
        renglones = []
        for linea in parte.split("\n"):
            linea = _limpio(linea)
            if not linea:
                continue
            if renglones and (linea[0].islower() or renglones[-1].endswith((",", " de", " y", " o", " del", " la"))):
                renglones[-1] = f"{renglones[-1]} {linea}"
            else:
                renglones.append(linea)
        tipos += [r.strip(" .-•") for r in renglones if r.strip(" .-•")]
    return tipos


def _columnas_libres(top: list[str], sub: list[str] | None) -> dict:
    col: dict = {"nivel": []}
    arriba = ""
    clases = []
    for j, celda in enumerate(top):
        arriba = celda if _n(celda) else (arriba if sub else "")
        abajo = sub[j] if sub and j < len(sub) else ""
        clases.append(_clase_columna(celda or arriba, abajo))
    for j, clase in enumerate(clases):
        if clase == "codigo":
            # Un «CÓDIGO» suelto es del nombre que lo antecede (dependencia, serie o subserie);
            # si no hay uno antes, del que le sigue (código | serie).
            nombres = {"serie": "codigo_serie", "subserie": "codigo_subserie", "nivel": "codigo_dependencia"}
            antes = clases[j - 1] if j > 0 else None
            despues = clases[j + 1] if j + 1 < len(clases) else None
            clase = nombres.get(antes or "") or nombres.get(despues or "")
        if clase == "nivel":
            col["nivel"].append(j)
        elif clase:
            col.setdefault(clase, j)
    return col


def _es_encabezado_libre(fila: list[str], sub: list[str] | None) -> dict | None:
    col = _columnas_libres(fila, sub)
    otras = {"subserie", "tipos", "codigo_serie", "ag", "ac", "ct", "codigo_dependencia"} & set(col)
    if "serie" in col and (otras or col["nivel"]):
        return col
    return None


def _desde_tabla(hojas: list[list[list[str]]]) -> list[FilaCuadro]:
    grupos: dict[tuple, dict] = {}
    codigos_dep: dict[tuple, set] = {}
    for filas in hojas:
        col = None
        anterior: dict = {}
        marcador: Nodo | None = None
        i = 0
        while i < len(filas):
            fila = filas[i]
            i += 1
            dep = _dependencia_en(fila)
            if dep is not None:
                marcador, anterior = dep, {}
                continue
            sub = filas[i] if i < len(filas) else None
            es_sub = sub is not None and sum(1 for c in sub if _n(c).strip(" ./") in CORTAS) >= 2
            nueva = _es_encabezado_libre(fila, sub if es_sub else None)
            if nueva is not None:
                col, anterior = nueva, {}
                i += 1 if es_sub else 0
                continue
            if col is None:
                continue
            celda = lambda k: _limpio(fila[col[k]]) if k in col and col[k] < len(fila) else ""  # noqa: E731
            niveles = [_limpio(fila[j]) for j in col["nivel"] if j < len(fila)]
            niveles = [x for x in niveles if x and _n(x) not in ("n/a", "na", "-", "no aplica")]
            serie, cod_serie = celda("serie"), celda("codigo_serie")
            subserie, cod_sub, tipos = celda("subserie"), celda("codigo_subserie"), celda("tipos")
            if not any((niveles, serie, subserie, tipos)):
                continue
            # Celdas combinadas (Excel) o repetidas al cambiar de página: se hereda de la fila anterior.
            if not niveles:
                niveles = anterior.get("niveles", [])
            heredada = False
            if not serie and (subserie or tipos) and anterior.get("niveles") == niveles:
                serie, cod_serie, heredada = anterior.get("serie", ""), anterior.get("cod_serie", ""), True
            if heredada and not subserie:
                subserie, cod_sub = anterior.get("subserie", ""), anterior.get("cod_sub", "")
            anterior = {"niveles": niveles, "serie": serie, "cod_serie": cod_serie, "subserie": subserie,
                        "cod_sub": cod_sub}
            if not serie:
                continue
            if not niveles and marcador is not None:
                niveles = [marcador.nombre]
                if marcador.codigo:
                    codigos_dep.setdefault((_n(marcador.nombre),), set()).add(marcador.codigo)
            ruta = tuple(_n(x) for x in niveles)
            if celda("codigo_dependencia") and ruta:
                codigos_dep.setdefault(ruta, set()).add(celda("codigo_dependencia"))
            clave = (ruta, _n(serie), _n(subserie))
            g = grupos.get(clave)
            if g is None:
                g = grupos[clave] = {"fila": i, "niveles": niveles, "serie": serie, "subserie": subserie,
                                     "cod_serie": set(), "cod_sub": set(), "tipos": [], "ag": "", "ac": "", "disp": {},
                                     "procedimiento": "", "funcion": ""}
            if cod_serie:
                g["cod_serie"].add(cod_serie)
            if cod_sub:
                g["cod_sub"].add(cod_sub)
            for t in _tipos_en(fila[col["tipos"]] if "tipos" in col and col["tipos"] < len(fila) else ""):
                if t not in g["tipos"]:
                    g["tipos"].append(t)
            for k in ("ag", "ac", "procedimiento", "funcion"):
                if not g[k] and celda(k):
                    g[k] = celda(k)
            for k in DISPOSICION:
                g["disp"][k] = g["disp"].get(k) or _marcada(celda(k))
    salida = []
    for (ruta, _, _), g in grupos.items():
        niveles = g["niveles"]
        nodos = []
        for k, nombre in enumerate(niveles):
            codigos = codigos_dep.get(ruta[:k + 1], set())
            nodos.append(Nodo(sorted(codigos)[0] if len(codigos) == 1 else None, nombre))
        f = FilaCuadro(fila=g["fila"])
        if nodos:
            f.seccion = nodos[0]
            f.intermedias = nodos[1:-1]
            f.subseccion = nodos[-1] if len(nodos) > 1 else None
        f.serie = Nodo(next(iter(g["cod_serie"])) if len(g["cod_serie"]) == 1 else None, g["serie"])
        if g["subserie"]:
            f.subserie = Nodo(next(iter(g["cod_sub"])) if len(g["cod_sub"]) == 1 else None, g["subserie"])
        f.tipos = g["tipos"][:200]
        f.gestion = _anios(g["ag"], "archivo de gestión", f)
        f.central = _anios(g["ac"], "archivo central", f)
        _disposicion(f, g["disp"])
        f.procedimiento = g["procedimiento"] or None
        f.funcion = g["funcion"] or None
        productora = nodos[-1] if nodos else None
        if productora is not None and not productora.codigo:
            varios = codigos_dep.get(ruta, set())
            f.problemas.append(f"La dependencia «{productora.nombre}» tiene varios códigos en el archivo ("
                               f"{', '.join(sorted(varios))}): confirme cuál." if len(varios) > 1 else
                               f"La dependencia «{productora.nombre}» no tiene código en el archivo: sin él, el código "
                               f"de la serie se repite en otras dependencias. Regístrelo en Dependencias o cargue la "
                               f"TRD que lo trae.")
        for nombre, codigos in ((g["serie"], g["cod_serie"]), (g["subserie"], g["cod_sub"])):
            if len(codigos) > 1:
                f.problemas.append(f"«{nombre}» aparece con varios códigos ({', '.join(sorted(codigos))}): el archivo "
                                   "se contradice; confirme cuál es.")
        salida.append(validar(f))
    return salida


def interpretar(contenido: bytes, archivo: str) -> tuple[list[FilaCuadro], str]:
    if not contenido:
        raise ErrorCuadro("El archivo está vacío.")
    nombre = archivo.lower()
    limite = 3 * MAX_BYTES if nombre.endswith(".zip") else MAX_BYTES
    if len(contenido) > limite:
        raise ErrorCuadro(f"El archivo pasa de {limite // (1024 * 1024)} MB.", 413)
    if nombre.endswith(".zip"):
        partes = _filas_zip(contenido)
        filas, leidos, sin_leer = [], [], []
        for parte, hojas in partes:
            try:
                de_la_parte = _interpretar_hojas(hojas)[0] if hojas else []
                for f in de_la_parte:
                    f.parte = parte.rsplit("/", 1)[-1][:300]
                filas += de_la_parte
                (leidos if hojas else sin_leer).append(parte)
            except ErrorCuadro:
                sin_leer.append(parte)
        if not filas:
            raise ErrorCuadro("Ningún archivo del .zip tiene una tabla de CCD o TRD reconocible (" +
                              ", ".join(p.rsplit("/", 1)[-1] for p in sin_leer[:5]) + ").")
        origen = f"zip · {len(leidos)} archivo(s) leídos"
        if sin_leer:
            origen += f", {len(sin_leer)} sin tabla reconocible ({', '.join(p.rsplit('/', 1)[-1] for p in sin_leer[:3])}" \
                      + ("…" if len(sin_leer) > 3 else "") + ")"
        return filas, origen
    origen = {".pdf": "pdf", ".csv": "csv", ".docx": "word"}.get("." + nombre.rsplit(".", 1)[-1], "excel")
    filas, forma = _interpretar_hojas(_hojas(contenido, nombre))
    return filas, f"{origen} · {forma}"


def _interpretar_hojas(hojas: list[list[list[str]]]) -> tuple[list[FilaCuadro], str]:
    plantilla = {_n(n) for n, _ in PLANTILLA}
    for filas in hojas:
        for i, fila in enumerate(filas[:60]):
            celdas = {_n(c) for c in fila if c}
            # La plantilla del sistema: sus encabezados exactos, con «Sección (dependencia)».
            if {"serie", "codigo serie", "seccion (dependencia)"} <= celdas and len(celdas & plantilla) >= 4:
                return _desde_plantilla(filas, i), "plantilla del sistema"
            # El formato del AGN: series, subseries y tipos en una misma columna.
            if any("serie" in c and "tipo" in c for c in celdas) and \
                    any("retencion" in c or "procedimiento" in c or "disposicion" in c for c in celdas):
                return _desde_agn(filas, i), "formato de TRD del AGN"
    leidas = _desde_tabla(hojas)
    if leidas:
        return leidas, "columnas reconocidas por su nombre"
    raise ErrorCuadro("No se encontró una tabla con la columna de la serie. Revise que el archivo tenga un encabezado "
                      "con «Serie» (y, si es una TRD, la retención y la disposición final), o use la plantilla del "
                      "sistema.")


def vista_previa(contenido: bytes, archivo: str) -> dict:
    filas, origen = interpretar(contenido, archivo)
    return {"origen": origen, "filas": [f.a_dict() for f in filas],
            "resumen": {"filas": len(filas), "con_problemas": sum(1 for f in filas if f.problemas),
                        "secciones": len({(f.seccion.codigo, f.seccion.nombre) for f in filas if f.seccion}),
                        "series": len({codigos_compuestos(f)["serie"] or (f.serie.nombre if f.serie else "")
                                       for f in filas if f.serie}),
                        "subseries": sum(1 for f in filas if f.subserie),
                        "con_retencion": sum(1 for f in filas if f.disposicion)}}


# --- Plantilla -----------------------------------------------------------------------------------------


def plantilla_xlsx() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    libro = Workbook()
    hoja = libro.active
    hoja.title = "CCD-TRD"
    hoja.append([n for n, _ in PLANTILLA])
    hoja.append(["100", "Despacho del Alcalde", "", "", "2", "Actas", "1", "Actas de Consejo de Gobierno",
                 "Citación; Acta; Lista de asistencia", 2, 8, "X", "", "", "X",
                 "Conservación total por su valor histórico; se digitaliza.", "Gobierno municipal"])
    hoja.append(["100", "Despacho del Alcalde", "", "", "15", "Correspondencia", "", "",
                 "Oficio; Memorando", 2, 3, "", "X", "", "",
                 "Se elimina al cumplir su tiempo, con acta aprobada por el comité.", ""])
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="1F3A5F")
        celda.alignment = Alignment(wrap_text=True, vertical="center")
    for j, ancho in enumerate((10, 28, 10, 24, 10, 28, 10, 28, 40, 10, 10, 6, 6, 6, 6, 44, 28), start=1):
        hoja.column_dimensions[hoja.cell(1, j).column_letter].width = ancho
    hoja.freeze_panes = "A2"
    ayuda = libro.create_sheet("Instrucciones")
    for linea in (
        "Una fila por serie o subserie. La sección (dependencia) y la subsección pueden repetirse o dejarse en "
        "blanco debajo de la primera (como celdas combinadas).",
        "Códigos: el de la serie y la subserie puede ir solo (2, 1) o completo (100.2, 100.2.1); el sistema lo "
        "compone desde el superior.",
        "Tipos documentales: separados por punto y coma.",
        "Retención AG y AC: años en archivo de gestión y central (0 a 100).",
        "Disposición final: marque con X una columna (CT conservación total, E eliminación, S selección, "
        "M medio técnico). Si marca varias, la primera (CT, S, M, E) es la principal y las demás quedan anotadas.",
        "Función (opcional): el tipo de actividad que produce la serie.",
        "Antes de crear nada, el sistema muestra una vista previa con lo que entendió y los problemas.",
    ):
        ayuda.append([linea])
    ayuda.column_dimensions["A"].width = 120
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# --- Aplicar -------------------------------------------------------------------------------------------


def _agrupacion(db: Session, fondo: RecursoDocumental, nivel: str, nodo: Nodo, codigo: str | None,
                superior: RecursoDocumental, usuario_id: uuid.UUID, informe: dict, alcance: str | None = None,
                productor_id: uuid.UUID | None = None) -> RecursoDocumental:
    from app.servicios import descripcion

    if codigo:
        existente = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo.id,
                                                              RecursoDocumental.codigo_referencia == codigo))
        if existente is not None:
            if existente.nivel != nivel:
                raise ErrorCuadro(f"El código «{codigo}» ya es de un(a) {existente.nivel} y aquí sería {nivel}.", 409)
            informe["reutilizados"] += existente.id not in informe["_nuevos"]
            return existente
    if codigo and nivel in ("seccion", "subseccion"):
        # Una dependencia creada antes con otro código compuesto (100.110 en vez de 110) se reconoce
        # por su nombre dentro de la misma superior: no se duplica ni se le cambia el código.
        existente = next((r for r in db.scalars(select(RecursoDocumental).where(
            RecursoDocumental.fondo_id == fondo.id, RecursoDocumental.nivel == nivel,
            RecursoDocumental.incluido_en_id == superior.id)).all() if _n(r.titulo) == _n(nodo.nombre)), None)
        if existente is not None:
            informe["avisos"].append(f"«{existente.titulo}» conserva su código {existente.codigo_referencia}.")
            informe["reutilizados"] += existente.id not in informe["_nuevos"]
            return existente
    if not codigo:
        existente = next((r for r in db.scalars(select(RecursoDocumental).where(
            RecursoDocumental.fondo_id == fondo.id, RecursoDocumental.nivel == nivel,
            RecursoDocumental.incluido_en_id == superior.id)).all() if _n(r.titulo) == _n(nodo.nombre)), None)
        if existente is not None:
            informe["reutilizados"] += existente.id not in informe["_nuevos"]
            return existente
    try:
        r = descripcion.crear_agrupacion(db, fondo_id=fondo.id, nivel=nivel, titulo=nodo.nombre,
                                         incluido_en_id=superior.id, usuario_id=usuario_id, codigo_referencia=codigo,
                                         alcance=alcance, productor_id=productor_id, desde_trd=True)
    except descripcion.ErrorDescripcion as exc:
        raise ErrorCuadro(f"{nivel} «{nodo.nombre}»: {exc}", exc.codigo) from exc
    informe["creados"][nivel] = informe["creados"].get(nivel, 0) + 1
    informe["_nuevos"].add(r.id)  # lo creado en esta misma carga no cuenta como «ya existía»
    return r


def _de_vocabulario(db: Session, fondo_id: uuid.UUID, clase: str, nombre: str, usuario_id: uuid.UUID,
                    subtipo: str | None = None) -> tuple[EntidadVocabulario, bool]:
    from app.servicios import vocabulario

    existente = db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fondo_id,
                                                           EntidadVocabulario.clase == clase,
                                                           EntidadVocabulario.estado == "activa",
                                                           EntidadVocabulario.nombre_normalizado ==
                                                           vocabulario.normalizar(nombre)))
    if existente is not None:
        return existente, False
    e = vocabulario.crear(db, fondo_id=fondo_id, clase=clase, nombre=nombre, subtipo=subtipo, origen="persona",
                          confianza=None, motor=None, usuario_id=usuario_id)
    db.flush()
    return e, True


def _texto_regla(f: FilaCuadro, version: dict | None) -> str | None:
    otras = ", ".join(NOMBRE_DISPOSICION[x] for x in f.otras_disposiciones)
    return " ".join(x for x in (
        f.procedimiento, f"También: {otras}." if otras else None,
        f"Soporte: {SOPORTE[f.soporte]}." if f.soporte else None,
        f"{version['nombre']}, aprobada por {version['acto']}." if version and version.get("acto") else None) if x) or None


def _regla(db: Session, fondo: RecursoDocumental, hoja: RecursoDocumental, f: FilaCuadro, usuario_id: uuid.UUID,
           informe: dict, version: dict | None) -> None:
    """La regla de retención (rico:Rule) de la serie o subserie.

    Sin versión (carga directa de un archivo), una serie que ya tiene regla no
    se toca. Con una versión de la TRD que se aplica, la regla vigente se
    compara: si la retención o la disposición cambian, la anterior no se borra
    ni se modifica: su relación con la serie se cierra el día antes de la nueva
    vigencia y se crea la regla nueva desde esa fecha. Así cada expediente
    conserva la retención de la TRD con que se produjo (la que regía en su
    fecha) y la serie queda con la historia de sus reglas en RiC-O."""
    from app.servicios import autoridad, retencion

    vigentes = db.scalars(select(Relacion).where(Relacion.destino_id == hoja.id, Relacion.estado == "vigente",
                                                 Relacion.codigo_ric == "regulates_or_regulated",
                                                 Relacion.rol == "retencion")).all()
    texto = _texto_regla(f, version)
    if version and version.get("instrumento") == "tvd":
        _regla_tvd(db, fondo, hoja, f, usuario_id, informe, version, vigentes, texto)
        return
    abierta = next((r for r in vigentes if retencion.abierta(r.fecha_edtf)), None)
    if abierta is not None:
        actual = db.get(EntidadVocabulario, abierta.origen_id)
        igual = actual is not None and (actual.retencion_gestion_anios, actual.retencion_central_anios,
                                        actual.disposicion_final) == (f.gestion, f.central, DISPOSICION[f.disposicion])
        if version is None:
            informe["avisos"].append(f"«{hoja.titulo}» ya tenía su regla de retención: no se cambió.")
            return
        if igual:
            if not abierta.fecha_edtf:
                # Regla cargada antes de parametrizar la TRD: la versión que la confirma le da su vigencia.
                abierta.fecha_edtf, abierta.nota = f"{version['desde'].isoformat()}/", version["nombre"]
            informe["reglas_sin_cambio"] = informe.get("reglas_sin_cambio", 0) + 1
            return
        desde = version["desde"]
        inicio = (abierta.fecha_edtf or "").split("/")[0] if abierta.fecha_edtf else ""
        if inicio and inicio >= desde.isoformat():
            raise ErrorCuadro(f"«{hoja.titulo}»: su regla actual rige desde {inicio}; la nueva versión tiene que "
                              "empezar después.", 409)
        from datetime import timedelta
        abierta.fecha_edtf = f"{inicio}/{(desde - timedelta(days=1)).isoformat()}"
        abierta.nota = f"Cerrada al aplicar la {version['nombre']}."
        registrar(db, modulo="vocabularios", accion="regla_cerrada", usuario_id=usuario_id, entidad_tipo="relacion",
                  entidad_id=abierta.id, detalle=f"Retención de «{hoja.titulo}» reemplazada por la {version['nombre']}",
                  nuevo={"vigencia": abierta.fecha_edtf})
        informe["reglas_reemplazadas"] = informe.get("reglas_reemplazadas", 0) + 1
    prefijo = f"TRD v{version['numero']}" if version else "TRD"
    regla = retencion.crear_regla(db, fondo_id=fondo.id, nombre=f"{prefijo} {hoja.codigo_referencia or ''} "
                                  f"{hoja.titulo}".replace("  ", " ").strip(), gestion=f.gestion,
                                  central=f.central, disposicion=DISPOSICION[f.disposicion],
                                  procedimiento=texto, usuario_id=usuario_id)
    autoridad.vincular(db, tipo="regla_serie", desde=regla, con_tipo="recurso_documental", con_id=hoja.id,
                       usuario_id=usuario_id, fecha_edtf=f"{version['desde'].isoformat()}/" if version else None,
                       nota=f"{version['nombre']}" if version else None, desde_trd=True)
    informe["reglas"] += 1


def _regla_tvd(db: Session, fondo: RecursoDocumental, hoja: RecursoDocumental, f: FilaCuadro, usuario_id: uuid.UUID,
               informe: dict, version: dict, vigentes: list, texto: str | None) -> None:
    """La regla de la TVD rige los documentos producidos en su periodo
    institucional (desde/hasta), no desde una fecha hacia adelante: no cierra la
    regla de la TRD ni la de otro periodo. Si el mismo periodo ya tenía regla (una
    TVD anterior) y cambia, la anterior se anula con la nota de quién la reemplaza:
    no se borra ni se modifica."""
    from app.servicios import autoridad, retencion

    periodo = f"{version['desde'].isoformat()}/{version['hasta'].isoformat()}"
    previa = next((r for r in vigentes if r.fecha_edtf == periodo), None)
    if previa is not None:
        actual = db.get(EntidadVocabulario, previa.origen_id)
        if actual is not None and (actual.retencion_gestion_anios, actual.retencion_central_anios,
                                   actual.disposicion_final) == (f.gestion, f.central, DISPOSICION[f.disposicion]):
            informe["reglas_sin_cambio"] = informe.get("reglas_sin_cambio", 0) + 1
            return
        previa.estado = "anulada"
        previa.nota = f"Reemplazada por la {version['nombre']}."
        registrar(db, modulo="vocabularios", accion="regla_cerrada", usuario_id=usuario_id, entidad_tipo="relacion",
                  entidad_id=previa.id, detalle=f"Valoración de «{hoja.titulo}» reemplazada por la {version['nombre']}",
                  nuevo={"periodo": periodo})
        informe["reglas_reemplazadas"] = informe.get("reglas_reemplazadas", 0) + 1
    regla = retencion.crear_regla(db, fondo_id=fondo.id, nombre=f"TVD v{version['numero']} {hoja.codigo_referencia or ''} "
                                  f"{hoja.titulo}".replace("  ", " ").strip(), gestion=f.gestion, central=f.central,
                                  disposicion=DISPOSICION[f.disposicion], procedimiento=texto, usuario_id=usuario_id)
    autoridad.vincular(db, tipo="regla_serie", desde=regla, con_tipo="recurso_documental", con_id=hoja.id,
                       usuario_id=usuario_id, fecha_edtf=periodo, nota=version["nombre"], desde_trd=True)
    informe["reglas"] += 1


def aplicar(db: Session, fondo: RecursoDocumental, filas: list[dict], usuario_id: uuid.UUID,
            version: dict | None = None) -> dict:
    """Crea el cuadro y las reglas de lo que la persona confirmó en la vista
    previa. Si una fila tiene problemas, no se crea nada (todo o nada).

    `version` ({numero, nombre, acto, desde}) es la versión de la TRD que se
    aplica desde la parametrización: fecha la vigencia de las reglas y
    reemplaza las que cambian."""
    from app.servicios import autoridad

    leidas = [FilaCuadro.de_dict(d) for d in filas]
    con_problemas = [f for f in leidas if f.problemas]
    if not leidas:
        raise ErrorCuadro("No hay filas para crear.")
    if con_problemas:
        raise ErrorCuadro(f"Corrija las {len(con_problemas)} fila(s) con problemas antes de crear (la primera es la "
                          f"{con_problemas[0].fila}: {con_problemas[0].problemas[0]})")
    informe = {"creados": {}, "reutilizados": 0, "reglas": 0, "tipos_documentales": 0, "funciones": 0, "avisos": [],
               "_nuevos": set()}
    for f in leidas:
        c = codigos_compuestos(f)
        productor, nuevo = _de_vocabulario(db, fondo.id, "agente", f.seccion.nombre, usuario_id, "entidad_corporativa")
        seccion = _agrupacion(db, fondo, "seccion", f.seccion, c["seccion"], fondo, usuario_id, informe,
                              productor_id=productor.id)
        superior, codigo = seccion, c["seccion"]
        for n in f.intermedias:
            codigo = compone_dependencia(codigo, n.codigo) if n.codigo else None
            superior = _agrupacion(db, fondo, "subseccion", n, codigo, superior, usuario_id, informe)
        if f.subseccion:
            superior = _agrupacion(db, fondo, "subseccion", f.subseccion, c["subseccion"], superior, usuario_id, informe)
        tipos = "Tipos documentales: " + "; ".join(f.tipos) + "." if f.tipos else None
        # El código de la serie sale del de la dependencia tal como quedó en el cuadro (una ya existente
        # conserva el suyo).
        cod_serie = _compone(superior.codigo_referencia, f.serie.codigo) if superior.codigo_referencia \
            and superior.nivel != "fondo" else c["serie"]
        serie = _agrupacion(db, fondo, "serie", f.serie, cod_serie, superior, usuario_id, informe,
                            alcance=None if f.subserie else tipos)
        hoja = _agrupacion(db, fondo, "subserie", f.subserie, _compone(serie.codigo_referencia, f.subserie.codigo)
                           if serie.codigo_referencia else c["subserie"], serie, usuario_id, informe, alcance=tipos) \
            if f.subserie else serie
        formas = []
        for t in f.tipos:
            forma, creado = _de_vocabulario(db, fondo.id, "forma_documental", t, usuario_id)
            formas.append(forma.id)
            informe["tipos_documentales"] += int(creado)
        # Los tipos de la TRD quedan unidos a la serie o subserie (RiC-A17 en un Record
        # Set); una versión nueva los reemplaza. Ordenados: así el grafo los dice exactos.
        if sorted(set(formas)) != list(hoja.formas_miembros or []):
            hoja.formas_miembros = sorted(set(formas))
        if f.disposicion:
            _regla(db, fondo, hoja, f, usuario_id, informe, version)
        if f.funcion:
            funcion, creada = _de_vocabulario(db, fondo.id, "tipo_actividad", f.funcion, usuario_id)
            informe["funciones"] += int(creada)
            try:
                autoridad.vincular(db, tipo="serie_producida", desde=funcion, con_tipo="recurso_documental",
                                   con_id=hoja.id, usuario_id=usuario_id)
            except autoridad.ErrorAutoridad:
                pass  # ya estaba unida
    registrar(db, modulo="instrumentos", accion="cuadro_importado", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=fondo.id, detalle=f"CCD y TRD: {len(leidas)} fila(s)",
              nuevo={k: v for k, v in informe.items() if k not in ("avisos", "_nuevos")})
    db.flush()
    del informe["_nuevos"]
    return informe


def arbol(db: Session, fondo: RecursoDocumental) -> list[dict]:
    """El cuadro de clasificación del fondo: secciones, subsecciones, series
    y subseries con su código, su regla de retención y cuántos expedientes."""
    from app.servicios import retencion

    niveles = ("seccion", "subseccion", "serie", "subserie")
    todos = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo.id,
                                                       RecursoDocumental.nivel.in_(niveles + ("expediente",)))).all()
    hijos: dict[uuid.UUID, list[RecursoDocumental]] = {}
    for r in todos:
        hijos.setdefault(r.incluido_en_id, []).append(r)

    def nodo(r: RecursoDocumental) -> dict:
        regla = retencion.retencion_de(db, r) if r.nivel in ("serie", "subserie") else None
        return {"id": str(r.id), "nivel": r.nivel, "codigo": r.codigo_referencia, "titulo": r.titulo,
                "regla": regla, "expedientes": sum(1 for h in hijos.get(r.id, []) if h.nivel == "expediente"),
                "hijos": [nodo(h) for h in sorted(hijos.get(r.id, []), key=lambda x: (x.codigo_referencia or "", x.titulo))
                          if h.nivel in niveles]}
    return [nodo(r) for r in sorted(hijos.get(fondo.id, []), key=lambda x: (x.codigo_referencia or "", x.titulo))
            if r.nivel in niveles]


# --- Validación RiC-O ---------------------------------------------------------------------------------


def validar_rico(db: Session, fondo: RecursoDocumental) -> dict:
    """El fondo, con su cuadro, armado como grafo RiC-O 1.1 y validado contra la
    ontología oficial (OWL) y el perfil SHACL del sistema. Es el mismo mapeo
    con que se guarda en el almacén de tripletas."""
    from app.servicios import conformidad_rico, exportacion_rico

    db.flush()
    ex = exportacion_rico.exportar(db, fondo, incluir_restringidos=True)
    owl = conformidad_rico.verificar_owl(ex.grafo)
    shacl = conformidad_rico.validar_shacl(ex.grafo)
    resumen = ex.resumen()
    return {"conforme": not owl and shacl["conforme"], "ontologia": "RiC-O 1.1",
            "tripletas": resumen["tripletas"], "por_clase": resumen["por_clase"],
            "problemas_owl": [str(p) for p in owl[:20]],
            "resultados_shacl": [r if isinstance(r, dict) else {"mensaje": str(r)} for r in shacl["resultados"][:20]]}


def probar_y_aplicar(db: Session, fondo: RecursoDocumental, filas: list[dict], usuario_id: uuid.UUID,
                     crear: bool, version: dict | None = None) -> tuple[dict, dict]:
    """Aplica el cuadro dentro de un punto de guardado y valida el resultado en
    RiC-O. Si solo se valida, o si no es conforme, se deshace todo: nada queda
    creado a medias ni fuera de RiC-O."""
    punto = db.begin_nested()
    try:
        informe = aplicar(db, fondo, filas, usuario_id, version)
        validacion = validar_rico(db, fondo)
    except Exception:
        punto.rollback()
        raise
    if not crear or not validacion["conforme"]:
        punto.rollback()
    else:
        punto.commit()
    return informe, validacion
