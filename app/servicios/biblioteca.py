"""
Biblioteca de referencia del Asistente RICORA (RAG).

La administración carga aquí las leyes, decretos, acuerdos del AGN, manuales y procedimientos con
los que el asistente debe responder. Cada archivo se guarda con su huella SHA-256 y se le extrae el
texto con el mismo lector de la ingesta (capa de texto del PDF, o la imagen limpia y el OCR si viene
escaneado). El texto queda en el índice en español del buscador; el asistente recupera de ahí los
pasajes que tratan la pregunta.

El texto se extrae en segundo plano (el trabajador toma uno por vuelta): una ley escaneada de cien
páginas no detiene la pantalla. Nada se borra: un documento que ya no aplica se anula y deja de
consultarse.
"""

import hashlib
import logging
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.referencia import CLASES, DocumentoReferencia
from app.servicios import almacen
from app.servicios.auditoria import registrar

log = logging.getLogger("ricora.biblioteca")

LIMITE_BYTES = 200 * 1024 * 1024
EXTENSIONES = (".pdf", ".docx", ".doc", ".odt", ".txt", ".md", ".html", ".htm", ".rtf", ".png", ".jpg", ".jpeg",
               ".tif", ".tiff")
CLASE_NOMBRE = {"ley": "Ley", "decreto": "Decreto", "acuerdo_agn": "Acuerdo del AGN", "manual": "Manual",
                "procedimiento": "Procedimiento", "otro": "Otro documento de referencia"}


class ErrorBiblioteca(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo


def _guardar(origen: BinaryIO, doc_id: uuid.UUID, nombre: str) -> tuple[str, int, str]:
    relativa = f"referencia/{doc_id}{almacen.extension_segura(nombre)}"
    destino = almacen.ruta_absoluta(relativa)
    destino.parent.mkdir(parents=True, exist_ok=True)
    escritos, huella = 0, hashlib.sha256()
    try:
        with open(destino, "xb") as salida:
            while bloque := origen.read(almacen.TAMANO_BLOQUE):
                escritos += len(bloque)
                if escritos > LIMITE_BYTES:
                    raise ErrorBiblioteca(f"El archivo pasa de {LIMITE_BYTES // (1024 * 1024)} MB.", 413)
                huella.update(bloque)
                salida.write(bloque)
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    if escritos == 0:
        destino.unlink(missing_ok=True)
        raise ErrorBiblioteca("El archivo está vacío.")
    return relativa, escritos, huella.hexdigest()


def cargar(db: Session, archivo: BinaryIO, nombre: str, titulo: str | None, clase: str, usuario_id: uuid.UUID,
           mime: str | None = None) -> DocumentoReferencia:
    if clase not in CLASES:
        raise ErrorBiblioteca("Clase no válida.", 422)
    if not nombre.lower().endswith(EXTENSIONES):
        raise ErrorBiblioteca("Formatos que se leen: PDF, Word, texto o imagen escaneada.", 422)
    doc_id = uuid.uuid4()
    ruta, tamano, huella = _guardar(archivo, doc_id, nombre)
    repetido = db.scalar(select(DocumentoReferencia).where(DocumentoReferencia.huella == huella,
                                                           DocumentoReferencia.estado != "anulado"))
    if repetido is not None:
        almacen.borrar(ruta)
        raise ErrorBiblioteca(f"Ese archivo ya está en la biblioteca: «{repetido.titulo}».", 409)
    titulo = (titulo or "").strip() or Path(nombre).stem.replace("_", " ").strip()
    doc = DocumentoReferencia(id=doc_id, titulo=titulo[:300], clase=clase, nombre_original=nombre[:255], ruta=ruta,
                              huella=huella, tamano_bytes=tamano, formato_mime=mime, estado="procesando",
                              cargado_por_id=usuario_id)
    db.add(doc)
    db.flush()
    registrar(db, modulo="sistema", accion="referencia_cargada", usuario_id=usuario_id, entidad_tipo="documento_referencia",
              entidad_id=doc.id, detalle=f"Cargó «{doc.titulo}» a la biblioteca del asistente",
              nuevo={"clase": clase, "archivo": doc.nombre_original, "huella": huella})
    return doc


def procesar(db: Session, doc: DocumentoReferencia) -> None:
    """Extrae el texto (con OCR y la imagen limpia si viene escaneado)."""
    from app.servicios import texto

    try:
        leido = texto.extraer(almacen.ruta_absoluta(doc.ruta), doc.formato_mime, lambda *_: None)
        if not (leido.contenido or "").strip():
            raise texto.ArchivoIlegible("No se encontró texto en el archivo.")
        doc.texto, doc.origen_texto, doc.paginas = leido.contenido, leido.origen, leido.paginas
        doc.estado, doc.error = "listo", None
    except Exception as exc:  # noqa: BLE001 — el motivo queda en el documento
        log.warning("No se pudo leer la referencia %s: %s", doc.id, exc)
        doc.estado, doc.error = "error", str(exc)[:500] or "No se pudo leer el archivo."
    doc.procesado_en = ahora()


def una_pendiente(db: Session) -> bool:
    """Para el trabajador: procesa un documento pendiente. Devuelve si hizo uno."""
    doc = db.scalar(select(DocumentoReferencia).where(DocumentoReferencia.estado == "procesando")
                    .order_by(DocumentoReferencia.cargado_en).limit(1).with_for_update(skip_locked=True))
    if doc is None:
        return False
    procesar(db, doc)
    db.commit()
    return True


def anular(db: Session, doc: DocumentoReferencia, motivo: str | None, usuario_id: uuid.UUID) -> DocumentoReferencia:
    if doc.estado == "anulado":
        raise ErrorBiblioteca("Ya está anulado.", 409)
    doc.estado, doc.anulado_por_id, doc.anulado_en = "anulado", usuario_id, ahora()
    doc.motivo_anulacion = (motivo or "").strip()[:500] or None
    registrar(db, modulo="sistema", accion="referencia_anulada", usuario_id=usuario_id, entidad_tipo="documento_referencia",
              entidad_id=doc.id, detalle=f"Anuló «{doc.titulo}» de la biblioteca del asistente",
              nuevo={"motivo": doc.motivo_anulacion})
    return doc


def out(doc: DocumentoReferencia) -> dict:
    return {"id": str(doc.id), "titulo": doc.titulo, "clase": doc.clase, "clase_nombre": CLASE_NOMBRE[doc.clase],
            "archivo": doc.nombre_original, "huella": doc.huella, "tamano_bytes": doc.tamano_bytes, "estado": doc.estado,
            "error": doc.error, "paginas": doc.paginas, "origen_texto": doc.origen_texto,
            "caracteres": len(doc.texto or ""), "cargado_en": doc.cargado_en, "motivo_anulacion": doc.motivo_anulacion}


def listar(db: Session, con_anulados: bool = False) -> list[dict]:
    consulta = select(DocumentoReferencia).order_by(DocumentoReferencia.cargado_en.desc())
    if not con_anulados:
        consulta = consulta.where(DocumentoReferencia.estado != "anulado")
    return [out(d) for d in db.scalars(consulta)]
