"""
Copia con OCR estampado de lo que entra escaneado.

Todo documento que llega sin texto (un PDF escaneado o una imagen) recibe, además de su
texto en RICORA, una **copia en PDF con la capa de texto del OCR**: la misma imagen de cada
página y, debajo, el texto invisible que permite buscarlo, seleccionarlo y copiarlo en
cualquier lector de PDF.

El original no se modifica: conserva su huella SHA-256 y su valor de autenticidad. La copia es
otra instanciación, derivada del original (RiC-R014, hasOrHadDerivedInstantiation), con su
propia huella, su formato PRONOM, su segunda copia y el programa que la creó (Tesseract con su
versión) como mecanismo. Si algo falla, la ingesta del original termina igual y queda una alerta.
"""

import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.servicios import alertas, almacen, formato, mecanismos, parametros, segunda_copia

log = logging.getLogger("ricora.copia_ocr")

SUFIJO = " (con OCR).pdf"
CODIGO = "has_or_had_derived_instantiation"


def _nombre(original: str) -> str:
    base = original.rsplit(".", 1)[0] if "." in original else original
    return f"{base}{SUFIJO}"[:255]


def ya_tiene(db: Session, inst: Instanciacion) -> bool:
    return db.scalar(select(Instanciacion.id).where(Instanciacion.derivada_de_id == inst.id,
                                                    Instanciacion.nombre_original == _nombre(inst.nombre_original))) \
        is not None


def _paginas(ruta: Path, tipo: str, destino: Path) -> list[Path]:
    """Cada página como imagen (PNG en escala de grises, a la resolución del OCR de la ingesta)."""
    salida: list[Path] = []
    if tipo == "pdf":
        import pypdfium2 as pdfium

        documento = pdfium.PdfDocument(str(ruta))
        try:
            for i in range(len(documento)):
                imagen = documento[i].render(scale=settings.dpi_ocr / 72, grayscale=True).to_pil()
                archivo = destino / f"p{i:05d}.png"
                imagen.save(archivo)
                imagen.close()
                salida.append(archivo)
        finally:
            documento.close()
    else:
        from PIL import Image, ImageSequence

        with Image.open(ruta) as img:
            for i, cuadro in enumerate(ImageSequence.Iterator(img)):
                archivo = destino / f"p{i:05d}.png"
                cuadro.convert("L").save(archivo)
                salida.append(archivo)
    return salida


def _estampar(paginas: list[Path], base: Path) -> Path:
    """Un solo PDF con todas las páginas y su capa de texto (Tesseract, salida «pdf»)."""
    from app.servicios.texto import ENTORNO_TESSERACT

    lista = base.parent / "paginas.txt"
    lista.write_text("\n".join(str(p) for p in paginas), "utf-8")
    r = subprocess.run(["tesseract", str(lista), str(base), "-l", settings.idioma_ocr, "pdf"],
                       capture_output=True, env=os.environ | ENTORNO_TESSERACT, check=False,
                       timeout=max(120, settings.segundos_por_paso * max(1, len(paginas)) // 2))
    resultado = base.with_suffix(".pdf")
    if r.returncode != 0 or not resultado.exists() or resultado.stat().st_size == 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:] or "Tesseract no generó el PDF.")
    return resultado


