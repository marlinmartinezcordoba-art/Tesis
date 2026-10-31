"""
Versiones de la TRD: archivo original, comparación y registros afectados (fase B: requisitos 3 y 7).

- El archivo de cada carga se guarda tal como llegó, por su huella SHA-256 (si se sube dos veces
  el mismo, se guarda una sola copia), y cada fila de la matriz dice de qué archivo y de qué fila
  salió.
- Dos versiones se comparan serie por serie, por su código compuesto (110.2, 110.2.1): qué series
  se agregan, cuáles se retiran y qué cambió en cada una (tipos documentales, años en archivo de
  gestión y central, disposición final, soporte, procedimiento, función, dependencia).
- Los registros afectados por la versión nueva son los expedientes y documentos de las series
  que cambian o se retiran. Cada uno se rige por la TRD vigente en su fecha final (Acuerdo AGN 004
  de 2019): los cerrados antes de que rija la nueva conservan la anterior; los abiertos o cerrados
  después pasan a la nueva.
- Cada descripción guarda la versión que regía cuando se clasificó (`clasificar`).
"""

import hashlib
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental
from app.models.trd import CargaInstrumento, VersionTrd
from app.servicios import almacen
from app.servicios.auditoria import registrar

CAMPOS = {"dependencia": "Dependencia", "nombre": "Nombre", "nombres_tipos": "Tipos documentales",
          "gestion": "Años en archivo de gestión", "central": "Años en archivo central",
          "disposicion": "Disposición final", "otras_disposiciones": "Otras disposiciones", "soporte": "Soporte",
          "procedimiento": "Procedimiento", "funcion": "Función que la produce"}
DISPOSICION = {"ct": "Conservación total", "e": "Eliminación", "s": "Selección", "m": "Medio técnico"}
MUESTRA = 25  # registros que se nombran por serie; el resto se cuenta


# --- Archivo original ----------------------------------------------------------------------------------


def guardar_original(contenido: bytes, nombre: str) -> dict:
    """Guarda el archivo leído por su huella (una sola copia por contenido) y devuelve cómo citarlo."""
    huella = hashlib.sha256(contenido).hexdigest()
    ruta = f"instrumentos/{huella}{almacen.extension_segura(nombre)}"
    destino = almacen.ruta_absoluta(ruta)
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)
    return {"huella": huella, "archivo": (nombre or "archivo")[:300], "tamano": len(contenido), "ruta": ruta}


def registrar_carga(db: Session, fondo: RecursoDocumental, v: VersionTrd, original: dict,
                    usuario_id: uuid.UUID) -> CargaInstrumento | None:
    """La carga, si el archivo que dice la vista previa está de verdad guardado con esa huella."""
    huella = (original.get("huella") or "").lower()
    if len(huella) != 64 or not all(c in "0123456789abcdef" for c in huella):
        return None
    ruta = f"instrumentos/{huella}{almacen.extension_segura(original.get('archivo') or '')}"
    destino = almacen.ruta_absoluta(ruta)
    if not destino.exists() or hashlib.sha256(destino.read_bytes()).hexdigest() != huella:
        return None
    c = CargaInstrumento(id=uuid.uuid4(), fondo_id=fondo.id, version_id=v.id,
                         archivo=(original.get("archivo") or "archivo")[:300], huella=huella,
                         tamano=destino.stat().st_size, ruta=ruta, origen=(original.get("origen") or None),
                         filas_cargadas=0, cargado_por_id=usuario_id)
    db.add(c)
    db.flush()
    registrar(db, modulo="instrumentos", accion="trd_archivo_original", usuario_id=usuario_id,
              entidad_tipo="recurso_documental", entidad_id=fondo.id,
              detalle=f"{v.nombre}: archivo original «{c.archivo}»", nuevo={"huella": huella, "tamano": c.tamano})
    return c


