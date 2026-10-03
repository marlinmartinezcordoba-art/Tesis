"""
Módulo 5 · Preservación digital.

Trabaja solo sobre la Instantiation (RiC-E06), nunca sobre el Record
Resource. Tres piezas:

- integridad: recalcula la huella SHA-256 y la compara con la registrada
  en la ingesta (PREMIS fixity check), de forma periódica y a pedido;
- riesgo de obsolescencia: servicios/riesgo.py, llevado al panel central
  de alertas (el mismo mecanismo de todo el sistema);
- migración de formato: siempre aprobada por una persona. Si el destino
  está en la tabla de formatos soportados, la hace el sistema con una
  herramienta madura (Ghostscript, Pillow); si no, registra la solicitud y
  espera el archivo convertido por fuera. En los dos casos se crea una
  Instantiation nueva enlazada por RiC-R015 migrated into; la original no
  se modifica ni se borra nunca.
- segunda copia (servicios/segunda_copia.py): cada verificación compara
  también la segunda copia; su alteración o pérdida tiene alerta propia.
  Si la primaria se daña, se puede restaurar desde la segunda copia, con
  aprobación y sin borrar el archivo dañado (queda en cuarentena).

El paquete de información de archivo (AIP) con PREMIS está en
servicios/paquete.py.
"""

import fnmatch
import hashlib
import logging
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Callable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.alerta import Alerta
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.parametro import Parametro
from app.models.preservacion import Migracion, Restauracion, SegundaCopia, VerificacionIntegridad
from app.models.recurso_documental import RecursoDocumental
from app.servicios import alertas, almacen, derechos, formato, mecanismos, parametros, riesgo, segunda_copia
from app.servicios.auditoria import registrar

log = logging.getLogger("ricora.preservacion")

TIPOS_ALERTA = ("integridad_alterada", "segunda_copia_alterada", "riesgo_obsolescencia", "formato_no_identificado")
TIPOS_INTEGRIDAD = ("integridad_alterada", "segunda_copia_alterada")


class ErrorPreservacion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


# --- Formatos destino y conversores -------------------------------------------------------------


@dataclass(frozen=True)
class Destino:
    clave: str
    nombre: str
    extension: str
    puids: frozenset  # lo que Siegfried debe reconocer en el resultado; vacío = no se exige


DESTINOS = {d.clave: d for d in [
    Destino("pdfa_2b", "PDF/A-2b (ISO 19005-2)", ".pdf", frozenset(riesgo.PDFA)),
    Destino("tiff", "TIFF sin pérdida", ".tif", frozenset(riesgo.TIFF)),
    Destino("png", "PNG", ".png", frozenset(riesgo.PNG)),
    Destino("jpeg2000", "JPEG 2000", ".jp2", frozenset(riesgo.JPEG2000)),
    Destino("odt", "OpenDocument texto (ODT)", ".odt", frozenset()),
    Destino("txt", "Texto plano UTF-8", ".txt", frozenset()),
    Destino("csv", "CSV", ".csv", frozenset()),
    Destino("xml", "XML", ".xml", frozenset()),
]}


@dataclass(frozen=True)
class Ejecucion:
    """Quién convirtió (programa y versión exacta, que pasan a ser el agente
    mecanismo del vocabulario) y qué hizo (parámetros)."""
    programa: str
    version: str
    parametros: str


def _pdfa_ghostscript(entrada: Path, salida: Path) -> Ejecucion:
    """PDF/PostScript → PDF/A-2b con Ghostscript, con perfil de color sRGB
    incrustado (OutputIntent), como exige ISO 19005."""
    binario = settings.ghostscript_binario
    icc = _perfil_srgb(binario)
    definicion = salida.with_suffix(".def.ps")
    definicion.write_text(
        "%!\n"
        f"/ICCProfile ({icc}) def\n"
        "[/_objdef {icc_PDFA} /type /stream /OBJ pdfmark\n"
        "[{icc_PDFA} <</N 3>> /PUT pdfmark\n"
        "[{icc_PDFA} ICCProfile (r) file /PUT pdfmark\n"
        "[/_objdef {OutputIntent_PDFA} /type /dict /OBJ pdfmark\n"
        "[{OutputIntent_PDFA} <</Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {icc_PDFA} "
        "/OutputConditionIdentifier (sRGB)>> /PUT pdfmark\n"
        "[{Catalog} <</OutputIntents [ {OutputIntent_PDFA} ]>> /PUT pdfmark\n")
    try:
        r = subprocess.run([binario, "-q", "-dPDFA=2", "-dBATCH", "-dNOPAUSE", "-dSAFER", "-dNOOUTERSAVE",
                            "-sColorConversionStrategy=RGB", "-sDEVICE=pdfwrite", "-dPDFACompatibilityPolicy=1",
                            f"--permit-file-read={icc}", f"-sOutputFile={salida}", str(definicion), str(entrada)],
                           capture_output=True, timeout=settings.segundos_por_paso, check=False)
    except FileNotFoundError as exc:
        raise ErrorPreservacion("Ghostscript no está instalado en el servidor.", 503) from exc
    except subprocess.TimeoutExpired as exc:
        raise ErrorPreservacion("La conversión tardó demasiado y se detuvo.") from exc
    finally:
        definicion.unlink(missing_ok=True)
    if r.returncode != 0 or not salida.exists() or salida.stat().st_size == 0:
        raise ErrorPreservacion("Ghostscript no pudo convertir el archivo: "
                                + r.stderr.decode("utf-8", "replace").strip()[:200])
    return Ejecucion("Ghostscript", _version([binario, "--version"]), "pdfwrite, PDF/A-2b, perfil sRGB")


