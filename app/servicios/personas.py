"""
La persona del equipo como agente del vocabulario del fondo (hallazgo PRE-04).

El PREMIS identifica a quien aprobó una migración o cargó un archivo con el
agente de tipo persona del vocabulario del fondo, no con la cuenta de acceso
(que se desactiva o se renombra). El vínculo cuenta ↔ agente es un
identificador interno «usuario:<id>» en la ficha de autoridad, creada una
sola vez. No se busca por nombre (dos personas pueden llamarse igual): si
la persona ya tenía otra ficha en el vocabulario, se unen con la fusión de
Vocabularios, que conserva los identificadores y redirige la URI.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, IdentificadorEntidad
from app.models.usuario import Usuario
from app.core.config import settings
from app.servicios import mecanismos, vocabulario


def _valor(usuario_id: uuid.UUID) -> str:
    return f"usuario:{usuario_id}"


def agente_de_usuario(db: Session, usuario_id: uuid.UUID | None, fondo_id: uuid.UUID) -> EntidadVocabulario | None:
    if usuario_id is None:
        return None
    existente = db.scalar(select(EntidadVocabulario).join(IdentificadorEntidad,
                                                          IdentificadorEntidad.entidad_id == EntidadVocabulario.id)
                          .where(EntidadVocabulario.fondo_id == fondo_id, IdentificadorEntidad.esquema == "interno",
                                 IdentificadorEntidad.valor == _valor(usuario_id),
                                 IdentificadorEntidad.estado == "vigente"))
    if existente is not None:
        return mecanismos._vigente(db, existente)
    u = db.get(Usuario, usuario_id)
    if u is None:
        return None
    from app.servicios import autoridad

    e = vocabulario.crear(db, fondo_id=fondo_id, clase="agente", nombre=u.nombre, subtipo="persona", origen="persona",
                          confianza=None, motor=None, usuario_id=usuario_id)
    e.contexto_general = "Persona del equipo de archivo: agente de las acciones de preservación (PREMIS)."
    autoridad.agregar_identificador(db, e, esquema="interno", valor=_valor(usuario_id), usuario_id=usuario_id)
    db.flush()
    return e


def agente_premis(db: Session, usuario_id: uuid.UUID | None, fondo_id: uuid.UUID) -> dict | None:
    e = agente_de_usuario(db, usuario_id, fondo_id)
    if e is None:
        return None
    return {"tipo_id": f"{settings.nombre_sistema} vocabulario", "id": str(e.id), "nombre": e.nombre,
            "tipo": "person"}
