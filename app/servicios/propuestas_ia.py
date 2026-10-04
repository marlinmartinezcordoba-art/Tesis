"""
La propuesta del motor como registro propio (brecha RF-AI-002).

Cada vez que el motor propone, al describir o en la evaluación ciega, queda
una fila en propuestas_ia con todo lo necesario para reconstruir y evaluar
lo que pasó: el modelo pedido y la versión que respondió, la versión de la
instrucción, los parámetros, lo que se le envió (con la huella de cada
texto), la respuesta tal como llegó, la propuesta ya controlada (con la
página y la zona de cada fragmento), la hora y la duración.

El contenido no cambia nunca y la fila no se borra (disparador de la
migración 0036). Lo único que cambia es su estado: generada → publicada,
cancelada o expirada. La huella SHA-256 de entrada + respuesta + contenido
permite comprobar después que nadie la alteró por fuera de la aplicación.
"""

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.evidencia_ia import PropuestaIA
from app.servicios import evidencia

# Estado de la propuesta según cómo terminó el trabajo de descripción.
ESTADO_POR_TRABAJO = {"publicado": "publicada", "cancelado": "cancelada", "expirado": "expirada"}
ESTADO_NOMBRE = {"generada": "Generada, sin decidir", "publicada": "Publicada (decidida por una persona)",
                 "cancelada": "Descartada al cancelar", "expirada": "Sin decidir: la edición venció",
                 "evaluada": "Usada en la evaluación ciega"}


def huella_de(entrada, respuesta, contenido) -> str:
    canonico = json.dumps({"entrada": entrada, "respuesta": respuesta, "contenido": contenido},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def ubicar_fragmentos(db: Session, propuesta) -> None:
    """Agrega a cada entidad propuesta la página y la zona de su fragmento
    (RF-OCR-001). Queda en el contenido de la propuesta: la evidencia es la
    del texto que vio el motor."""
    for e in propuesta.entidades:
        if e.fragmento and e.documento_id:
            zona = evidencia.ubicar(db, e.documento_id, e.inicio, e.fragmento)
            if zona:
                e.pagina, e.zona = zona["pagina"], zona


def registrar(db: Session, propuesta, *, origen: str, fondo_id: uuid.UUID, nivel: str, instanciaciones: list[uuid.UUID],
              solicitada_por_id: uuid.UUID | None, trabajo_id: uuid.UUID | None = None,
              evaluacion_id: uuid.UUID | None = None, estado: str = "generada") -> PropuestaIA | None:
    """Guarda la propuesta. Si no hay motor configurado no hubo propuesta:
    no se registra nada."""
    if not propuesta.motor:
        return None
    contenido = propuesta.a_dict()
    confianzas = [e.confianza for e in propuesta.entidades if e.confianza is not None]
    fila = PropuestaIA(
        id=uuid.uuid4(), origen=origen, fondo_id=fondo_id, trabajo_id=trabajo_id, evaluacion_id=evaluacion_id,
        solicitada_por_id=solicitada_por_id, nivel=nivel, instanciaciones=list(instanciaciones),
        motor=propuesta.motor, version_modelo=propuesta.version_modelo, version_prompt=propuesta.version_prompt,
        parametros=propuesta.parametros or {}, entrada=propuesta.entrada or {}, respuesta=propuesta.respuesta,
        contenido=contenido, huella=huella_de(propuesta.entrada or {}, propuesta.respuesta, contenido),
        disponible=propuesta.disponible, aviso=propuesta.aviso, entidades=len(propuesta.entidades),
        confianza_media=round(sum(confianzas) / len(confianzas), 3) if confianzas else None,
        generada_en=ahora(), duracion_ms=propuesta.duracion_ms, estado=estado,
        estado_en=ahora() if estado != "generada" else None)
    db.add(fila)
    db.flush()
    return fila


def cerrar(db: Session, propuesta_id: uuid.UUID | None, estado_trabajo: str, recurso_id: uuid.UUID | None = None) -> None:
    """La propuesta sigue al trabajo: publicada, cancelada o expirada. Se
    conserva en cualquier caso."""
    if not propuesta_id:
        return
    p = db.get(PropuestaIA, propuesta_id)
    estado = ESTADO_POR_TRABAJO.get(estado_trabajo)
    if p is None or estado is None or p.estado != "generada":
        return
    p.estado, p.estado_en = estado, ahora()
    if recurso_id:
        p.recurso_id = recurso_id


def integra(p: PropuestaIA) -> bool:
    return huella_de(p.entrada, p.respuesta, p.contenido) == p.huella


def out(p: PropuestaIA, completa: bool = False) -> dict:
    datos = {
        "id": str(p.id), "origen": p.origen, "nivel": p.nivel, "motor": p.motor, "version_modelo": p.version_modelo,
        "version_prompt": p.version_prompt, "generada_en": p.generada_en.isoformat(), "duracion_ms": p.duracion_ms,
        "estado": p.estado, "estado_nombre": ESTADO_NOMBRE.get(p.estado, p.estado),
        "estado_en": p.estado_en.isoformat() if p.estado_en else None, "disponible": p.disponible, "aviso": p.aviso,
        "entidades": p.entidades, "confianza_media": p.confianza_media, "huella": p.huella, "integra": integra(p),
        "trabajo_id": str(p.trabajo_id) if p.trabajo_id else None,
        "evaluacion_id": str(p.evaluacion_id) if p.evaluacion_id else None,
        "recurso_id": str(p.recurso_id) if p.recurso_id else None,
        "instanciaciones": [str(i) for i in p.instanciaciones], "parametros": p.parametros,
    }
    if completa:
        datos |= {"entrada": p.entrada, "respuesta": p.respuesta, "contenido": p.contenido}
    return datos


def de_recurso(db: Session, recurso_id: uuid.UUID) -> list[PropuestaIA]:
    return db.scalars(select(PropuestaIA).where(PropuestaIA.recurso_id == recurso_id)
                      .order_by(PropuestaIA.generada_en.desc())).all()