def _perfil_srgb(binario: str) -> str:
    candidatos = sorted(Path("/usr/share/ghostscript").glob("*/iccprofiles/srgb.icc")) + [
        Path("/usr/share/color/icc/ghostscript/srgb.icc")]
    for c in candidatos:
        if c.exists():
            return str(c)
    raise ErrorPreservacion("No se encontró el perfil de color sRGB de Ghostscript.", 503)


def _tiff_pillow(entrada: Path, salida: Path) -> Ejecucion:
    """Imagen → TIFF sin pérdida (LZW), todas las páginas, con Pillow."""
    import PIL
    from PIL import Image, ImageSequence

    try:
        with Image.open(entrada) as imagen:
            paginas = [p.convert("RGB") if p.mode not in ("RGB", "L", "1", "RGBA") else p.copy()
                       for p in ImageSequence.Iterator(imagen)]
            dpi = imagen.info.get("dpi")
    except Exception as exc:  # Pillow lanza varios tipos según el formato
        raise ErrorPreservacion(f"No se pudo leer la imagen: {exc}") from exc
    opciones = {"compression": "tiff_lzw", "save_all": True, "append_images": paginas[1:]}
    if dpi:
        opciones["dpi"] = dpi
    paginas[0].save(salida, format="TIFF", **opciones)
    return Ejecucion("Pillow", PIL.__version__, "TIFF, compresión LZW sin pérdida")


def _version(argumentos: list[str]) -> str:
    try:
        return subprocess.run(argumentos, capture_output=True, timeout=10).stdout.decode().strip()[:40]
    except (OSError, subprocess.TimeoutExpired):
        return ""


@dataclass(frozen=True)
class Conversor:
    clave: str
    nombre: str
    destino: str
    ejecutar: Callable[[Path, Path], Ejecucion]


CONVERSORES = {c.clave: c for c in [
    Conversor("ghostscript_pdfa", "Ghostscript (PDF → PDF/A-2b)", "pdfa_2b", _pdfa_ghostscript),
    Conversor("pillow_tiff", "Pillow (imagen → TIFF)", "tiff", _tiff_pillow),
]}

FORMATOS_POR_DEFECTO = [
    {"id": "texto-pdfa", "origen": "Documentos de texto en PDF", "origen_mime": ["application/pdf", "application/postscript"],
     "destino": "pdfa_2b", "conversor": "ghostscript_pdfa", "activo": True},
    {"id": "imagen-tiff", "origen": "Imágenes", "origen_mime": ["image/*"],
     "destino": "tiff", "conversor": "pillow_tiff", "activo": True},
]


def formatos_soportados(db: Session) -> list[dict]:
    valor = parametros.leer(db, "preservacion_formatos")
    return valor if valor is not None else FORMATOS_POR_DEFECTO


def _ya_es(inst: Instanciacion, destino: Destino) -> bool:
    return bool(destino.puids) and inst.formato_puid in destino.puids


def fila_soportada(db: Session, inst: Instanciacion, destino: str) -> dict | None:
    """La fila activa de la tabla que permite convertir esta instanciación
    a ese destino de forma automática, si existe."""
    mime = (inst.formato_mime or "").lower()
    for fila in formatos_soportados(db):
        if fila["activo"] and fila["destino"] == destino and any(fnmatch.fnmatch(mime, p.lower()) for p in fila["origen_mime"]):
            return fila
    return None


def destinos_para(db: Session, inst: Instanciacion) -> list[dict]:
    salida = []
    for d in DESTINOS.values():
        if _ya_es(inst, d):
            continue
        fila = fila_soportada(db, inst, d.clave)
        salida.append({"clave": d.clave, "nombre": d.nombre, "automatica": fila is not None,
                       "conversor": CONVERSORES[fila["conversor"]].nombre if fila else None})
    return sorted(salida, key=lambda d: (not d["automatica"], d["nombre"]))


# --- Integridad ---------------------------------------------------------------------------------


def huella_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while bloque := f.read(almacen.TAMANO_BLOQUE):
            h.update(bloque)
    return h.hexdigest()


