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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.alerta import Alerta
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.parametro import Parametro
from app.models.preservacion import Migracion, VerificacionIntegridad
from app.models.recurso_documental import RecursoDocumental
from app.servicios import alertas, almacen, formato, parametros, riesgo
from app.servicios.auditoria import registrar

log = logging.getLogger("ricora.preservacion")

TIPOS_ALERTA = ("integridad_alterada", "riesgo_obsolescencia", "formato_no_identificado")


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


def _pdfa_ghostscript(entrada: Path, salida: Path) -> str:
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
    return f"Ghostscript {_version([binario, '--version'])} (pdfwrite, PDF/A-2b, perfil sRGB)"


def _perfil_srgb(binario: str) -> str:
    candidatos = sorted(Path("/usr/share/ghostscript").glob("*/iccprofiles/srgb.icc")) + [
        Path("/usr/share/color/icc/ghostscript/srgb.icc")]
    for c in candidatos:
        if c.exists():
            return str(c)
    raise ErrorPreservacion("No se encontró el perfil de color sRGB de Ghostscript.", 503)


def _tiff_pillow(entrada: Path, salida: Path) -> str:
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
    return f"Pillow {PIL.__version__} (TIFF, compresión LZW sin pérdida)"


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
    ejecutar: Callable[[Path, Path], str]


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
    """Recalcula la huella y la compara con la registrada en la ingesta.
    Alterada o ausente → alerta de severidad alta. No corrige nada sola."""
    try:
        calculada = huella_de(almacen.ruta_absoluta(inst.ruta))
        resultado = "integra" if calculada == inst.huella else "alterada"
    except (FileNotFoundError, ValueError):
        calculada, resultado = None, "ausente"
    v = VerificacionIntegridad(instanciacion_id=inst.id, resultado=resultado, algoritmo=inst.algoritmo_huella,
                               huella_registrada=inst.huella, huella_calculada=calculada, origen=origen,
                               usuario_id=usuario_id)
    db.add(v)
    inst.estado_integridad, inst.ultima_verificacion_en = resultado, ahora()
    if resultado != "integra":
        mensaje = (f"«{inst.nombre_original}»: la huella digital ya no coincide con la registrada en la ingesta "
                   "(el archivo cambió)." if resultado == "alterada" else
                   f"«{inst.nombre_original}»: el archivo no está en el almacenamiento.")
        alertas.crear(db, tipo="integridad_alterada", severidad="alta", modulo="preservacion",
                      entidad_tipo="instanciacion", entidad_id=inst.id, fondo_id=inst.fondo_id, mensaje=mensaje,
                      detalle={"resultado": resultado, "huella_registrada": inst.huella, "huella_calculada": calculada})
    registrar(db, modulo="preservacion", accion="integridad_verificada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip,
              nuevo={"resultado": resultado, "origen": origen}, detalle=inst.nombre_original)
    db.flush()
    return v


def _verificables(db: Session):
    return select(Instanciacion).where(Instanciacion.estado == "listo_para_descripcion", Instanciacion.huella.is_not(None))


CLAVE_ULTIMA_VERIFICACION = "preservacion_ultima_verificacion"