def crear(db: Session, inst: Instanciacion) -> Instanciacion | None:
    """La copia con OCR de una instanciación escaneada; None si no aplica (ya trae texto, es una
    copia derivada, ya la tiene o el parámetro está apagado)."""
    if not parametros.leer(db, "ingesta_copia_ocr"):
        return None
    if inst.origen_texto != "ocr" or inst.derivada_de_id is not None or inst.recorte_de_id is not None:
        return None
    tipo = "pdf" if (inst.formato_mime or "").endswith("pdf") or inst.nombre_original.lower().endswith(".pdf") \
        else "imagen" if (inst.formato_mime or "").startswith("image/") else None
    if tipo is None or ya_tiene(db, inst):
        return None
    from app.servicios.preservacion import huella_de

    with tempfile.TemporaryDirectory(prefix="ricora-copia-ocr-") as tmp:
        carpeta = Path(tmp)
        paginas = _paginas(almacen.ruta_absoluta(inst.ruta), tipo, carpeta)
        if not paginas:
            return None
        pdf = _estampar(paginas, carpeta / "copia")
        nueva_id = uuid.uuid4()
        nombre = _nombre(inst.nombre_original)
        with pdf.open("rb") as archivo:
            ruta, tamano = almacen.guardar(archivo, inst.fondo_id, nueva_id, nombre, parametros.limite_ingesta_bytes(db))
    try:
        absoluta = almacen.ruta_absoluta(ruta)
        f = formato.identificar(absoluta)
        programa = mecanismos.de_texto("ocr")
        nueva = Instanciacion(
            id=nueva_id, fondo_id=inst.fondo_id, nombre_original=nombre, ruta=ruta, tamano_bytes=tamano,
            estado="listo_para_descripcion", paso="terminado", progreso=100, huella=huella_de(absoluta),
            formato_puid=f.puid, formato_nombre=f.nombre, formato_version=f.version, formato_mime=f.mime,
            formato_base=f.base, formato_no_identificado=not f.identificado, herramienta_identificacion=f.herramienta,
            mecanismo_identificacion_id=mecanismos.de_identificacion(db, inst.fondo_id, f.herramienta).id,
            texto_extraido=inst.texto_extraido, origen_texto="capa_de_texto", paginas=inst.paginas,
            confianza_ocr=inst.confianza_ocr, palabras_ocr=inst.palabras_ocr,
            mecanismo_creacion_id=mecanismos.obtener(db, inst.fondo_id, *programa).id if programa else None,
            derivada_de_id=inst.id, cargado_por_id=inst.cargado_por_id, procesado_en=ahora())
        db.add(nueva)
        db.flush()
    except BaseException:
        almacen.borrar(ruta)  # la copia no llegó a integrarse al fondo
        raise
    # La copia deriva del original (RiC-R014); la crea la ingesta que pidió quien subió el archivo.
    db.add(Relacion(origen_tipo="instanciacion", origen_id=inst.id, destino_tipo="instanciacion",
                    destino_id=nueva.id, tipo_relacion="identidad", codigo_ric=CODIGO,
                    origen="persona", confirmada_por_id=inst.cargado_por_id))
    db.flush()
    segunda_copia.asegurar(db, nueva, "ingesta")
    return nueva


def crear_sin_detener(db: Session, inst: Instanciacion) -> Instanciacion | None:
    """Como crear(), pero un fallo no detiene la ingesta del original: queda una alerta."""
    try:
        with db.begin_nested():
            return crear(db, inst)
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo crear la copia con OCR de %s: %s", inst.id, exc)
        alertas.crear(db, tipo="copia_ocr_fallida", severidad="baja", modulo="ingesta", entidad_tipo="instanciacion",
                      entidad_id=inst.id, fondo_id=inst.fondo_id,
                      mensaje=f"«{inst.nombre_original}»: no se pudo crear la copia con OCR estampado. El original y "
                              "su texto quedaron bien; puede reintentarlo desde la ficha del documento.",
                      detalle={"error": str(exc)[:300]})
        return None


def una_pendiente(db: Session) -> bool:
    """Lo escaneado que entró antes de esta función también recibe su copia: una por vuelta del
    trabajador, cuando no hay nada nuevo que procesar. Devuelve si hizo una."""
    if not parametros.leer(db, "ingesta_copia_ocr"):
        return False
    copias = select(Instanciacion.derivada_de_id).where(Instanciacion.derivada_de_id.is_not(None),
                                                        Instanciacion.nombre_original.like(f"%{SUFIJO}"))
    from sqlalchemy import String, cast

    from app.models.alerta import Alerta

    fallidas = select(Alerta.entidad_id).where(Alerta.tipo == "copia_ocr_fallida")
    inst = db.scalar(select(Instanciacion).where(
        Instanciacion.origen_texto == "ocr", Instanciacion.estado == "listo_para_descripcion",
        Instanciacion.derivada_de_id.is_(None), Instanciacion.recorte_de_id.is_(None),
        Instanciacion.id.not_in(copias), cast(Instanciacion.id, String).not_in(fallidas)).order_by(Instanciacion.cargado_en).limit(1))
    if inst is None:
        return False
    hecha = crear_sin_detener(db, inst)
    db.commit()
    if hecha is not None:
        log.info("Copia con OCR estampado de «%s» (documento cargado antes).", inst.nombre_original)
    return True