def verificar(db: Session, inst: Instanciacion, *, origen: str, usuario_id: uuid.UUID | None = None,
              ip: str | None = None) -> VerificacionIntegridad:
    """Recalcula la huella de la copia primaria y de la segunda copia y las
    compara con la registrada en la ingesta (y, por tanto, entre sí).
    Primaria alterada o ausente → alerta «integridad_alterada»; segunda copia
    alterada o ausente → alerta «segunda_copia_alterada». No corrige nada
    sola. Si aún no hay segunda copia y la primaria está íntegra, la crea."""
    try:
        calculada = huella_de(almacen.ruta_absoluta(inst.ruta))
        resultado = "integra" if calculada == inst.huella else "alterada"
    except (FileNotFoundError, ValueError):
        calculada, resultado = None, "ausente"
    copia = segunda_copia.vigente(db, inst.id)
    res_copia, huella_copia = segunda_copia.comprobar(copia, inst.huella)
    # Referencia independiente de la base (manifiesto de la segunda copia):
    # si no coincide con la huella registrada, lo alterado es la referencia.
    referencia = segunda_copia.huella_de_manifiesto(inst)
    if referencia is not None and referencia != inst.huella:
        archivos_bien = calculada == referencia and (huella_copia in (None, referencia))
        alertas.crear(db, tipo="huella_referencia_alterada", severidad="alta", modulo="preservacion",
                      entidad_tipo="instanciacion", entidad_id=inst.id, fondo_id=inst.fondo_id,
                      mensaje=(f"«{inst.nombre_original}»: la huella registrada en la base no coincide con el manifiesto "
                               "de la segunda copia" + (". Los archivos coinciden con el manifiesto: lo alterado es "
                                                        "la base de datos, no el documento." if archivos_bien else ".")),
                      detalle={"huella_base": inst.huella, "huella_manifiesto": referencia, "huella_primaria": calculada,
                               "huella_segunda_copia": huella_copia})
    if res_copia == "sin_copia" and resultado == "integra":
        copia = segunda_copia.asegurar(db, inst, "pendiente")
        res_copia, huella_copia = segunda_copia.comprobar(copia, inst.huella)
    v = VerificacionIntegridad(instanciacion_id=inst.id, resultado=resultado, algoritmo=inst.algoritmo_huella,
                               huella_registrada=inst.huella, huella_calculada=calculada, origen=origen,
                               usuario_id=usuario_id, segunda_copia_id=copia.id if copia else None,
                               segunda_copia_resultado=res_copia, segunda_copia_huella=huella_copia,
                               mecanismo_id=mecanismos.del_sistema(db, inst.fondo_id).id)
    db.add(v)
    inst.estado_integridad, inst.ultima_verificacion_en = resultado, ahora()
    if resultado != "integra":
        mensaje = (f"«{inst.nombre_original}»: la huella digital ya no coincide con la registrada en la ingesta "
                   "(el archivo cambió)." if resultado == "alterada" else
                   f"«{inst.nombre_original}»: el archivo no está en el almacenamiento.")
        if res_copia == "integra":
            mensaje += " La segunda copia está íntegra: se puede restaurar desde ella."
        alertas.crear(db, tipo="integridad_alterada", severidad="alta", modulo="preservacion",
                      entidad_tipo="instanciacion", entidad_id=inst.id, fondo_id=inst.fondo_id, mensaje=mensaje,
                      detalle={"resultado": resultado, "huella_registrada": inst.huella, "huella_calculada": calculada,
                               "segunda_copia": res_copia})
    if copia is not None:
        copia.ultima_verificacion_en = ahora()
        copia.estado = "sincronizada" if res_copia == "integra" else res_copia
    if res_copia in ("alterada", "ausente"):
        mensaje = (f"«{inst.nombre_original}»: la segunda copia ya no coincide con la huella de la ingesta."
                   if res_copia == "alterada" else f"«{inst.nombre_original}»: la segunda copia no está en su lugar.")
        alertas.crear(db, tipo="segunda_copia_alterada", severidad="alta", modulo="preservacion",
                      entidad_tipo="instanciacion", entidad_id=inst.id, fondo_id=inst.fondo_id, mensaje=mensaje,
                      detalle={"resultado": res_copia, "ubicacion": copia.ubicacion, "huella_registrada": inst.huella,
                               "huella_calculada": huella_copia})
    registrar(db, modulo="preservacion", accion="integridad_verificada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip,
              nuevo={"resultado": resultado, "segunda_copia": res_copia, "origen": origen}, detalle=inst.nombre_original)
    db.flush()
    return v


def _verificables(db: Session):
    return select(Instanciacion).where(Instanciacion.estado == "listo_para_descripcion", Instanciacion.huella.is_not(None))


CLAVE_ULTIMA_VERIFICACION = "preservacion_ultima_verificacion"


LOTE_VERIFICACION = 20
MARGEN_ATRASO = timedelta(days=2)


def vencidas(db: Session, dias: int):
    """Instanciaciones cuya última verificación es más vieja que la
    frecuencia (o que nunca se verificaron)."""
    limite = ahora() - timedelta(days=dias)
    return _verificables(db).where(or_(Instanciacion.ultima_verificacion_en.is_(None),
                                       Instanciacion.ultima_verificacion_en < limite))


def verificacion_periodica(db: Session, lote: int = LOTE_VERIFICACION) -> int | None:
    """La llama el trabajador en cada vuelta. Verifica por antigüedad, en
    lotes: toma las instanciaciones que llevan más de N días sin
    verificarse (las más viejas primero). Así un reinicio del trabajador a
    mitad de camino no salta nada: en la vuelta siguiente sigue con las que
    faltan (hallazgo PRE-08). Devuelve cuántas verificó, o None si ninguna
    estaba vencida."""
    dias = int(parametros.leer(db, "preservacion_frecuencia_dias"))
    ids = db.scalars(vencidas(db, dias).with_only_columns(Instanciacion.id)
                     .order_by(Instanciacion.ultima_verificacion_en.asc().nulls_first(), Instanciacion.id)
                     .limit(lote)).all()
    revisar_atraso(db, dias)
    if not ids:
        db.commit()
        return None
    for inst_id in ids:
        inst = db.get(Instanciacion, inst_id)
        verificar(db, inst, origen="periodica")
        db.commit()
    fila = db.get(Parametro, CLAVE_ULTIMA_VERIFICACION)
    if fila is None:
        db.add(Parametro(clave=CLAVE_ULTIMA_VERIFICACION, valor=ahora().isoformat()))
    else:
        fila.valor = ahora().isoformat()
    evaluar_riesgos(db)
    db.commit()
    return len(ids)


