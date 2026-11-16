"""Importar la Tabla de Control de Acceso (TCA) que la entidad ya tiene, en el formato en que esté.

Cada fila se une a su serie o subserie del cuadro por el código y declara su categoría de acceso
(pública, clasificada o reservada; Ley 1712 de 2014, arts. 18 y 19), su fundamento legal, el plazo de
la restricción, la reproducción, las condiciones y el responsable. Primero se ve qué se entendió;
después se aplica solo lo válido. Una declaración nueva no borra la anterior: la reemplaza con su traza.
"""

import re
import unicodedata
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental

COLUMNAS = {
    "codigo": ("codigo", "cod.", "cod"),
    "nombre": ("nombre de la serie", "serie", "subserie", "series", "nombre", "asunto"),
    "acceso": ("categoria de acceso", "categoria", "acceso", "tipo de acceso", "clasificacion de la informacion",
               "clasificacion", "condicion de acceso"),
    "publica": ("publica", "informacion publica"),
    "clasificada": ("clasificada", "informacion publica clasificada"),
    "reservada": ("reservada", "informacion publica reservada"),
    "fundamento": ("fundamento legal", "fundamento juridico", "fundamento", "norma", "excepcion", "objetivo legitimo"),
    "plazo": ("plazo de la clasificacion", "plazo de la reserva", "plazo", "rige hasta", "vigente hasta", "hasta",
              "tiempo de reserva", "tiempo"),
    "reproduccion": ("reproduccion", "condiciones de reproduccion"),
    "condiciones": ("condiciones de acceso", "condiciones", "observaciones", "notas"),
    "responsable": ("responsable", "dependencia responsable", "quien autoriza"),
}


class ErrorImportacionTca(ValueError):
    pass


def _n(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9.° ,]", " ", t).split())


def _encabezado(fila: list[str]) -> dict[str, int] | None:
    posiciones: dict[str, int] = {}
    for i, celda in enumerate(fila):
        c = _n(celda)
        if not c:
            continue
        for campo, nombres in COLUMNAS.items():
            if campo not in posiciones and any(c == x or c.startswith(x) for x in nombres):
                posiciones[campo] = i
                break
    tiene_acceso = "acceso" in posiciones or {"publica", "clasificada", "reservada"} & set(posiciones)
    return posiciones if "codigo" in posiciones and tiene_acceso else None


def _acceso(v: dict) -> str | None:
    texto = _n(v.get("acceso"))
    if "reserv" in texto:
        return "reservado"
    if "clasific" in texto:
        return "clasificado"
    if "public" in texto or "libre" in texto or "abiert" in texto:
        return "publico"
    # Formato de casillas: una columna por categoría marcada con «X».
    for campo, clave in (("reservada", "reservado"), ("clasificada", "clasificado"), ("publica", "publico")):
        if _n(v.get(campo)):
            return clave
    return None


def _plazo(texto: str, hoy: date) -> date | None:
    t = (texto or "").strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", t)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"(\d{1,2})\s*a[nñ]os?", _n(t).replace("n", "n"))
    if m or re.fullmatch(r"\d{1,2}", t):
        anios = int(m.group(1) if m else t)
        try:
            return hoy.replace(year=hoy.year + anios)
        except ValueError:  # 29 de febrero
            return hoy.replace(year=hoy.year + anios, day=28)
    return None


def _reproduccion(texto: str, acceso: str) -> str:
    t = _n(texto)
    if "no " in f"{t} " and "permit" in t:
        return "no_permitida"
    if "condic" in t or "restring" in t:
        return "condicionada"
    if "permit" in t or "libre" in t:
        return "permitida"
    return "permitida" if acceso == "publico" else "condicionada"