def cargas_de(db: Session, v: VersionTrd) -> list[dict]:
    return [{"id": str(c.id), "archivo": c.archivo, "huella": c.huella, "tamano": c.tamano, "origen": c.origen,
             "filas_cargadas": c.filas_cargadas, "cargado_en": c.cargado_en.isoformat()}
            for c in db.scalars(select(CargaInstrumento).where(CargaInstrumento.version_id == v.id)
                                .order_by(CargaInstrumento.cargado_en))]


# --- Comparar dos versiones -----------------------------------------------------------------------------


def _por_codigo(db: Session, v: VersionTrd) -> dict[str, dict]:
    from app.servicios.parametrizacion_trd import filas

    salida = {}
    for f in filas(db, v):
        f["nombre"] = f["subserie"] or f["serie"]
        salida[f["codigo"] or f"sin código: {f['nombre']}"] = f
    return salida


def _legible(campo: str, valor):
    if valor in (None, "", []):
        return "—"
    if campo == "disposicion":
        return DISPOSICION.get(valor, valor)
    if campo == "otras_disposiciones":
        return ", ".join(DISPOSICION.get(x, x) for x in valor)
    if campo == "nombres_tipos":
        return ", ".join(valor)
    return valor


def comparar(db: Session, anterior: VersionTrd, nueva: VersionTrd) -> dict:
    a, b = _por_codigo(db, anterior), _por_codigo(db, nueva)
    cambiadas = []
    for codigo in sorted(set(a) & set(b)):
        diferencias = []
        for campo, etiqueta in CAMPOS.items():
            va, vb = a[codigo].get(campo), b[codigo].get(campo)
            if campo == "nombres_tipos":
                quitados, puestos = sorted(set(va or []) - set(vb or [])), sorted(set(vb or []) - set(va or []))
                if quitados or puestos:
                    diferencias.append({"campo": campo, "etiqueta": etiqueta, "quitados": quitados, "agregados": puestos})
                continue
            if (va or None) != (vb or None):
                diferencias.append({"campo": campo, "etiqueta": etiqueta, "antes": _legible(campo, va),
                                    "despues": _legible(campo, vb)})
        if diferencias:
            cambiadas.append({"codigo": codigo, "nombre": b[codigo]["nombre"], "dependencia": b[codigo]["dependencia"],
                              "diferencias": diferencias})
    breve = lambda f, c: {"codigo": c, "nombre": f["nombre"], "dependencia": f["dependencia"]}  # noqa: E731
    deps_a = {f["codigo_dependencia"]: f["dependencia"] for f in a.values()}
    deps_b = {f["codigo_dependencia"]: f["dependencia"] for f in b.values()}
    return {
        "anterior": {"id": str(anterior.id), "nombre": anterior.nombre},
        "nueva": {"id": str(nueva.id), "nombre": nueva.nombre},
        "agregadas": [breve(b[c], c) for c in sorted(set(b) - set(a))],
        "retiradas": [breve(a[c], c) for c in sorted(set(a) - set(b))],
        "cambiadas": cambiadas,
        "sin_cambio": len(set(a) & set(b)) - len(cambiadas),
        "dependencias_nuevas": [{"codigo": c, "nombre": n} for c, n in sorted(deps_b.items(), key=lambda x: str(x[0]))
                                if c not in deps_a],
        "dependencias_retiradas": [{"codigo": c, "nombre": n} for c, n in sorted(deps_a.items(), key=lambda x: str(x[0]))
                                   if c not in deps_b],
    }


# --- Registros afectados --------------------------------------------------------------------------------