def revisar_atraso(db: Session, dias: int) -> int:
    """Alerta si hay instanciaciones sin verificar más allá de la frecuencia
    y un margen: señal de que el trabajador no está corriendo. Se resuelve
    sola cuando ya no queda ninguna atrasada."""
    limite = ahora() - timedelta(days=dias) - MARGEN_ATRASO
    atrasadas = db.scalar(select(func.count()).select_from(_verificables(db).where(
        or_(Instanciacion.ultima_verificacion_en < limite,
            and_(Instanciacion.ultima_verificacion_en.is_(None), Instanciacion.cargado_en < limite))).subquery()))
    pendiente = alertas.pendiente(db, "verificacion_atrasada", "verificacion_periodica")
    if atrasadas:
        alertas.crear(db, tipo="verificacion_atrasada", severidad="alta", modulo="preservacion",
                      entidad_tipo="verificacion_periodica", entidad_id="verificacion_periodica",
                      mensaje=f"{atrasadas} archivo(s) llevan más de {dias} días sin verificar su integridad. "
                              "Revise que el trabajador esté en marcha.", detalle={"atrasadas": atrasadas})
    elif pendiente is not None:
        alertas.atender(db, pendiente, None, "Resuelta sola: ya no hay archivos con la verificación atrasada.")
    db.flush()
    return atrasadas


# --- Riesgo de obsolescencia (al panel central de alertas) -----------------------------------------


def riesgo_de(db: Session, inst: Instanciacion) -> dict:
    r = riesgo.evaluar(inst.formato_puid, inst.formato_mime, not inst.formato_no_identificado)
    mitigado_por = None
    if r.nivel != "bajo":
        derivada = db.scalar(select(Instanciacion).where(Instanciacion.derivada_de_id == inst.id)
                             .order_by(Instanciacion.cargado_en.desc()))
        if derivada is not None and riesgo.evaluar(derivada.formato_puid, derivada.formato_mime,
                                                   not derivada.formato_no_identificado).nivel == "bajo":
            mitigado_por = {"id": str(derivada.id), "nombre": derivada.nombre_original}
    return {"nivel": r.nivel, "razon": r.razon, "recomendacion": r.recomendacion, "destino_sugerido": r.destino_sugerido,
            "mitigado_por": mitigado_por}


def evaluar_riesgos(db: Session, fondo_id: uuid.UUID | None = None) -> None:
    """Lleva al panel central de alertas los formatos con riesgo medio o
    alto; cierra solas las que ya no aplican (p. ej. tras una migración a
    un formato de conservación). Lo no identificado ya tiene su alerta
    desde la ingesta: no se duplica."""
    consulta = _verificables(db)
    if fondo_id is not None:
        consulta = consulta.where(Instanciacion.fondo_id == fondo_id)
    for inst in db.scalars(consulta).all():
        r = riesgo_de(db, inst)
        aplica = r["nivel"] in ("medio", "alto") and not r["mitigado_por"] and not inst.formato_no_identificado
        existente = alertas.pendiente(db, "riesgo_obsolescencia", inst.id)
        if aplica and existente is None:
            alertas.crear(db, tipo="riesgo_obsolescencia", severidad="media" if r["nivel"] == "alto" else "baja",
                          modulo="preservacion", entidad_tipo="instanciacion", entidad_id=inst.id,
                          fondo_id=inst.fondo_id,
                          mensaje=f"«{inst.nombre_original}»: riesgo {r['nivel']} de obsolescencia de formato "
                                  f"({inst.formato_nombre or inst.formato_puid}).",
                          detalle={"nivel": r["nivel"], "razon": r["razon"], "recomendacion": r["recomendacion"]})
        elif not aplica and existente is not None:
            nota = (f"Resuelta: se migró a «{r['mitigado_por']['nombre']}»." if r["mitigado_por"]
                    else "Resuelta: el formato ya no tiene riesgo.")
            alertas.atender(db, existente, None, nota)
    db.flush()


# --- Panel y detalle ----------------------------------------------------------------------------


def _contexto(db: Session, inst_id: uuid.UUID) -> list[dict]:
    """Migas hacia el Record Resource asociado (el de la original si esta
    salió de una migración)."""
    recurso_id = db.scalar(select(Relacion.origen_id).where(
        Relacion.destino_id == inst_id, Relacion.codigo_ric == "has_or_had_instantiation", Relacion.estado == "vigente"))
    migas, actual = [], db.get(RecursoDocumental, recurso_id) if recurso_id else None
    while actual is not None:
        migas.append({"id": str(actual.id), "nivel": actual.nivel, "titulo": actual.titulo})
        actual = db.get(RecursoDocumental, actual.incluido_en_id) if actual.incluido_en_id and actual.nivel != "fondo" else None
    return list(reversed(migas))


ORDEN_SEVERIDAD = {"alta": 0, "media": 1, "baja": 2}


