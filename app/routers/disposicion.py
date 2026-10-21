"""
Disposición final: el calendario de retención del fondo (qué cumple su
retención y qué manda la TRD) y el registro de lo ejecutado como rico:Activity.
Consultar: quien lee la descripción. Ejecutar: solo la administración.
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo, solo_administrador
from app.db.session import get_db
from app.routers.fondos import fondo_o_404
from app.schemas.respuestas_disposicion import ActividadDisposicion, ElementoCalendario
from app.servicios import disposicion

router = APIRouter(prefix="/api/disposicion", tags=["Disposición final"])


@router.get("/calendario", response_model=list[ElementoCalendario],
            summary="Expedientes con su regla, cuándo cumplen la retención y qué manda la TRD")
def calendario(fondo_id: uuid.UUID, al: date | None = None, _: Actor = Depends(acceso_modulo("descripcion")),
               db: Session = Depends(get_db)):
    return disposicion.calendario(db, fondo_o_404(db, fondo_id), al)


@router.get("/historial", response_model=list[ActividadDisposicion],
            summary="Disposiciones ejecutadas en el fondo (rico:Activity)")
def historial(fondo_id: uuid.UUID, _: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    return disposicion.historial(db, fondo_o_404(db, fondo_id))


class EjecutarIn(BaseModel):
    fondo_id: uuid.UUID
    recursos: list[uuid.UUID] = Field(min_length=1, max_length=2000)
    disposicion: Literal["eliminacion", "seleccion", "conservacion_total", "medio_tecnico"]
    acta_numero: str = Field(max_length=60)
    acta_fecha: date
    ejecutor: str = Field(max_length=300)
    acta_recurso_id: uuid.UUID | None = None
    observaciones: str | None = Field(default=None, max_length=5000)


@router.post("/ejecutar", response_model=ActividadDisposicion, status_code=status.HTTP_201_CREATED,
             summary="Registrar una disposición ejecutada según la TRD (con acta), validada en RiC-O")
def ejecutar(datos: EjecutarIn, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    from app.servicios import cuadro

    fondo = fondo_o_404(db, datos.fondo_id)
    punto = db.begin_nested()
    try:
        a = disposicion.ejecutar(db, fondo, recursos=datos.recursos, disposicion=datos.disposicion,
                                 acta_numero=datos.acta_numero, acta_fecha=datos.acta_fecha, ejecutor=datos.ejecutor,
                                 usuario_id=actor.id, acta_recurso_id=datos.acta_recurso_id,
                                 observaciones=datos.observaciones)
        validacion = cuadro.validar_rico(db, fondo)
    except disposicion.ErrorDisposicion as exc:
        punto.rollback()
        db.rollback()
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    if not validacion["conforme"]:
        punto.rollback()
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La disposición no quedaría conforme con "
                            "RiC-O 1.1: " + "; ".join((validacion["problemas_owl"] + [r.get("mensaje") or "" for r in
                                                                                     validacion["resultados_shacl"]])[:3]))
    punto.commit()
    db.commit()
    return next(h for h in disposicion.historial(db, fondo) if h["id"] == str(a.id))
