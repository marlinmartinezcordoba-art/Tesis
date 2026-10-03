"""
Previsualización de un documento sin descargarlo (cola de ingesta y
descripción). Reutiliza el mismo renderizador de páginas del visor de
descripción (PDF e imágenes a PNG, con tamaño máximo): nunca entrega el
archivo original, y respeta el nivel de acceso del documento.

Quien no tiene sesión de archivista (escritura en ingesta, descripción o el
catálogo) no ve un documento cuyo acceso, propio o heredado, es clasificado
o reservado: recibe error de permisos, como en el catálogo.
"""

import uuid

from sqlalchemy.orm import Session

from app.core.permisos import Actor
from app.models.instanciacion import Instanciacion
from app.servicios import derechos, recorte

ACCESO_RESTRINGIDO = ("clasificado", "reservado")


class ErrorPrevisualizacion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def es_archivista(actor: Actor) -> bool:
    return any(actor.puede(m, "escribir") for m in ("ingesta", "descripcion", "catalogo"))


def documento(db: Session, actor: Actor, instanciacion_id: uuid.UUID) -> Instanciacion:
    inst = db.get(Instanciacion, instanciacion_id)
    if inst is None or inst.estado in ("descartado",):
        raise ErrorPrevisualizacion("El documento no existe.", 404)
    declaracion = derechos.aplicable(db, inst)
    if declaracion and declaracion["acceso"] in ACCESO_RESTRINGIDO and not es_archivista(actor):
        raise ErrorPrevisualizacion(
            f"Documento con acceso {declaracion['acceso_nombre'].lower()}: solo lo ve el equipo de archivo.", 403)
    return inst


def info(db: Session, actor: Actor, instanciacion_id: uuid.UUID) -> dict:
    inst = documento(db, actor, instanciacion_id)
    salida = {"id": str(inst.id), "nombre": inst.nombre_original, "formato": inst.formato_nombre,
              "puid": inst.formato_puid, "admite": False, "total": 0,
              "texto": (inst.texto_extraido or "")[:4000] or None, "origen_texto": inst.origen_texto}
    if recorte.admite_paginas(inst):
        try:
            salida.update(admite=True, total=recorte.total_paginas(inst))
        except (OSError, ValueError):
            pass
    return salida


def pagina(db: Session, actor: Actor, instanciacion_id: uuid.UUID, numero: int) -> bytes:
    inst = documento(db, actor, instanciacion_id)
    try:
        return recorte.pagina_png(inst, numero)
    except recorte.ErrorRecorte as exc:
        raise ErrorPrevisualizacion(str(exc)) from exc
    except OSError as exc:
        raise ErrorPrevisualizacion("No se pudo leer el archivo para mostrarlo.") from exc