def leer(contenido: bytes, nombre: str) -> list[dict]:
    from app.servicios import cuadro

    try:
        hojas = cuadro._hojas(contenido, nombre)
    except cuadro.ErrorCuadro as exc:
        raise ErrorImportacionTca(str(exc)) from exc
    filas: list[dict] = []
    for hoja in hojas:
        columnas = None
        for numero, fila in enumerate(hoja, start=1):
            if columnas is None:
                columnas = _encabezado(fila)
                continue
            valor = {k: (str(fila[i]).strip() if i < len(fila) and fila[i] is not None else "") for k, i in columnas.items()}
            if valor.get("codigo"):
                filas.append({"fila": numero, **valor})
    if not filas:
        raise ErrorImportacionTca("No se encontró el encabezado de la TCA (código de la serie y categoría de acceso) "
                                  "ni filas debajo.")
    return filas


def vista_previa(db: Session, fondo: RecursoDocumental, contenido: bytes, nombre: str) -> dict:
    from app.servicios import tca

    series = {(s.codigo_referencia or "").strip(): s for s in db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == fondo.id, RecursoDocumental.nivel.in_(("serie", "subserie"))))
        if s.codigo_referencia}
    hoy, salida = date.today(), []
    for f in leer(contenido, nombre):
        problemas = []
        serie = series.get(f["codigo"].strip())
        if serie is None:
            problemas.append(f"El código {f['codigo']} no es una serie ni subserie del cuadro.")
        acceso = _acceso(f)
        if acceso is None:
            problemas.append("No se reconoce la categoría de acceso (pública, clasificada o reservada).")
        fundamento = " ".join((f.get("fundamento") or "").split())
        if len(fundamento) < 5:
            problemas.append("Falta el fundamento legal.")
        plazo = _plazo(f.get("plazo", ""), hoy) if acceso and acceso != "publico" else None
        if acceso and acceso != "publico":
            if plazo is None:
                problemas.append("La clasificación o la reserva necesita su plazo (una fecha o «N años»).")
            elif plazo <= hoy:
                problemas.append("El plazo de la restricción ya pasó.")
            elif plazo > hoy.replace(year=hoy.year + tca.MAXIMO_ANIOS):
                problemas.append(f"La restricción no puede pasar de {tca.MAXIMO_ANIOS} años (Ley 1712 de 2014, art. 22).")
        salida.append({"fila": f["fila"], "codigo": f["codigo"], "serie": serie.titulo if serie else (f.get("nombre") or None),
                       "serie_id": str(serie.id) if serie else None, "acceso": acceso,
                       "acceso_nombre": tca.ACCESO.get(acceso) if acceso else None, "fundamento": fundamento or None,
                       "vigente_hasta": plazo.isoformat() if plazo else None,
                       "reproduccion": _reproduccion(f.get("reproduccion", ""), acceso or "publico"),
                       "condiciones": (f.get("condiciones") or "").strip() or None,
                       "responsable": (f.get("responsable") or "").strip() or None, "problemas": problemas})
    validas = sum(1 for x in salida if not x["problemas"])
    return {"filas": salida, "validas": validas, "con_problemas": len(salida) - validas}


def aplicar(db: Session, fondo: RecursoDocumental, contenido: bytes, nombre: str, usuario_id, ip: str | None = None) -> dict:
    from app.servicios import tca
    from app.servicios.auditoria import registrar

    previa = vista_previa(db, fondo, contenido, nombre)
    aplicadas = 0
    for f in previa["filas"]:
        if f["problemas"]:
            continue
        serie = db.get(RecursoDocumental, f["serie_id"])
        tca.declarar(db, serie, acceso=f["acceso"], fundamento=f["fundamento"], reproduccion=f["reproduccion"],
                     vigente_hasta=date.fromisoformat(f["vigente_hasta"]) if f["vigente_hasta"] else None,
                     condiciones=f["condiciones"], responsable=f["responsable"], usuario_id=usuario_id, ip=ip)
        aplicadas += 1
    registrar(db, modulo="descripcion", accion="tca_importada", usuario_id=usuario_id, entidad_tipo="recurso_documental",
              entidad_id=fondo.id, ip=ip, detalle=f"TCA importada de «{nombre}»: {aplicadas} serie(s) declaradas; "
                                                  f"{previa['con_problemas']} fila(s) fuera por sus problemas.")
    return {**previa, "aplicadas": aplicadas}
