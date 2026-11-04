"""
Asistente RICORA con IA (app/servicios/asistente.py): orienta en archivística y en el uso del sistema.
Cualquier persona con sesión puede usarlo; no lee documentos ni cambia nada.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permisos import Actor, usuario_actual
from app.db.session import get_db
from app.schemas.respuestas_sistema import EstadoAsistenteOut, RespuestaAsistenteOut
from app.servicios import asistente
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


@router.get("/estado", responses={200: {"model": EstadoAsistenteOut, "description": "Disponibilidad"}},
            summary="Si el asistente con IA está disponible")
def estado(actor: Actor = Depends(usuario_actual)):
    return asistente.estado()


@router.post("/preguntar", responses={200: {"model": RespuestaAsistenteOut, "description": "Respuesta"}},
             summary="Pregunta al Asistente RICORA (orienta; no lee documentos ni cambia nada)")
def preguntar(datos: PreguntaIn, actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    try:
        return asistente.preguntar(db, actor.id, [m.model_dump() for m in datos.mensajes],
                                   datos.pantalla.model_dump() if datos.pantalla else None, datos.fondo)
    except asistente.AsistenteNoDisponible as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except MotorError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