def panel(db: Session, fondo_id: uuid.UUID) -> dict:
    evaluar_riesgos(db, fondo_id)
    total = db.scalar(select(func.count()).select_from(_verificables(db).where(Instanciacion.fondo_id == fondo_id).subquery()))
    pendientes = db.scalars(select(Alerta).where(Alerta.fondo_id == fondo_id, Alerta.atendida_en.is_(None),
                                                 Alerta.tipo.in_(TIPOS_ALERTA))).all()
    con_integridad = {a.entidad_id for a in pendientes if a.tipo == "integridad_alterada"}
    con_copia = {a.entidad_id for a in pendientes if a.tipo == "segunda_copia_alterada"}
    con_riesgo = {a.entidad_id for a in pendientes if a.tipo not in TIPOS_INTEGRIDAD}
    atencion = []
    for a in sorted(pendientes, key=lambda a: (ORDEN_SEVERIDAD[a.severidad], a.creada_en)):
        inst = db.get(Instanciacion, uuid.UUID(a.entidad_id))
        if inst is None:
            continue
        atencion.append({"alerta_id": str(a.id), "tipo": a.tipo, "severidad": a.severidad, "mensaje": a.mensaje,
                         "instanciacion": {"id": str(inst.id), "nombre": inst.nombre_original,
                                           "formato": inst.formato_nombre, "puid": inst.formato_puid},
                         "contexto": _contexto(db, inst.derivada_de_id or inst.id)})
    return {
        "resumen": {"total": total, "alerta_integridad": len(con_integridad), "alerta_segunda_copia": len(con_copia),
                    "riesgo_obsolescencia": len(con_riesgo),
                    "buen_estado": max(0, total - len(con_integridad | con_copia | con_riesgo))},
        "atencion": atencion,
        "frecuencia_dias": int(parametros.leer(db, "preservacion_frecuencia_dias")),
        "ultima_verificacion": (db.get(Parametro, CLAVE_ULTIMA_VERIFICACION).valor
                                if db.get(Parametro, CLAVE_ULTIMA_VERIFICACION) else None),
        "sin_segunda_copia": len(sin_segunda_copia(db, fondo_id)),
    }


def instanciacion_o_error(db: Session, inst_id: uuid.UUID) -> Instanciacion:
    inst = db.get(Instanciacion, inst_id)
    if inst is None or inst.estado != "listo_para_descripcion":
        raise ErrorPreservacion("La instanciación no existe o todavía no terminó la ingesta.", 404)
    return inst


def _breve(inst: Instanciacion | None) -> dict | None:
    return {"id": str(inst.id), "nombre": inst.nombre_original, "formato": inst.formato_nombre,
            "puid": inst.formato_puid} if inst else None


def detalle(db: Session, inst: Instanciacion) -> dict:
    from app.models.usuario import Usuario

    nombres = dict(db.execute(select(Usuario.id, Usuario.nombre)).all())
    verificaciones = db.scalars(select(VerificacionIntegridad).where(VerificacionIntegridad.instanciacion_id == inst.id)
                                .order_by(VerificacionIntegridad.fecha.desc()).limit(100)).all()
    migraciones = db.scalars(select(Migracion).where(Migracion.instanciacion_origen_id == inst.id)
                             .order_by(Migracion.aprobada_en.desc())).all()
    origen_migracion = db.scalar(select(Migracion).where(Migracion.instanciacion_resultado_id == inst.id))
    copia = segunda_copia.vigente(db, inst.id)
    restauraciones = db.scalars(select(Restauracion).where(Restauracion.instanciacion_id == inst.id)
                                .order_by(Restauracion.fecha.desc())).all()
    return {
        "id": str(inst.id), "nombre": inst.nombre_original, "fondo_id": str(inst.fondo_id),
        "formato": {"puid": inst.formato_puid, "nombre": inst.formato_nombre, "version": inst.formato_version,
                    "mime": inst.formato_mime, "identificado": not inst.formato_no_identificado,
                    "herramienta": mecanismos.etiqueta(db, inst.mecanismo_identificacion_id,
                                                       inst.herramienta_identificacion),
                    "mecanismo": mecanismos.resumen(db, inst.mecanismo_identificacion_id), "base": inst.formato_base},
        "tamano_bytes": inst.tamano_bytes, "paginas": inst.paginas,
        "huella": inst.huella, "algoritmo_huella": inst.algoritmo_huella,
        "cargado_en": inst.cargado_en, "estado_integridad": inst.estado_integridad,
        "ultima_verificacion_en": inst.ultima_verificacion_en,
        "riesgo": riesgo_de(db, inst),
        "contexto": _contexto(db, inst.derivada_de_id or inst.id),
        "derivada_de": _breve(db.get(Instanciacion, inst.derivada_de_id)) if inst.derivada_de_id else None,
        "migrada_desde": {"herramienta": herramienta_de(db, origen_migracion), "modo": origen_migracion.modo,
                          "mecanismo": mecanismos.resumen(db, origen_migracion.mecanismo_id)}
        if origen_migracion else None,
        "verificaciones": [{"fecha": v.fecha, "resultado": v.resultado, "origen": v.origen,
                            "segunda_copia": v.segunda_copia_resultado,
                            "por": nombres.get(v.usuario_id)} for v in verificaciones],
        "almacenamiento": {"primaria": {"ubicacion": str(almacen.raiz()), "ruta": inst.ruta},
                           "segunda_copia": _copia_out(copia)},
        "restauraciones": [{"fecha": r.fecha, "por": nombres.get(r.usuario_id), "estado_previo": r.estado_previo,
                            "cuarentena": r.ruta_cuarentena} for r in restauraciones],
        "acciones": {"restaurar": inst.estado_integridad in ("alterada", "ausente")
                     and copia is not None and copia.estado == "sincronizada",
                     "reponer_segunda_copia": inst.estado_integridad == "integra"
                     and (copia is None or copia.estado in ("alterada", "ausente"))},
        "derechos": derechos.aplicable(db, inst),
        "aplicacion_creadora": aplicacion_creadora(db, inst),
        "migraciones": [{"id": str(m.id), "destino": m.destino, "destino_nombre": m.destino_nombre, "modo": m.modo,
                         "estado": m.estado, "herramienta": herramienta_de(db, m), "mensaje": m.mensaje,
                         "mecanismo": mecanismos.resumen(db, m.mecanismo_id), "parametros": m.parametros,
                         "aprobada_por": nombres.get(m.aprobada_por_id), "aprobada_en": m.aprobada_en,
                         "terminada_en": m.terminada_en,
                         "resultado": _breve(db.get(Instanciacion, m.instanciacion_resultado_id))
                         if m.instanciacion_resultado_id else None} for m in migraciones],
        "destinos": destinos_para(db, inst),
    }


