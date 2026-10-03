"""
Comprobaciones técnicas de preservación (hallazgos PRE-09 y PRE-13).

- Antivirus con ClamAV en la ingesta (NDSA, Integridad, nivel 1): un archivo
  infectado pasa a cuarentena y no sigue el flujo.
- Validación de formato: veraPDF para PDF/A (ISO 19005) y JHOVE para TIFF,
  en la ingesta y después de cada migración. El «riesgo bajo» de un PDF/A o
  un TIFF depende de que la validación sea conforme, no de que el archivo
  declare serlo.

Cada comprobación queda en comprobaciones_tecnicas con el mecanismo que la
hizo y su versión exacta, y sale en el PREMIS como «virus check» o
«validation». Si la herramienta no está instalada, se registra
«no_disponible»: nunca se da por hecha una comprobación que no ocurrió.
"""

import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.instanciacion import Instanciacion
from app.models.preservacion import ComprobacionTecnica
from app.servicios import alertas, almacen, mecanismos
from app.servicios.riesgo import PDFA, TIFF

TIFF_VALIDABLE = TIFF  # JHOVE (TIFF-hul) lee todas las versiones de TIFF que identifica PRONOM


def _ejecutar(argumentos: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argumentos, capture_output=True, timeout=settings.segundos_por_paso, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _guardar(db: Session, inst: Instanciacion, *, tipo: str, herramienta: str, version: str | None, resultado: str,
             perfil: str | None, resumen: str, detalle: dict | None, origen: str) -> ComprobacionTecnica:
    mecanismo = mecanismos.obtener(db, inst.fondo_id, herramienta, version) if version else None
    c = ComprobacionTecnica(instanciacion_id=inst.id, tipo=tipo, herramienta=herramienta,
                            mecanismo_id=mecanismo.id if mecanismo else None, resultado=resultado, perfil=perfil,
                            resumen=resumen[:2000], detalle=detalle, origen=origen, realizada_en=ahora())
    db.add(c)
    db.flush()
    return c


def ultima(db: Session, instanciacion_id, tipo: str) -> ComprobacionTecnica | None:
    return db.scalar(select(ComprobacionTecnica).where(ComprobacionTecnica.instanciacion_id == instanciacion_id,
                                                       ComprobacionTecnica.tipo == tipo)
                     .order_by(ComprobacionTecnica.realizada_en.desc()).limit(1))


# --- Antivirus (ClamAV) -------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _version_clamav() -> str | None:
    r = _ejecutar([settings.clamscan, "--version"])
    return r.stdout.decode().strip()[:120] if r is not None and r.returncode == 0 else None


def antivirus(db: Session, inst: Instanciacion, origen: str = "ingesta") -> ComprobacionTecnica:
    """clamscan sobre el archivo. Código 0: limpio; 1: infectado; otro: error."""
    ruta = almacen.ruta_absoluta(inst.ruta)
    version = _version_clamav()
    if version is None:
        return _guardar(db, inst, tipo="antivirus", herramienta="ClamAV", version=None, resultado="no_disponible",
                        perfil=None, resumen="ClamAV no está instalado en el servidor: el archivo no se analizó.",
                        detalle=None, origen=origen)
    argumentos = [settings.clamscan, "--no-summary", "--stdout"]
    if settings.clamav_firmas:
        argumentos.append(f"--database={settings.clamav_firmas}")
    r = _ejecutar(argumentos + [str(ruta)])
    if r is None or r.returncode not in (0, 1):
        error = (r.stderr.decode("utf-8", "replace").strip() if r is not None else "tiempo agotado")[:300]
        return _guardar(db, inst, tipo="antivirus", herramienta="ClamAV", version=version, resultado="error",
                        perfil=None, resumen=f"El análisis no se pudo completar: {error}", detalle=None, origen=origen)
    if r.returncode == 0:
        return _guardar(db, inst, tipo="antivirus", herramienta="ClamAV", version=version, resultado="limpio",
                        perfil=None, resumen="Sin amenazas detectadas.", detalle=None, origen=origen)
    firma = re.search(r":\s*(.+?)\s+FOUND", r.stdout.decode("utf-8", "replace"))
    return _guardar(db, inst, tipo="antivirus", herramienta="ClamAV", version=version, resultado="infectado",
                    perfil=None, resumen=f"Amenaza detectada: {firma.group(1) if firma else 'firma sin nombre'}.",
                    detalle={"firma": firma.group(1) if firma else None}, origen=origen)


def poner_en_cuarentena(db: Session, inst: Instanciacion, comprobacion: ComprobacionTecnica) -> None:
    """Saca el archivo del almacenamiento normal (no se borra: se aparta) y
    detiene su flujo, con una alerta de severidad alta."""
    origen = almacen.ruta_absoluta(inst.ruta)
    relativa = Path("cuarentena") / str(inst.fondo_id) / f"{inst.id}{origen.suffix}"
    destino = almacen.raiz() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(origen), str(destino))
    inst.ruta = relativa.as_posix()
    inst.estado, inst.paso, inst.tomado_en = "error", "terminado", None
    inst.mensaje_error = (f"{comprobacion.resumen} El archivo quedó en cuarentena y no sigue el flujo. Avise al "
                          "administrador antes de descartarlo o restaurarlo.")
    alertas.crear(db, tipo="archivo_infectado", severidad="alta", modulo="ingesta", entidad_tipo="instanciacion",
                  entidad_id=inst.id, fondo_id=inst.fondo_id,
                  mensaje=f"«{inst.nombre_original}»: {comprobacion.resumen} Quedó en cuarentena.",
                  detalle={"firma": (comprobacion.detalle or {}).get("firma"), "cuarentena": inst.ruta})


