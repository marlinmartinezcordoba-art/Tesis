"""
Panel central de alertas y estado. Lo alimentan los módulos (hoy: formato
no identificado en ingesta) y lo atienden el archivista o el administrador.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.permisos import ADMINISTRADOR, ARCHIVISTA, REVISOR, Actor, requiere_roles
from app.db.session import get_db
from app.models.alerta import Alerta
from app.models.usuario import Usuario
from app.schemas.ingesta import AlertaOut, AtenderIn
from app.servicios import alertas as servicio
from app.servicios.auditoria import registrar

router = APIRouter(prefix="/api/alertas", tags=["Panel de alertas"])

_ORDEN = case({"alta": 0, "media": 1, "baja": 2}, value=Alerta.severidad)


def _out(a: Alerta, nombres: dict) -> AlertaOut:
    return AlertaOut(id=a.id, tipo=a.tipo, severidad=a.severidad, modulo=a.modulo, mensaje=a.mensaje,
                     entidad_tipo=a.entidad_tipo, entidad_id=a.entidad_id, creada_en=a.creada_en,
                     atendida_en=a.atendida_en, atendida_por=nombres.get(a.atendida_por_id),
                     nota_atencion=a.nota_atencion)


@router.get("", response_model=list[AlertaOut], summary="Alertas del fondo, las más graves primero")
def listar(fondo_id: uuid.UUID | None = None, atendidas: bool = False,
           _: Actor = Depends(requiere_roles(ADMINISTRADOR, ARCHIVISTA, REVISOR)), db: Session = Depends(get_db)):
    consulta = select(Alerta).where(Alerta.atendida_en.isnot(None) if atendidas else Alerta.atendida_en.is_(None))
    if fondo_id is not None:
        consulta = consulta.where(Alerta.fondo_id == fondo_id)
    filas = db.scalars(consulta.order_by(_ORDEN, Alerta.creada_en.desc()).limit(500)).all()
    nombres = dict(db.execute(select(Usuario.id, Usuario.nombre)).all())
    return [_out(a, nombres) for a in filas]


@router.post("/{alerta_id}/atender", response_model=AlertaOut, summary="Marcar una alerta como atendida")
def atender(alerta_id: uuid.UUID, datos: AtenderIn, request: Request,
            actor: Actor = Depends(requiere_roles(ADMINISTRADOR, ARCHIVISTA)), db: Session = Depends(get_db)):
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La alerta no existe.")
    if alerta.atendida_en is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="La alerta ya fue atendida.")
    nota = (datos.nota or "").strip() or None
    servicio.atender(db, alerta, actor.id, nota)
    registrar(db, modulo=alerta.modulo, accion="alerta_atendida", usuario_id=actor.id, entidad_tipo="alerta",
              entidad_id=alerta.id, anterior={"atendida": False}, nuevo={"atendida": True, "nota": nota},
              detalle=alerta.mensaje, request=request)
    db.commit()
    return _out(alerta, {actor.id: actor.usuario.nombre})