def _copia_out(copia: SegundaCopia | None) -> dict:
    if copia is None:
        return {"estado": "sin_copia"}
    return {"id": str(copia.id), "estado": copia.estado, "ubicacion": copia.ubicacion, "ruta": copia.ruta,
            "huella": copia.huella, "motivo": copia.motivo, "creada_en": copia.creada_en,
            "ultima_verificacion_en": copia.ultima_verificacion_en}


def herramienta_de(db: Session, m: Migracion) -> str | None:
    """Para mostrar: el mecanismo vigente y lo que hizo. Las filas
    anteriores a la migración 0013 conservan su texto hasta vincularse."""
    nombre = mecanismos.etiqueta(db, m.mecanismo_id)
    if nombre is None:
        return m.herramienta or m.parametros
    return f"{nombre} ({m.parametros})" if m.parametros else nombre


def aplicacion_creadora(db: Session, inst: Instanciacion) -> str | None:
    """PREMIS creatingApplication: se conoce cuando el archivo lo produjo
    una migración del sistema; de lo que llega en la ingesta, no."""
    m = db.scalar(select(Migracion).where(Migracion.instanciacion_resultado_id == inst.id))
    return herramienta_de(db, m) if m else None


# --- Migración ----------------------------------------------------------------------------------


def _nombre_derivado(original: str, destino: Destino) -> str:
    base = Path(original).stem or "archivo"
    return f"{base} ({destino.nombre.split(' (')[0]}){destino.extension}"[:500]


def _crear_derivada(db: Session, original: Instanciacion, archivo: BinaryIO, nombre: str,
                    usuario_id: uuid.UUID, destino: Destino | None) -> Instanciacion:
    """Guarda el archivo resultado como una Instantiation nueva: huella,
    formato PRONOM, enlace RiC-R015 desde la original y RiC-R025 desde los
    mismos Record Resource que ya tenía la original."""
    nueva_id = uuid.uuid4()
    ruta, tamano = almacen.guardar(archivo, original.fondo_id, nueva_id, nombre, parametros.limite_ingesta_bytes(db))
    try:
        absoluta = almacen.ruta_absoluta(ruta)
        f = formato.identificar(absoluta)
        if destino is not None and destino.puids and f.puid not in destino.puids:
            raise ErrorPreservacion(f"El resultado no es {destino.nombre}: Siegfried lo identificó como "
                                    f"{f.nombre or 'formato desconocido'} ({f.puid or 'sin PUID'}).")
        nueva = Instanciacion(
            id=nueva_id, fondo_id=original.fondo_id, nombre_original=nombre, ruta=ruta, tamano_bytes=tamano,
            estado="listo_para_descripcion", paso="terminado", progreso=100, huella=huella_de(absoluta),
            formato_puid=f.puid, formato_nombre=f.nombre, formato_version=f.version, formato_mime=f.mime,
            formato_base=f.base, formato_no_identificado=not f.identificado, herramienta_identificacion=f.herramienta,
            mecanismo_identificacion_id=mecanismos.de_identificacion(db, original.fondo_id, f.herramienta).id,
            texto_extraido=original.texto_extraido, origen_texto=original.origen_texto, paginas=original.paginas,
            derivada_de_id=original.id, cargado_por_id=usuario_id, procesado_en=ahora())
        db.add(nueva)
        db.flush()
    except BaseException:
        almacen.borrar(ruta)  # el resultado no llegó a integrarse al fondo
        raise
    db.add(Relacion(origen_tipo="instanciacion", origen_id=original.id, destino_tipo="instanciacion",
                    destino_id=nueva.id, tipo_relacion="asociacion", codigo_ric="migrated_into",
                    origen="persona", confirmada_por_id=usuario_id))
    for recurso_id in db.scalars(select(Relacion.origen_id).where(
            Relacion.destino_id == original.id, Relacion.codigo_ric == "has_or_had_instantiation",
            Relacion.estado == "vigente")).all():
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=recurso_id, destino_tipo="instanciacion",
                        destino_id=nueva.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                        origen="persona", confirmada_por_id=usuario_id))
    segunda_copia.asegurar(db, nueva, "migracion")  # su propia segunda copia, sin acción manual
    return nueva


