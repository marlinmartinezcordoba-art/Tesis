"""
Procesamiento automático de cada archivo cargado, sin intervención del
archivista: huella digital SHA-256 → búsqueda de duplicado exacto en el
fondo → identificación de formato contra PRONOM → texto (capa de texto u
OCR). Al terminar, el documento pasa a «listo_para_descripcion».

No hay cola ni traspaso: el estado «procesando» es la cola, y el
trabajador (app/trabajador.py) toma de a un documento en ese estado.
"""

import hashlib
import logging
import uuid
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.instanciacion import Instanciacion
from app.servicios import alertas, almacen, comprobaciones, formato, mecanismos, parametros, segunda_copia, texto

log = logging.getLogger("ricora.ingesta")

# Si el trabajador deja de dar señales de vida sobre un documento durante
# este tiempo (se reinició el servidor a mitad de camino), otro intento lo
# vuelve a tomar.
SIN_SENAL = timedelta(minutes=10)

MENSAJE_INESPERADO = "Ocurrió un problema inesperado al procesar el archivo. Puede reintentar."
MENSAJE_SERVIDOR = "El servidor no pudo completar el procesamiento ({}). Avise al administrador y luego reintente."
MENSAJE_SIN_ARCHIVO = "El archivo no se encuentra en el almacenamiento. Descártelo y vuelva a cargarlo."

# Rango de la barra de avance que ocupa cada paso.
TRAMOS = {"huella": (0, 15), "duplicados": (15, 20), "formato": (20, 35), "texto": (35, 99)}


