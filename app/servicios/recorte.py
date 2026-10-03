"""
Páginas y recortes de un documento, para describir sus partes.

- pagina(): la imagen de una página (PDF, imagen de varias páginas o imagen
  simple), para mostrarla en el espacio de trabajo de descripción.
- recortar(): una zona de una página (la firma, el sello, un anexo) se
  guarda como una instanciación propia de la parte documental, con su
  huella SHA-256, su formato identificado contra PRONOM y su segunda copia,
  exactamente como cualquier archivo ingestado. El original no se toca.

El recorte se guarda en PNG: sin pérdida, abierto y en la tabla de formatos
aceptados para preservación de imágenes junto con TIFF.
"""

import hashlib
import io
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.servicios import almacen, formato, mecanismos
from app.servicios.auditoria import registrar

DPI_PAGINA = 110  # suficiente para ver y recortar en pantalla
DPI_RECORTE = 300  # el recorte se toma a resolución de preservación
MAXIMO_LADO = 2200


class ErrorRecorte(Exception):
    pass


def _es_pdf(inst: Instanciacion) -> bool:
    return (inst.formato_mime or "") == "application/pdf" or inst.ruta.lower().endswith(".pdf")


def _es_imagen(inst: Instanciacion) -> bool:
    return (inst.formato_mime or "").startswith("image/") or Path(inst.ruta).suffix.lower() in (
        ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")


def admite_paginas(inst: Instanciacion) -> bool:
    return _es_pdf(inst) or _es_imagen(inst)


def total_paginas(inst: Instanciacion) -> int:
    if inst.paginas:
        return inst.paginas
    if _es_imagen(inst):
        from PIL import Image

        with Image.open(almacen.ruta_absoluta(inst.ruta)) as img:
            return getattr(img, "n_frames", 1)
    return 1


def _imagen(inst: Instanciacion, pagina: int, dpi: int):
    """Imagen PIL de la página (1 en adelante)."""
    if not admite_paginas(inst):
        raise ErrorRecorte("Este formato no se puede mostrar como página (solo PDF e imágenes).")
    total = total_paginas(inst)
    if not 1 <= pagina <= total:
        raise ErrorRecorte(f"El documento tiene {total} página(s).")
    ruta = almacen.ruta_absoluta(inst.ruta)
    if _es_pdf(inst):
        import pypdfium2 as pdfium

        documento = pdfium.PdfDocument(str(ruta))
        try:
            return documento[pagina - 1].render(scale=dpi / 72).to_pil().convert("RGB")
        finally:
            documento.close()
    from PIL import Image

    img = Image.open(ruta)
    if getattr(img, "n_frames", 1) > 1:
        img.seek(pagina - 1)
    return img.convert("RGB")


def pagina_png(inst: Instanciacion, pagina: int) -> bytes:
    img = _imagen(inst, pagina, DPI_PAGINA)
    img.thumbnail((MAXIMO_LADO, MAXIMO_LADO))
    salida = io.BytesIO()
    img.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


def _zona(zona: dict) -> tuple[int, float, float, float, float]:
    try:
        pagina = int(zona.get("pagina", 1))
        x, y, ancho, alto = (float(zona[k]) for k in ("x", "y", "ancho", "alto"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ErrorRecorte("La zona del recorte está incompleta.") from exc
    if not (0 <= x < 1 and 0 <= y < 1 and 0.01 <= ancho <= 1 and 0.01 <= alto <= 1 and x + ancho <= 1.0001
            and y + alto <= 1.0001):
        raise ErrorRecorte("La zona del recorte debe quedar dentro de la página.")
    return pagina, x, y, min(ancho, 1 - x), min(alto, 1 - y)


def recortar(db: Session, origen: Instanciacion, zona: dict, nombre: str, usuario_id: uuid.UUID) -> Instanciacion:
    """Crea la instanciación del recorte. No hace commit: va dentro de la
    transacción de la publicación. Si esa transacción falla, quien llama
    borra el archivo con borrar_archivo()."""
    pagina, x, y, ancho, alto = _zona(zona)
    img = _imagen(origen, pagina, DPI_RECORTE)
    w, h = img.size
    caja = (round(x * w), round(y * h), round((x + ancho) * w), round((y + alto) * h))
    recorte = img.crop(caja)
    datos = io.BytesIO()
    recorte.save(datos, format="PNG", dpi=(DPI_RECORTE, DPI_RECORTE))
    contenido = datos.getvalue()
    inst_id = uuid.uuid4()
    limpio = "".join(c if c.isalnum() or c in "-_" else "_" for c in nombre)[:60] or "parte"
    nombre_archivo = f"{Path(origen.nombre_original).stem}_{limpio}.png"
    relativa, tamano = almacen.guardar(io.BytesIO(contenido), origen.fondo_id, inst_id, nombre_archivo,
                                       limite_bytes=len(contenido) + 1)
    try:
        f = formato.identificar(almacen.ruta_absoluta(relativa))
    except formato.IdentificadorNoDisponible:
        f = None
    inst = Instanciacion(
        id=inst_id, fondo_id=origen.fondo_id, nombre_original=nombre_archivo, ruta=relativa, tamano_bytes=tamano,
        tipo_declarado="image/png", estado="listo_para_descripcion", paso="terminado", progreso=100,
        huella=hashlib.sha256(contenido).hexdigest(), algoritmo_huella="SHA-256",
        formato_puid=f.puid if f else None, formato_nombre=f.nombre if f else None,
        formato_version=f.version if f else None, formato_mime=f.mime if f else "image/png",
        formato_base=f.base if f else None, formato_no_identificado=not (f and f.identificado),
        herramienta_identificacion=f.herramienta if f else None,
        mecanismo_identificacion_id=mecanismos.de_identificacion(db, origen.fondo_id, f.herramienta).id if f else None,
        origen_texto="sin_texto", paginas=1, cargado_por_id=usuario_id, procesado_en=ahora(),
        recorte_de_id=origen.id, recorte_zona={"pagina": pagina, "x": x, "y": y, "ancho": ancho, "alto": alto},
    )
    db.add(inst)
    db.flush()
    # El recorte es una instanciación derivada de su archivo de origen (RiC-R014, hallazgo CM-04).
    db.add(Relacion(origen_tipo="instanciacion", origen_id=origen.id, destino_tipo="instanciacion",
                    destino_id=inst.id, tipo_relacion="identidad", codigo_ric="has_or_had_derived_instantiation",
                    origen="persona", confirmada_por_id=usuario_id))
    db.flush()
    registrar(db, modulo="descripcion", accion="recorte_creado", usuario_id=usuario_id, entidad_tipo="instanciacion",
              entidad_id=inst.id, detalle=f"Recorte de «{origen.nombre_original}», página {pagina}",
              nuevo={"recorte_de": str(origen.id), "zona": inst.recorte_zona, "huella": inst.huella,
                     "formato": inst.formato_puid})
    return inst


def borrar_archivo(inst: Instanciacion) -> None:
    """Solo si la publicación que creó el recorte no llegó a confirmarse."""
    almacen.borrar(inst.ruta)