# --- Validación de formato (veraPDF, JHOVE) --------------------------------------------------------


def _lib() -> Path:
    return Path(settings.directorio_validadores) / "lib"


def _verapdf(ruta: Path) -> tuple[str, str | None, str, str, dict]:
    """(resultado, versión, perfil, resumen, detalle)"""
    if not _lib().is_dir():
        return "no_disponible", None, "PDF/A", "veraPDF no está instalado en el servidor.", {}
    r = _ejecutar([settings.java, "-cp", f"{_lib()}/*", "org.verapdf.apps.GreenfieldCliWrapper", "--format", "json",
                   str(ruta)])
    if r is None or not r.stdout:
        return "error", None, "PDF/A", "veraPDF no respondió.", {}
    try:
        informe = json.loads(r.stdout.decode("utf-8", "replace"))["report"]
    except (ValueError, KeyError):
        return "error", None, "PDF/A", "La respuesta de veraPDF no se pudo leer.", {}
    version = next((d["version"] for d in informe["buildInformation"]["releaseDetails"] if d["id"] == "core"), None)
    trabajo = informe["jobs"][0]
    validacion = (trabajo.get("validationResult") or [None])[0]
    if not validacion:
        return "error", version, "PDF/A", "veraPDF no pudo validar el archivo.", {"trabajo": trabajo.get("taskResult")}
    perfil = validacion.get("profileName", "PDF/A").replace(" validation profile", "")
    detalles = validacion.get("details", {})
    reglas = [{"especificacion": x.get("specification"), "clausula": x.get("clause"), "prueba": x.get("testNumber"),
               "descripcion": (x.get("description") or "")[:300]}
              for x in detalles.get("ruleSummaries", []) if x.get("ruleStatus") == "FAILED"][:20]
    if validacion.get("compliant"):
        return "conforme", version, perfil, f"Conforme con {perfil} ({detalles.get('passedRules')} reglas).", {}
    return ("no_conforme", version, perfil,
            f"No conforme con {perfil}: {detalles.get('failedRules')} regla(s) incumplidas"
            + (f", p. ej. cláusula {reglas[0]['clausula']} de {reglas[0]['especificacion']}." if reglas else "."),
            {"reglas_incumplidas": reglas})


def _jhove(ruta: Path) -> tuple[str, str | None, str, str, dict]:
    configuracion = Path(settings.directorio_validadores) / "jhove.conf"
    if not _lib().is_dir() or not configuracion.exists():
        return "no_disponible", None, "TIFF-hul", "JHOVE no está instalado en el servidor.", {}
    r = _ejecutar([settings.java, "-cp", f"{_lib()}/*", "edu.harvard.hul.ois.jhove.Jhove", "-c", str(configuracion),
                   "-m", "TIFF-hul", "-h", "json", str(ruta)])
    if r is None or not r.stdout:
        return "error", None, "TIFF-hul", "JHOVE no respondió.", {}
    try:
        informe = json.loads(r.stdout.decode("utf-8", "replace"))["jhove"]
        rep = informe["repInfo"][0]
    except (ValueError, KeyError, IndexError):
        return "error", None, "TIFF-hul", "La respuesta de JHOVE no se pudo leer.", {}
    modulo = rep.get("reportingModule", {})
    version = f"{informe.get('release')} (TIFF-hul {modulo.get('release')})"
    estado = rep.get("status", "")
    mensajes = [m.get("message") for m in rep.get("messages", []) if m.get("message")][:10]
    if estado == "Well-Formed and valid":
        return "conforme", version, "TIFF-hul", "TIFF bien formado y válido.", {}
    return "no_conforme", version, "TIFF-hul", f"TIFF {estado.lower() or 'no válido'}.", {"mensajes": mensajes}


def validar(db: Session, inst: Instanciacion, origen: str = "ingesta") -> ComprobacionTecnica | None:
    """Valida un PDF/A o un TIFF; los demás formatos no tienen validador en el sistema."""
    if inst.formato_puid in PDFA:
        resultado, version, perfil, resumen, detalle = _verapdf(almacen.ruta_absoluta(inst.ruta))
        herramienta = "veraPDF"
    elif inst.formato_puid in TIFF_VALIDABLE:
        resultado, version, perfil, resumen, detalle = _jhove(almacen.ruta_absoluta(inst.ruta))
        herramienta = "JHOVE"
    else:
        return None
    c = _guardar(db, inst, tipo="validacion", herramienta=herramienta, version=version, resultado=resultado,
                 perfil=perfil, resumen=resumen, detalle=detalle or None, origen=origen)
    if resultado == "no_conforme":
        alertas.crear(db, tipo="validacion_formato_fallida", severidad="media", modulo="preservacion",
                      entidad_tipo="instanciacion", entidad_id=inst.id, fondo_id=inst.fondo_id,
                      mensaje=f"«{inst.nombre_original}»: {resumen} No se considera de riesgo bajo hasta que valide.",
                      detalle=detalle or None)
    return c