def tomar_siguiente(db: Session) -> uuid.UUID | None:
    """Toma el documento en espera más antiguo. SKIP LOCKED permite más de
    un trabajador sin que dos tomen el mismo documento."""
    limite = ahora() - SIN_SENAL
    fila = db.scalar(
        select(Instanciacion)
        .where(Instanciacion.estado == "procesando",
               or_(Instanciacion.tomado_en.is_(None), Instanciacion.tomado_en < limite))
        .order_by(Instanciacion.cargado_en)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if fila is None:
        db.rollback()
        return None
    fila.tomado_en = ahora()
    fila.intentos += 1
    db.commit()
    return fila.id


def _avance(db: Session, inst: Instanciacion, paso: str, dentro: int = 0, detalle: str | None = None) -> None:
    inicio, fin = TRAMOS[paso]
    inst.paso = paso
    inst.progreso = inicio + (fin - inicio) * max(0, min(dentro, 100)) // 100
    inst.detalle_paso = detalle
    inst.tomado_en = ahora()  # señal de vida
    db.commit()


def _huella(db: Session, inst: Instanciacion) -> None:
    ruta = almacen.ruta_absoluta(inst.ruta)
    total = max(ruta.stat().st_size, 1)
    sha = hashlib.sha256()
    leidos, ultimo = 0, 0
    with open(ruta, "rb") as f:
        while bloque := f.read(almacen.TAMANO_BLOQUE * 4):
            sha.update(bloque)
            leidos += len(bloque)
            porcentaje = 100 * leidos // total
            if porcentaje - ultimo >= 20:
                _avance(db, inst, "huella", porcentaje)
                ultimo = porcentaje
    inst.huella = sha.hexdigest()
    inst.algoritmo_huella = "SHA-256"
    inst.huella_en = ahora()  # hora exacta del evento PREMIS (PRE-02)


def duplicado_de(db: Session, inst: Instanciacion) -> Instanciacion | None:
    """Instanciación ya existente en el mismo fondo con la misma huella.
    No cuentan las que están en error ni las que esperan decisión de
    duplicado: esas todavía no forman parte del fondo."""
    return db.scalar(
        select(Instanciacion)
        .where(Instanciacion.fondo_id == inst.fondo_id,
               Instanciacion.huella == inst.huella,
               Instanciacion.id != inst.id,
               Instanciacion.estado.in_(("procesando", "listo_para_descripcion")),
               Instanciacion.cargado_en <= inst.cargado_en)
        .order_by(Instanciacion.cargado_en)
        .limit(1)
    )


def _error(db: Session, inst: Instanciacion, mensaje: str) -> None:
    inst.estado = "error"
    inst.mensaje_error = mensaje[:500]
    inst.tomado_en = None
    inst.detalle_paso = None
    db.commit()


def _cifra(valor: float | None) -> str:
    return f"{valor:.1f}".replace(".", ",") if valor is not None else "—"


def procesar(db: Session, instanciacion_id: uuid.UUID) -> None:
    inst = db.get(Instanciacion, instanciacion_id)
    if inst is None or inst.estado != "procesando":
        return
    try:
        # 1. Huella digital (si viene de confirmar un duplicado, ya la tiene).
        if inst.huella is None:
            _avance(db, inst, "huella", 0, "Calculando huella digital (SHA-256)")
            _huella(db, inst)

        # 1 bis. Antivirus (NDSA, Integridad, nivel 1; hallazgo PRE-13): un
        # archivo infectado pasa a cuarentena y no sigue el flujo.
        if settings.antivirus and comprobaciones.ultima(db, inst.id, "antivirus") is None:
            analisis = comprobaciones.antivirus(db, inst, "ingesta")
            if analisis.resultado == "infectado":
                comprobaciones.poner_en_cuarentena(db, inst, analisis)
                db.commit()
                return

        # 2. Duplicado exacto: se detiene hasta que el archivista decida.
        _avance(db, inst, "duplicados", 0, "Buscando duplicados en el fondo")
        if not inst.duplicado_confirmado:
            original = duplicado_de(db, inst)
            if original is not None:
                inst.estado = "duplicado_pendiente"
                inst.duplicado_de_id = original.id
                inst.tomado_en = None
                inst.detalle_paso = None
                db.commit()
                return

        # 3. Formato contra PRONOM. No identificarlo no detiene nada.
        _avance(db, inst, "formato", 0, "Identificando formato (PRONOM)")
        f = formato.identificar(almacen.ruta_absoluta(inst.ruta))
        inst.formato_puid, inst.formato_nombre, inst.formato_version = f.puid, f.nombre, f.version
        inst.formato_mime, inst.formato_base = f.mime, f.base
        inst.formato_no_identificado = not f.identificado
        inst.herramienta_identificacion = f.herramienta
        # Quién identificó: el mecanismo del vocabulario (Siegfried con su
        # versión y sus firmas PRONOM), no solo el texto.
        inst.mecanismo_identificacion_id = mecanismos.de_identificacion(db, inst.fondo_id, f.herramienta).id
        inst.formato_en = ahora()
        # 3 bis. Validación formal de lo que dice ser PDF/A o TIFF (veraPDF, JHOVE; hallazgo PRE-09).
        comprobaciones.validar(db, inst, "ingesta")

        # 4. Texto para el motor de descripción.
        _avance(db, inst, "texto", 0, "Extrayendo texto")
        t = texto.extraer(almacen.ruta_absoluta(inst.ruta), f.mime,
                          lambda p, d: _avance(db, inst, "texto", p, d))
        inst.texto_extraido, inst.origen_texto, inst.paginas = t.contenido, t.origen, t.paginas
        inst.confianza_ocr, inst.palabras_ocr = t.confianza_ocr, t.palabras_ocr
        inst.texto_en = ahora()
        programa = mecanismos.de_texto(t.origen)
        if programa:
            inst.mecanismo_texto_id = mecanismos.obtener(db, inst.fondo_id, *programa).id
        umbral = int(parametros.leer(db, "ingesta_umbral_ocr"))
        inst.ocr_baja_confianza = t.confianza_ocr is not None and t.confianza_ocr < umbral

        # Listo: desde aquí lo muestra descripción, por su estado.
        inst.estado = "listo_para_descripcion"
        inst.paso = "terminado"
        inst.progreso = 100
        inst.detalle_paso = None
        inst.mensaje_error = None
        inst.tomado_en = None
        inst.procesado_en = ahora()
        # Segunda copia en el lugar configurado, sin acción manual (si no
        # se puede, queda su alerta y la ingesta termina igual).
        segunda_copia.asegurar(db, inst, "ingesta")
        if inst.formato_no_identificado:
            alertas.crear(
                db, tipo="formato_no_identificado", severidad="media", modulo="ingesta",
                entidad_tipo="instanciacion", entidad_id=inst.id, fondo_id=inst.fondo_id,
                mensaje=f"«{inst.nombre_original}»: el formato no se pudo identificar contra el registro PRONOM. "
                        "Requiere revisión manual de preservación.",
                detalle={"formato_probable": inst.formato_nombre, "base": inst.formato_base},
            )
        if inst.ocr_baja_confianza:
            alertas.crear(
                db, tipo="ocr_baja_confianza", severidad="media", modulo="ingesta",
                entidad_tipo="instanciacion", entidad_id=inst.id, fondo_id=inst.fondo_id,
                mensaje=f"«{inst.nombre_original}»: el texto se leyó por OCR con confianza {_cifra(inst.confianza_ocr)} "
                        f"sobre 100 (umbral {umbral}). Lea la transcripción con cuidado antes de validar la descripción.",
                detalle={"confianza_ocr": inst.confianza_ocr, "umbral": umbral, "palabras": inst.palabras_ocr},
            )
        db.commit()
    except texto.ArchivoIlegible as exc:
        db.rollback()
        _error(db, db.get(Instanciacion, instanciacion_id), str(exc))
    except (formato.IdentificadorNoDisponible, texto.OcrNoDisponible) as exc:
        db.rollback()
        log.error("Herramienta no disponible al procesar %s: %s", instanciacion_id, exc)
        _error(db, db.get(Instanciacion, instanciacion_id), MENSAJE_SERVIDOR.format(exc))
    except FileNotFoundError:
        db.rollback()
        _error(db, db.get(Instanciacion, instanciacion_id), MENSAJE_SIN_ARCHIVO)
    except Exception:
        db.rollback()
        log.exception("Error inesperado al procesar %s", instanciacion_id)
        _error(db, db.get(Instanciacion, instanciacion_id), MENSAJE_INESPERADO)


def procesar_pendientes(db: Session) -> int:
    """Procesa todo lo que esté en espera (lo usa el trabajador y las pruebas)."""
    n = 0
    while (siguiente := tomar_siguiente(db)) is not None:
        procesar(db, siguiente)
        n += 1
    return n


def reiniciar(inst: Instanciacion) -> None:
    """Deja el documento como recién cargado, para reprocesarlo desde el
    principio (reintento tras un error)."""
    inst.estado = "procesando"
    inst.paso = "en_espera"
    inst.progreso = 0
    inst.detalle_paso = None
    inst.tomado_en = None
    inst.mensaje_error = None
    inst.huella = None
    inst.huella_en = inst.formato_en = inst.texto_en = None
    inst.duplicado_de_id = None
    inst.duplicado_confirmado = False
    inst.formato_puid = inst.formato_nombre = inst.formato_version = None
    inst.formato_mime = inst.formato_base = inst.herramienta_identificacion = None
    inst.mecanismo_identificacion_id = None
    inst.formato_no_identificado = False
    inst.texto_extraido = None
    inst.origen_texto = None
    inst.paginas = None
    inst.confianza_ocr = None
    inst.palabras_ocr = None
    inst.ocr_baja_confianza = False
