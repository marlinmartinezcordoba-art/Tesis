"""
Asistente RICORA con IA (app/servicios/asistente.py): responde con los documentos de la entidad (RAG)
o con internet. Cualquier persona con sesión puede usarlo; no cambia nada. La biblioteca de
referencia (leyes, acuerdos, manuales) la carga y la anula la administración.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permisos import Actor, solo_administrador, usuario_actual
from app.db.session import get_db
from app.schemas.respuestas_sistema import DocumentoReferenciaOut, EstadoAsistenteOut, RespuestaAsistenteOut
from app.models.referencia import DocumentoReferencia
from app.servicios import asistente, biblioteca
from app.servicios.motor import MotorError

router = APIRouter(prefix="/api/asistente", tags=["Asistente RICORA"])


class MensajeIn(BaseModel):
    rol: Literal["persona", "asistente"]
    texto: str = Field(min_length=1, max_length=4000)


class PantallaIn(BaseModel):
    titulo: str | None = Field(default=None, max_length=200)
    pasos: list[str] = Field(default_factory=list, max_length=12)


class PreguntaIn(BaseModel):
    mensajes: list[MensajeIn] = Field(min_length=1, max_length=30)
    pantalla: PantallaIn | None = None
    fondo: str | None = Field(default=None, max_length=400)
    fondo_id: uuid.UUID | None = None
    # documentos: responde solo con la biblioteca y el fondo (RAG); internet: con Google Search.
    fuentes: Literal["documentos", "internet"] = "documentos"


@router.get("/estado", responses={200: {"model": EstadoAsistenteOut, "description": "Disponibilidad"}},
            summary="Si el asistente con IA está disponible")
def estado(actor: Actor = Depends(usuario_actual)):
    return asistente.estado()


@router.post("/preguntar", responses={200: {"model": RespuestaAsistenteOut, "description": "Respuesta"}},
             summary="Pregunta al Asistente RICORA (orienta; no lee documentos ni cambia nada)")
def preguntar(datos: PreguntaIn, actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    try:
        return asistente.preguntar(db, actor.id, [m.model_dump() for m in datos.mensajes],
                                   datos.pantalla.model_dump() if datos.pantalla else None, datos.fondo,
                                   fuentes=datos.fuentes, fondo_id=datos.fondo_id)
    except asistente.AsistenteNoDisponible as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except MotorError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# --- Biblioteca de referencia (RAG) -----------------------------------------------------------------


class AnularIn(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


@router.get("/biblioteca", responses={200: {"model": list[DocumentoReferenciaOut], "description": "La biblioteca"}},
            summary="Leyes, acuerdos y manuales con los que responde el asistente")
def biblioteca_listar(actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    return biblioteca.listar(db)


@router.post("/biblioteca", status_code=status.HTTP_201_CREATED,
             responses={201: {"model": DocumentoReferenciaOut, "description": "Cargado; el texto se extrae en segundo plano"}},
             summary="Cargar una ley, acuerdo, manual o procedimiento a la biblioteca del asistente")
def biblioteca_cargar(archivo: UploadFile = File(...), titulo: str | None = Form(default=None, max_length=300),
                      clase: str = Form(default="otro"), actor: Actor = Depends(solo_administrador),
                      db: Session = Depends(get_db)):
    try:
        doc = biblioteca.cargar(db, archivo.file, archivo.filename or "documento", titulo, clase, actor.id,
                                archivo.content_type)
    except biblioteca.ErrorBiblioteca as exc:
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    db.commit()
    return biblioteca.out(doc)


@router.post("/biblioteca/{doc_id}/anular",
             responses={200: {"model": DocumentoReferenciaOut, "description": "Anulado (no se borra)"}},
             summary="Anular un documento de la biblioteca (no se borra)")
def biblioteca_anular(doc_id: uuid.UUID, datos: AnularIn, actor: Actor = Depends(solo_administrador),
                      db: Session = Depends(get_db)):
    doc = db.get(DocumentoReferencia, doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El documento no existe.")
    try:
        biblioteca.anular(db, doc, datos.motivo, actor.id)
    except biblioteca.ErrorBiblioteca as exc:
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    db.commit()
    return biblioteca.out(doc)