def migrar(db: Session, inst: Instanciacion, destino_clave: str, usuario_id: uuid.UUID,
           ip: str | None = None) -> Migracion:
    """Se llama solo desde la acción explícita de aprobación del archivista."""
    destino = DESTINOS.get(destino_clave)
    if destino is None:
        raise ErrorPreservacion("Formato destino desconocido.")
    if _ya_es(inst, destino):
        raise ErrorPreservacion(f"El archivo ya está en {destino.nombre}.")
    if inst.estado_integridad in ("alterada", "ausente"):
        raise ErrorPreservacion("El archivo tiene una alerta de integridad: resuélvala antes de migrarlo.", 409)
    fila = fila_soportada(db, inst, destino.clave)
    m = Migracion(instanciacion_origen_id=inst.id, destino=destino.clave, destino_nombre=destino.nombre,
                  modo="automatica" if fila else "manual", estado="en_curso" if fila else "esperando_archivo",
                  aprobada_por_id=usuario_id)
    db.add(m)
    db.flush()
    registrar(db, modulo="preservacion", accion="migracion_aprobada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip,
              nuevo={"migracion_id": str(m.id), "destino": destino.clave, "modo": m.modo},
              detalle=f"{inst.nombre_original} → {destino.nombre}")
    if fila is None:
        db.flush()
        return m
    conversor = CONVERSORES[fila["conversor"]]
    huella_antes = inst.huella
    with tempfile.TemporaryDirectory(dir=_temporal()) as carpeta:
        entrada = Path(carpeta) / f"entrada{Path(inst.ruta).suffix}"
        salida = Path(carpeta) / f"salida{destino.extension}"
        try:
            almacen.copiar_a(inst.ruta, entrada)  # se convierte una copia: la original no se abre para escribir
            hecho = conversor.ejecutar(entrada, salida)
            # El agente es el mecanismo del vocabulario, con su versión
            # exacta; nunca el nombre del programa como texto en la migración.
            m.mecanismo_id = mecanismos.obtener(db, inst.fondo_id, hecho.programa, hecho.version, usuario_id).id
            m.parametros = hecho.parametros[:200]
            with open(salida, "rb") as archivo:
                nueva = _crear_derivada(db, inst, archivo, _nombre_derivado(inst.nombre_original, destino), usuario_id,
                                        destino)
        except (ErrorPreservacion, formato.IdentificadorNoDisponible, OSError) as exc:
            m.estado, m.mensaje, m.terminada_en = "fallida", str(exc)[:500], ahora()
            registrar(db, modulo="preservacion", accion="migracion_fallida", usuario_id=usuario_id,
                      entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip,
                      nuevo={"migracion_id": str(m.id), "motivo": m.mensaje})
            db.flush()
            return m
    if inst.huella != huella_antes:  # la original no cambia nunca; si pasara, es un fallo del sistema
        raise RuntimeError("La instanciación original cambió durante la migración.")
    m.estado, m.terminada_en, m.instanciacion_resultado_id = "completada", ahora(), nueva.id
    registrar(db, modulo="preservacion", accion="migracion_completada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip,
              nuevo={"migracion_id": str(m.id), "resultado_id": str(nueva.id), "mecanismo_id": str(m.mecanismo_id),
                     "mecanismo": mecanismos.etiqueta(db, m.mecanismo_id), "parametros": m.parametros,
                     "formato": nueva.formato_puid})
    evaluar_riesgos(db, inst.fondo_id)
    return m


def cargar_convertido(db: Session, m: Migracion, archivo: BinaryIO, nombre: str, usuario_id: uuid.UUID,
                      ip: str | None = None) -> Instanciacion:
    """Migración a un formato no soportado: la archivista sube el archivo
    que convirtió por fuera. Se identifica con PRONOM y queda enlazado."""
    if m.estado != "esperando_archivo":
        raise ErrorPreservacion("Esta migración no está esperando un archivo.", 409)
    original = db.get(Instanciacion, m.instanciacion_origen_id)
    destino = DESTINOS[m.destino]
    try:
        nueva = _crear_derivada(db, original, archivo, nombre, usuario_id, destino)
    except almacen.ExcedeLimite as exc:
        raise ErrorPreservacion("El archivo supera el tamaño máximo permitido.", 413) from exc
    m.estado, m.terminada_en, m.instanciacion_resultado_id = "completada", ahora(), nueva.id
    m.parametros = "Conversión externa, cargada por la archivista"  # sin mecanismo: la hizo una persona
    registrar(db, modulo="preservacion", accion="migracion_completada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=original.id, ip=ip,
              nuevo={"migracion_id": str(m.id), "resultado_id": str(nueva.id), "modo": "manual",
                     "formato": nueva.formato_puid, "nombre": nombre})
    evaluar_riesgos(db, original.fondo_id)
    return nueva


# --- Segunda copia: restauración, reposición y copias pendientes ----------------------------------


def restaurar(db: Session, inst: Instanciacion, usuario_id: uuid.UUID, ip: str | None = None) -> Restauracion:
    """Contingencia del plan de preservación: la copia primaria alterada o
    perdida se repone desde la segunda copia íntegra. El archivo dañado no
    se borra, se aparta a la cuarentena. Siempre por aprobación explícita."""
    if inst.estado_integridad not in ("alterada", "ausente"):
        raise ErrorPreservacion("La copia primaria no tiene alerta de integridad: no hay nada que restaurar.", 409)
    copia = segunda_copia.vigente(db, inst.id)
    resultado, _ = segunda_copia.comprobar(copia, inst.huella)
    if resultado != "integra":
        raise ErrorPreservacion("La segunda copia no está íntegra: no se puede restaurar desde ella.", 409)
    primaria = almacen.ruta_absoluta(inst.ruta)
    huella_previa, cuarentena = None, None
    if primaria.exists():
        huella_previa = huella_de(primaria)
        cuarentena = f".cuarentena/{inst.id}-{ahora():%Y%m%dT%H%M%S}{almacen.extension_segura(inst.ruta)}"
        destino_cuarentena = almacen.ruta_absoluta(cuarentena)
        destino_cuarentena.parent.mkdir(parents=True, exist_ok=True)
        primaria.replace(destino_cuarentena)
    primaria.parent.mkdir(parents=True, exist_ok=True)
    temporal = primaria.with_name(primaria.name + ".restaurando")
    shutil.copyfile(segunda_copia.ruta_absoluta(copia), temporal)
    if huella_de(temporal) != inst.huella:
        temporal.unlink(missing_ok=True)
        raise ErrorPreservacion("La copia restaurada no tiene la huella de la ingesta; no se completó.", 500)
    temporal.replace(primaria)
    r = Restauracion(instanciacion_id=inst.id, segunda_copia_id=copia.id, usuario_id=usuario_id,
                     estado_previo=inst.estado_integridad, huella_previa=huella_previa, ruta_cuarentena=cuarentena,
                     mecanismo_id=mecanismos.del_sistema(db, inst.fondo_id).id)
    db.add(r)
    registrar(db, modulo="preservacion", accion="copia_primaria_restaurada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip, detalle=inst.nombre_original,
              anterior={"estado_integridad": inst.estado_integridad, "huella": huella_previa},
              nuevo={"desde_segunda_copia": str(copia.id), "cuarentena": cuarentena})
    db.flush()
    verificar(db, inst, origen="manual", usuario_id=usuario_id, ip=ip)
    existente = alertas.pendiente(db, "integridad_alterada", inst.id)
    if existente is not None and inst.estado_integridad == "integra":
        alertas.atender(db, existente, usuario_id, "Resuelta: copia primaria restaurada desde la segunda copia.")
    db.flush()
    return r


