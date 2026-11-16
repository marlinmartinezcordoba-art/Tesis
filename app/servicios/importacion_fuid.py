"""
Importación de un Formato Único de Inventario Documental (FUID, Acuerdo AGN 042 de 2002) existente.

Cada fila del inventario es una unidad documental (en RiC, un rico:RecordSet de
tipo expediente) incluida en la serie o subserie del cuadro cuyo código trae la
fila, con sus fechas extremas, su unidad de conservación (caja, carpeta, tomo u
otra), sus folios, su soporte y su frecuencia de consulta.

Dos pasos, como el CCD y la TRD:
- `vista_previa` lee el archivo (Excel, CSV, PDF con texto o Word) y dice, fila
  por fila, qué entendió, en qué serie va y qué problema tiene, sin crear nada;
- `aplicar` crea lo que la persona confirmó, todo o nada. Las filas con problemas
  quedan fuera con su motivo.

No se inventa nada: sin código de una serie que exista en el cuadro, la fila no se
crea. El código propio de cada expediente se compone con el de su serie y el
número de orden (110.15-0001).
"""

import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental

COLUMNAS = {
    "orden": ("numero de orden", "no. de orden", "n de orden", "orden", "no.", "n°", "nº", "numero"),
    "codigo": ("codigo", "cod.", "cod"),
    "nombre": ("nombre de las series", "nombre de la serie", "series, subseries o asuntos", "nombre", "asunto",
               "descripcion", "titulo"),
    "fecha_inicial": ("fecha inicial", "inicial", "fecha extrema inicial", "desde"),
    "fecha_final": ("fecha final", "final", "fecha extrema final", "hasta"),
    "caja": ("caja",),
    "carpeta": ("carpeta",),
    "tomo": ("tomo",),
    "otro": ("otro", "otra"),
    "folios": ("numero de folios", "no. de folios", "folios", "n de folios"),
    "soporte": ("soporte",),
    "frecuencia": ("frecuencia de consulta", "frecuencia"),
    "notas": ("notas", "observaciones"),
}
FRECUENCIA = {"alta": "alta", "media": "media", "baja": "baja", "ninguna": "ninguna", "nula": "ninguna"}


class ErrorFuid(ValueError):
    pass


def _n(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9.°º ,]", " ", t).split())


def _encabezado(fila: list[str]) -> dict[str, int] | None:
    """Columnas del FUID en la fila; None si no parece el encabezado."""
    posiciones: dict[str, int] = {}
    for i, celda in enumerate(fila):
        c = _n(celda)
        if not c:
            continue
        for campo, nombres in COLUMNAS.items():
            if campo not in posiciones and any(c == x or c.startswith(x) for x in nombres):
                posiciones[campo] = i
                break
    return posiciones if {"codigo", "nombre"} <= set(posiciones) and len(posiciones) >= 3 else None


def leer(contenido: bytes, nombre: str) -> list[dict]:
    from app.servicios import cuadro

    try:
        hojas = cuadro._hojas(contenido, nombre)
    except cuadro.ErrorCuadro as exc:
        raise ErrorFuid(str(exc)) from exc
    filas: list[dict] = []
    for hoja in hojas:
        columnas = None
        for numero, fila in enumerate(hoja, start=1):
            if columnas is None:
                columnas = _encabezado(fila)
                continue
            valor = {k: (str(fila[i]).strip() if i < len(fila) and fila[i] is not None else "") for k, i in columnas.items()}
            if not valor.get("nombre") and not valor.get("codigo"):
                continue
            filas.append({"fila": numero, **valor})
    if not filas:
        raise ErrorFuid("No se encontró el encabezado del FUID (código y nombre de la serie o asunto) ni filas debajo.")
    return filas


def _extremas(inicial: str, final: str) -> str | None:
    a = re.sub(r"[^0-9-/]", "", inicial or "")
    b = re.sub(r"[^0-9-/]", "", final or "")
    if not a and not b:
        return None
    return f"{a or b}–{b or a}" if a != b else a