def verificacion_periodica(db: Session) -> int | None:
    """La llama el trabajador en cada vuelta. Si pasó la frecuencia
    configurada desde la última pasada, verifica todo el fondo. Devuelve
    cuántas instanciaciones verificó, o None si no tocaba."""
    dias = int(parametros.leer(db, "preservacion_frecuencia_dias"))
    fila = db.get(Parametro, CLAVE_ULTIMA_VERIFICACION)
    if fila is not None and ahora() - datetime.fromisoformat(fila.valor) < timedelta(days=dias):
        return None
    # Se marca el inicio antes de recorrer: si el trabajador se reinicia a
    # mitad de camino, no vuelve a empezar de inmediato.
    if fila is None:
        db.add(Parametro(clave=CLAVE_ULTIMA_VERIFICACION, valor=ahora().isoformat()))
    else:
        fila.valor = ahora().isoformat()
    db.commit()
    n = 0
    for inst_id in db.scalars(_verificables(db).with_only_columns(Instanciacion.id)).all():
        inst = db.get(Instanciacion, inst_id)
        verificar(db, inst, origen="periodica")
        db.commit()
        n += 1
    evaluar_riesgos(db)
    db.commit()
    return n


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
    con_riesgo = {a.entidad_id for a in pendientes if a.tipo != "integridad_alterada"}
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
        "resumen": {"total": total, "alerta_integridad": len(con_integridad), "riesgo_obsolescencia": len(con_riesgo),
                    "buen_estado": max(0, total - len(con_integridad | con_riesgo))},
        "atencion": atencion,
        "frecuencia_dias": int(parametros.leer(db, "preservacion_frecuencia_dias")),
        "ultima_verificacion": (db.get(Parametro, CLAVE_ULTIMA_VERIFICACION).valor
                                if db.get(Parametro, CLAVE_ULTIMA_VERIFICACION) else None),
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
    return {
        "id": str(inst.id), "nombre": inst.nombre_original, "fondo_id": str(inst.fondo_id),
        "formato": {"puid": inst.formato_puid, "nombre": inst.formato_nombre, "version": inst.formato_version,
                    "mime": inst.formato_mime, "identificado": not inst.formato_no_identificado,
                    "herramienta": inst.herramienta_identificacion, "base": inst.formato_base},
        "tamano_bytes": inst.tamano_bytes, "paginas": inst.paginas,
        "huella": inst.huella, "algoritmo_huella": inst.algoritmo_huella,
        "cargado_en": inst.cargado_en, "estado_integridad": inst.estado_integridad,
        "ultima_verificacion_en": inst.ultima_verificacion_en,
        "riesgo": riesgo_de(db, inst),
        "contexto": _contexto(db, inst.derivada_de_id or inst.id),
        "derivada_de": _breve(db.get(Instanciacion, inst.derivada_de_id)) if inst.derivada_de_id else None,
        "migrada_desde": {"herramienta": origen_migracion.herramienta, "modo": origen_migracion.modo}
        if origen_migracion else None,
        "verificaciones": [{"fecha": v.fecha, "resultado": v.resultado, "origen": v.origen,
                            "por": nombres.get(v.usuario_id)} for v in verificaciones],
        "migraciones": [{"id": str(m.id), "destino": m.destino, "destino_nombre": m.destino_nombre, "modo": m.modo,
                         "estado": m.estado, "herramienta": m.herramienta, "mensaje": m.mensaje,
                         "aprobada_por": nombres.get(m.aprobada_por_id), "aprobada_en": m.aprobada_en,
                         "terminada_en": m.terminada_en,
                         "resultado": _breve(db.get(Instanciacion, m.instanciacion_resultado_id))
                         if m.instanciacion_resultado_id else None} for m in migraciones],
        "destinos": destinos_para(db, inst),
    }


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
            m.herramienta = conversor.ejecutar(entrada, salida)[:200]
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
              nuevo={"migracion_id": str(m.id), "resultado_id": str(nueva.id), "herramienta": m.herramienta,
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
    m.herramienta = "Conversión externa, cargada por la archivista"
    registrar(db, modulo="preservacion", accion="migracion_completada", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=original.id, ip=ip,
              nuevo={"migracion_id": str(m.id), "resultado_id": str(nueva.id), "modo": "manual",
                     "formato": nueva.formato_puid, "nombre": nombre})
    evaluar_riesgos(db, original.fondo_id)
    return nueva


def _temporal() -> Path:
    carpeta = almacen.raiz() / ".temporal"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def herramientas_disponibles() -> dict:
    return {"ghostscript": shutil.which(settings.ghostscript_binario) is not None}