def reponer_segunda_copia(db: Session, inst: Instanciacion, usuario_id: uuid.UUID,
                          ip: str | None = None) -> SegundaCopia | None:
    """La segunda copia alterada o perdida se rehace desde la primaria
    íntegra. La copia dañada no se borra: queda «reemplazada»."""
    try:
        calculada = huella_de(almacen.ruta_absoluta(inst.ruta))
    except (FileNotFoundError, ValueError):
        calculada = None
    if calculada != inst.huella:
        raise ErrorPreservacion("La copia primaria no está íntegra: primero restáurela.", 409)
    if segunda_copia.solo_lectura():
        # La web no escribe en la segunda copia: se aparta la dañada (no se
        # borra) y el trabajador crea la nueva en su próxima vuelta.
        danada = segunda_copia.vigente(db, inst.id)
        if danada is not None:
            danada.estado, danada.reemplazada_en = "reemplazada", ahora()
        registrar(db, modulo="preservacion", accion="segunda_copia_reposicion_encargada", usuario_id=usuario_id,
                  entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip, detalle=inst.nombre_original,
                  nuevo={"reemplazada": str(danada.id) if danada else None})
        db.flush()
        return None
    try:
        copia = segunda_copia.crear(db, inst, "reposicion", usuario_id, ip)
    except (segunda_copia.ErrorSegundaCopia, OSError) as exc:
        raise ErrorPreservacion(f"No se pudo rehacer la segunda copia: {exc}", 503) from exc
    existente = alertas.pendiente(db, "segunda_copia_alterada", inst.id)
    if existente is not None:
        alertas.atender(db, existente, usuario_id, "Resuelta: segunda copia rehecha desde la primaria.")
    db.flush()
    return copia


def sin_segunda_copia(db: Session, fondo_id: uuid.UUID | None = None, limite: int | None = None) -> list[uuid.UUID]:
    """Instanciaciones íntegras sin segunda copia vigente en el lugar
    configurado (fondos anteriores a esta versión, o cambio de lugar)."""
    try:
        ubicacion = str(segunda_copia.ubicacion_actual(db))
    except segunda_copia.ErrorSegundaCopia:
        return []
    con_copia = select(SegundaCopia.instanciacion_id).where(SegundaCopia.estado != "reemplazada",
                                                            SegundaCopia.ubicacion == ubicacion)
    consulta = (_verificables(db).with_only_columns(Instanciacion.id)
                .where(Instanciacion.estado_integridad.in_(("sin_verificar", "integra")),
                       Instanciacion.id.not_in(con_copia)).order_by(Instanciacion.cargado_en))
    if fondo_id is not None:
        consulta = consulta.where(Instanciacion.fondo_id == fondo_id)
    if limite is not None:
        consulta = consulta.limit(limite)
    return list(db.scalars(consulta).all())


def replicar_pendientes(db: Session, limite: int = 20) -> int:
    """La llama el trabajador: crea, de a pocas, las segundas copias que
    falten. Si la primaria ya no tiene su huella, no la replica: la verifica
    (y queda su alerta de integridad)."""
    n = 0
    for inst_id in sin_segunda_copia(db, limite=limite):
        inst = db.get(Instanciacion, inst_id)
        try:
            actual = segunda_copia.vigente(db, inst.id)
            segunda_copia.crear(db, inst, "pendiente" if actual is None else "cambio_de_ubicacion")
            n += 1
        except segunda_copia.ErrorSegundaCopia:
            verificar(db, inst, origen="periodica")
        except OSError as exc:  # el lugar no existe o no se puede escribir: se avisa una vez
            db.rollback()
            alertas.crear(db, tipo="segunda_copia_alterada", severidad="alta", modulo="preservacion",
                          entidad_tipo="parametro", entidad_id="preservacion_segunda_ubicacion",
                          mensaje=f"No se puede escribir en el lugar de la segunda copia: {exc}",
                          detalle={"resultado": "no_creada", "motivo": str(exc)[:300]})
            db.commit()
            return n
        db.commit()
    return n


def _temporal() -> Path:
    carpeta = almacen.raiz() / ".temporal"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def herramientas_disponibles() -> dict:
    return {"ghostscript": shutil.which(settings.ghostscript_binario) is not None}
