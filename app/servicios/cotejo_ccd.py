"""
Cotejo del cuadro de clasificación (CCD) con una versión de la TRD (fase C, requisito 4).

El CCD y la TRD deben describir las mismas dependencias, series y subseries: toda serie del
cuadro necesita su regla de retención, y la TRD no puede retener series que el cuadro no tiene.
Cuando la entidad los entrega por separado (como el CCD y la TRD de MinAmbiente), no siempre
coinciden. El cotejo los compara por código compuesto (110, 110.2, 110.2.1) y dice:

- series y subseries del CCD que la TRD no tiene: quedarían sin retención (lo más grave);
- series y subseries de la TRD que el CCD no tiene;
- el mismo código con otro nombre;
- la misma serie en otra dependencia;
- dependencias que están en uno y no en el otro, o con otro nombre.

Si algo no coincide, deja una alerta en el panel. No corrige nada: decide la persona.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental
from app.models.trd import CargaInstrumento, VersionTrd
from app.servicios import cuadro
from app.servicios.auditoria import registrar


def _n(texto: str | None) -> str:
    from app.servicios.parametrizacion_trd import _norm

    return _norm(texto or "")


def _del_ccd(filas_leidas: list[dict]) -> tuple[dict, dict, dict]:
    """Del CCD: dependencias, series y subseries por código compuesto."""
    deps, series, subseries = {}, {}, {}
    for d in filas_leidas:
        f = cuadro.FilaCuadro.de_dict(d)
        if f.problemas:
            continue
        c = cuadro.codigos_compuestos(f)
        dep_codigo = c["subseccion"] or c["seccion"]
        dep_nombre = (f.subseccion or f.seccion).nombre if (f.subseccion or f.seccion) else ""
        # La dependencia que produce la serie (la subsección, o la sección si no hay), como en la TRD.
        if dep_codigo:
            deps.setdefault(dep_codigo, dep_nombre)
        if c["serie"] and f.serie:
            series.setdefault(c["serie"], {"nombre": f.serie.nombre, "dependencia": dep_nombre, "codigo_dependencia": dep_codigo,
                                           "fila": f.fila, "parte": f.parte})
        if c["subserie"] and f.subserie:
            subseries.setdefault(c["subserie"], {"nombre": f.subserie.nombre, "dependencia": dep_nombre,
                                                 "codigo_dependencia": dep_codigo, "fila": f.fila, "parte": f.parte})
    return deps, series, subseries


def _de_la_trd(db: Session, v: VersionTrd) -> tuple[dict, dict, dict]:
    from app.servicios.parametrizacion_trd import filas

    deps, series, subseries = {}, {}, {}
    for f in filas(db, v):
        deps.setdefault(f["codigo_dependencia"], f["dependencia"])
        datos = {"dependencia": f["dependencia"], "codigo_dependencia": f["codigo_dependencia"]}
        if f["codigo_serie"]:
            series.setdefault(f["codigo_serie"], {"nombre": f["serie"], **datos})
        if f["subserie"] and f["codigo"]:
            subseries.setdefault(f["codigo"], {"nombre": f["subserie"], **datos})
    return deps, series, subseries


def cotejar(db: Session, v: VersionTrd, filas_ccd: list[dict]) -> dict:
    deps_c, series_c, sub_c = _del_ccd(filas_ccd)
    deps_t, series_t, sub_t = _de_la_trd(db, v)
    if not series_c:
        from app.servicios.parametrizacion_trd import ErrorTrd

        raise ErrorTrd("El archivo no trae series reconocibles: no se puede cotejar como CCD.", 422)

    def faltan(origen: dict, destino: dict, nivel: str) -> list[dict]:
        return [{"codigo": k, "nivel": nivel, **{x: origen[k][x] for x in ("nombre", "dependencia")},
                 **({"fila": origen[k].get("fila"), "parte": origen[k].get("parte")} if "fila" in origen[k] else {})}
                for k in sorted(set(origen) - set(destino), key=str)]

    def distintos(campo: str, nivel: str, a: dict, b: dict) -> list[dict]:
        salida = []
        for k in sorted(set(a) & set(b), key=str):
            va, vb = (a[k][campo], b[k][campo])
            if (_n(va) if campo == "nombre" else (va or "")) != (_n(vb) if campo == "nombre" else (vb or "")):
                salida.append({"codigo": k, "nivel": nivel, "en_ccd": a[k]["dependencia" if campo == "codigo_dependencia" else campo],
                               "en_trd": b[k]["dependencia" if campo == "codigo_dependencia" else campo],
                               "nombre": b[k]["nombre"]})
        return salida

    informe = {
        "version": {"id": str(v.id), "nombre": v.nombre},
        "sin_retencion": faltan(series_c, series_t, "serie") + faltan(sub_c, sub_t, "subserie"),
        "solo_en_trd": faltan(series_t, series_c, "serie") + faltan(sub_t, sub_c, "subserie"),
        "nombre_distinto": distintos("nombre", "serie", series_c, series_t) + distintos("nombre", "subserie", sub_c, sub_t),
        "otra_dependencia": distintos("codigo_dependencia", "serie", series_c, series_t)
                            + distintos("codigo_dependencia", "subserie", sub_c, sub_t),
        "dependencias": {
            "solo_en_ccd": [{"codigo": k, "nombre": deps_c[k]} for k in sorted(set(deps_c) - set(deps_t), key=str)],
            "solo_en_trd": [{"codigo": k, "nombre": deps_t[k]} for k in sorted(set(deps_t) - set(deps_c), key=str)],
            "nombre_distinto": [{"codigo": k, "en_ccd": deps_c[k], "en_trd": deps_t[k]}
                                for k in sorted(set(deps_c) & set(deps_t), key=str) if _n(deps_c[k]) != _n(deps_t[k])],
        },
        "coinciden": len((set(series_c) & set(series_t)) | (set(sub_c) & set(sub_t))),
        "totales": {"series_ccd": len(series_c), "subseries_ccd": len(sub_c), "series_trd": len(series_t),
                    "subseries_trd": len(sub_t)},
    }
    informe["diferencias"] = (len(informe["sin_retencion"]) + len(informe["solo_en_trd"]) + len(informe["nombre_distinto"])
                              + len(informe["otra_dependencia"]) + sum(len(x) for x in informe["dependencias"].values()))
    return informe


def _alertar(db: Session, v: VersionTrd, informe: dict, archivo: str) -> None:
    from app.servicios import alertas

    if not informe["diferencias"]:
        pendiente = alertas.pendiente(db, "ccd_trd_no_coinciden", v.id)
        if pendiente is not None:
            alertas.atender(db, pendiente, None, "Un cotejo posterior ya no encontró diferencias.")
        return
    partes = [f"{len(informe['sin_retencion'])} serie(s) o subserie(s) del CCD sin retención en la TRD"
              if informe["sin_retencion"] else None,
              f"{len(informe['solo_en_trd'])} de la TRD que no están en el CCD" if informe["solo_en_trd"] else None,
              f"{len(informe['nombre_distinto'])} con otro nombre" if informe["nombre_distinto"] else None,
              f"{len(informe['otra_dependencia'])} en otra dependencia" if informe["otra_dependencia"] else None]
    alertas.crear(db, tipo="ccd_trd_no_coinciden", severidad="alta" if informe["sin_retencion"] else "media",
                  modulo="instrumentos", entidad_tipo="version_trd", entidad_id=v.id, fondo_id=v.fondo_id,
                  mensaje=f"El CCD «{archivo}» y la {v.nombre} no coinciden: " + "; ".join(p for p in partes if p)
                          + ". Revíselo en TRD y CCD, paso 2.",
                  detalle={"diferencias": informe["diferencias"]})


def cotejar_y_guardar(db: Session, v: VersionTrd, filas_ccd: list[dict], original: dict | None,
                      usuario_id: uuid.UUID) -> dict:
    from app.servicios import versiones_trd

    informe = cotejar(db, v, filas_ccd)
    fondo = db.get(RecursoDocumental, v.fondo_id)
    carga = versiones_trd.registrar_carga(db, fondo, v, original, usuario_id, clase="ccd") if original else None
    archivo = carga.archivo if carga else (original or {}).get("archivo") or "sin archivo"
    informe["archivo"] = {"carga": str(carga.id), "archivo": carga.archivo, "huella": carga.huella} if carga else None
    if carga is not None:
        carga.informe = informe
        carga.filas_cargadas = informe["totales"]["series_ccd"] + informe["totales"]["subseries_ccd"]
    _alertar(db, v, informe, archivo)
    registrar(db, modulo="instrumentos", accion="ccd_cotejado", usuario_id=usuario_id, entidad_tipo="recurso_documental",
              entidad_id=v.fondo_id, detalle=f"CCD «{archivo}» cotejado con la {v.nombre}",
              nuevo={"diferencias": informe["diferencias"], "coinciden": informe["coinciden"]})
    return informe


def ultimo(db: Session, v: VersionTrd) -> dict | None:
    c = db.scalar(select(CargaInstrumento).where(CargaInstrumento.version_id == v.id, CargaInstrumento.clase == "ccd")
                  .order_by(CargaInstrumento.cargado_en.desc()).limit(1))
    if c is None or c.informe is None:
        return None
    return {**c.informe, "cotejado_en": c.cargado_en.isoformat()}


def repetir(db: Session, v: VersionTrd, usuario_id: uuid.UUID) -> dict:
    """Vuelve a cotejar el último CCD guardado con la versión tal como está ahora (después de corregir)."""
    from app.servicios import almacen
    from app.servicios.parametrizacion_trd import ErrorTrd

    c = db.scalar(select(CargaInstrumento).where(CargaInstrumento.version_id == v.id, CargaInstrumento.clase == "ccd")
                  .order_by(CargaInstrumento.cargado_en.desc()).limit(1))
    if c is None:
        raise ErrorTrd("Todavía no se ha cotejado ningún CCD con esta versión.", 404)
    contenido = almacen.ruta_absoluta(c.ruta).read_bytes()
    filas_leidas, _ = cuadro.interpretar(contenido, c.archivo)
    return cotejar_y_guardar(db, v, [f.a_dict() for f in filas_leidas],
                             {"huella": c.huella, "archivo": c.archivo, "origen": c.origen}, usuario_id)