def vista_previa(db: Session, fondo: RecursoDocumental, contenido: bytes, nombre: str) -> dict:
    from app.servicios import fechas

    series = {(s.codigo_referencia or "").strip(): s for s in db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == fondo.id, RecursoDocumental.nivel.in_(("serie", "subserie"))))
        if s.codigo_referencia}
    existentes = {c for (c,) in db.execute(select(RecursoDocumental.codigo_referencia).where(
        RecursoDocumental.fondo_id == fondo.id, RecursoDocumental.codigo_referencia.is_not(None)))}
    salida, vistos = [], set()
    for i, f in enumerate(leer(contenido, nombre), start=1):
        problemas = []
        codigo = re.sub(r"\s+", "", f.get("codigo", ""))
        serie = series.get(codigo)
        if serie is None:
            problemas.append(f"El código «{codigo or '—'}» no es una serie ni subserie del cuadro.")
        orden = re.sub(r"\D", "", f.get("orden", "")) or str(i)
        propio = f"{codigo}-{int(orden):04d}" if codigo else None
        if propio and (propio in existentes or propio in vistos):
            problemas.append(f"El expediente «{propio}» ya existe.")
        vistos.add(propio)
        extremas = _extremas(f.get("fecha_inicial", ""), f.get("fecha_final", ""))
        if extremas:
            try:
                fechas.extremas(extremas)
            except fechas.FechaInvalida as exc:
                problemas.append(f"Fechas: {exc}")
        folios = re.sub(r"\D", "", f.get("folios", ""))
        titulo = " ".join(f.get("nombre", "").split()) or (serie.titulo if serie else "")
        if len(titulo) < 3:
            problemas.append("Sin nombre del asunto.")
        salida.append({"fila": f["fila"], "codigo_serie": codigo, "serie": serie.titulo if serie else None,
                       "serie_id": str(serie.id) if serie else None, "codigo": propio, "titulo": titulo,
                       "fechas_extremas": extremas, "caja": f.get("caja") or None, "carpeta": f.get("carpeta") or None,
                       "tomo": f.get("tomo") or None, "otra_unidad": f.get("otro") or None,
                       "folios": int(folios) if folios else None, "soporte": f.get("soporte") or None,
                       "frecuencia_consulta": FRECUENCIA.get(_n(f.get("frecuencia", ""))),
                       "notas": f.get("notas") or None, "problemas": problemas})
    return {"filas": salida, "validas": sum(1 for x in salida if not x["problemas"]),
            "con_problemas": sum(1 for x in salida if x["problemas"])}


def aplicar(db: Session, fondo: RecursoDocumental, contenido: bytes, nombre: str, usuario_id: uuid.UUID) -> dict:
    from app.servicios import descripcion
    from app.servicios.auditoria import registrar

    previa = vista_previa(db, fondo, contenido, nombre)
    creados = 0
    for f in (x for x in previa["filas"] if not x["problemas"]):
        r = descripcion.crear_agrupacion(db, fondo_id=fondo.id, nivel="expediente", titulo=f["titulo"],
                                         incluido_en_id=uuid.UUID(f["serie_id"]), usuario_id=usuario_id,
                                         codigo_referencia=f["codigo"], fechas_extremas=f["fechas_extremas"])
        for campo in ("caja", "carpeta", "tomo", "otra_unidad", "folios", "soporte", "frecuencia_consulta"):
            if f[campo] is not None:
                setattr(r, campo, f[campo])
        if f["notas"]:
            r.nota = f["notas"]
        creados += 1
    registrar(db, modulo="instrumentos", accion="fuid_importado", usuario_id=usuario_id, entidad_tipo="recurso_documental",
              entidad_id=fondo.id, detalle=f"{nombre}: {creados} expediente(s)",
              nuevo={"creados": creados, "fuera": previa["con_problemas"]})
    return {"creados": creados, "fuera": previa["con_problemas"],
            "motivos": [{"fila": x["fila"], "problemas": x["problemas"]} for x in previa["filas"] if x["problemas"]][:50]}