def afectados(db: Session, nueva: VersionTrd, comparacion: dict) -> dict:
    """Los expedientes y documentos de las series que cambian o se retiran, según qué TRD los rige."""
    from app.servicios import retencion

    codigos = {c["codigo"]: ("cambia", c["nombre"]) for c in comparacion["cambiadas"]}
    codigos |= {c["codigo"]: ("se_retira", c["nombre"]) for c in comparacion["retiradas"]}
    if not codigos:
        return {"series": [], "total": 0, "pasan_a_la_nueva": 0, "conservan_la_anterior": 0,
                "desde": nueva.vigente_desde.isoformat() if nueva.vigente_desde else None}
    todos = list(db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == nueva.fondo_id)))
    hijos = defaultdict(list)
    for r in todos:
        if r.incluido_en_id and r.id != r.fondo_id:
            hijos[r.incluido_en_id].append(r)
    desde = nueva.vigente_desde
    series, total, nuevos, anteriores = [], 0, 0, 0
    for r in todos:
        if r.nivel not in ("serie", "subserie") or r.codigo_referencia not in codigos:
            continue
        motivo, nombre = codigos[r.codigo_referencia]
        pila, registros = list(hijos.get(r.id, [])), []
        while pila:
            x = pila.pop()
            pila.extend(hijos.get(x.id, []))
            if x.nivel in ("expediente", "unidad_documental") and x.publicado_en is not None:
                registros.append(x)
        if not registros:
            continue
        filas = []
        for x in registros:
            fin = retencion._fecha_de(x)
            # Se valora con la TRD vigente en su fecha final; sin fecha final (abierto) o cerrado después, la nueva.
            rige = "nueva" if desde is None or fin is None or fin >= desde else "anterior"
            filas.append({"id": str(x.id), "titulo": x.titulo, "nivel": x.nivel, "codigo": x.codigo_referencia,
                          "fecha_final": fin.isoformat() if fin else None, "rige": rige})
        n_nueva = sum(1 for f in filas if f["rige"] == "nueva")
        total += len(filas)
        nuevos += n_nueva
        anteriores += len(filas) - n_nueva
        filas.sort(key=lambda f: (f["rige"] != "nueva", f["titulo"]))
        series.append({"codigo": r.codigo_referencia, "nombre": nombre, "motivo": motivo, "total": len(filas),
                       "pasan_a_la_nueva": n_nueva, "conservan_la_anterior": len(filas) - n_nueva,
                       "registros": filas[:MUESTRA]})
    series.sort(key=lambda s: s["codigo"] or "")
    return {"series": series, "total": total, "pasan_a_la_nueva": nuevos, "conservan_la_anterior": anteriores,
            "desde": desde.isoformat() if desde else None}


def comparar_con_afectados(db: Session, v: VersionTrd, con: VersionTrd | None = None) -> dict:
    """La versión frente a otra: por defecto, un borrador frente a la vigente, y una aplicada frente a la anterior."""
    if con is None:
        candidatas = list(db.scalars(select(VersionTrd).where(
            VersionTrd.fondo_id == v.fondo_id, VersionTrd.instrumento == v.instrumento, VersionTrd.id != v.id,
            VersionTrd.estado.in_(("vigente", "historica"))).order_by(VersionTrd.numero.desc())))
        con = next((x for x in candidatas if x.numero < v.numero), None) if v.estado != "borrador" else \
            next((x for x in candidatas if x.estado == "vigente"), None)
    if con is None:
        return {"comparable": False, "explicacion": "No hay otra versión con qué compararla: es la primera."}
    anterior, nueva = (con, v) if con.numero < v.numero else (v, con)
    c = comparar(db, anterior, nueva)
    return {"comparable": True, **c, "afectados": afectados(db, nueva, c)}


# --- Con qué versión se clasificó -----------------------------------------------------------------------


def clasificar(db: Session, recurso: RecursoDocumental, reclasificado: bool = False) -> None:
    """Anota la TRD que rige hoy en la descripción que se publica en su lugar del cuadro (requisito 7).
    Se anota una vez; solo cambia si la descripción se mueve a otro lugar del cuadro."""
    if recurso.nivel == "fondo" or (recurso.version_trd_id is not None and not reclasificado):
        return
    vigente = db.scalar(select(VersionTrd.id).where(VersionTrd.fondo_id == recurso.fondo_id,
                                                    VersionTrd.instrumento == "trd", VersionTrd.estado == "vigente"))
    if vigente is not None and recurso.version_trd_id != vigente:
        recurso.version_trd_id = vigente
