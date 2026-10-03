"""
Módulo transversal de auditoría: consulta del registro.

- Trazabilidad por entidad y trazabilidad propia: roles con auditoría
  «propia» (solo sus acciones) o «todo».
- Panel consolidado semanal y desglose por persona: solo quien ve toda la
  auditoría (el administrador, y el rol al que él le dé ese permiso).

El registro no se escribe por HTTP: los módulos llaman a
servicios/auditoria.registrar() dentro del mismo proceso. Ninguna ruta de
este archivo modifica ni borra eventos.
"""

import uuid
from datetime import date

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo, sin_permiso, solo_administrador, usuario_actual
from app.db.base import ahora
from app.db.session import get_db
from app.models.usuario import Usuario
from app.servicios import decisiones_ia, trazabilidad

router = APIRouter(prefix="/api/auditoria", tags=["Auditoría (transversal)"],
                   dependencies=[Depends(acceso_modulo("auditoria"))])


def ve_todo(actor: Actor = Depends(usuario_actual)) -> Actor:
    if not actor.ve_toda_la_auditoria:
        raise sin_permiso()
    return actor


def _solo_de(actor: Actor) -> uuid.UUID | None:
    """Principio de visibilidad: quien no ve toda la auditoría solo ve lo
    que hizo él mismo, en cualquier consulta."""
    return None if actor.ve_toda_la_auditoria else actor.id


@router.get("/acciones", summary="Tipos de acción disponibles para filtrar")
def acciones(actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    return trazabilidad.acciones_de(db, _solo_de(actor))


@router.get("/mi-trazabilidad", summary="Acciones del usuario autenticado, filtrables por tipo, módulo y fechas")
def mi_trazabilidad(accion: str | None = None, modulo: str | None = None, desde: date | None = None,
                    hasta: date | None = None, antes_de: int | None = None,
                    actor: Actor = Depends(usuario_actual), db: Session = Depends(get_db)):
    if desde and hasta and desde > hasta:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La fecha inicial es posterior a la final.")
    return trazabilidad.propia(db, actor.id, accion=accion, modulo=modulo, desde=desde, hasta=hasta, antes_de=antes_de)


@router.get("/entidad/{entidad_id}", summary="Historial de auditoría de una entidad")
def entidad(entidad_id: str, tipo: str = Query(..., max_length=60), actor: Actor = Depends(usuario_actual),
            db: Session = Depends(get_db)):
    if tipo not in trazabilidad.MODULO_DE_ENTIDAD:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tipo de entidad desconocido.")
    modulo = trazabilidad.MODULO_DE_ENTIDAD[tipo]
    # Hay que tener acceso a la entidad (su módulo) además de a la auditoría.
    if modulo and not (actor.puede(modulo) or (tipo == "instanciacion" and actor.puede("preservacion"))):
        raise sin_permiso()
    return {"entidad_tipo": tipo, "entidad_id": entidad_id, "solo_propias": not actor.ve_toda_la_auditoria,
            "eventos": trazabilidad.entidad(db, tipo, entidad_id[:64], solo_de=_solo_de(actor))}


def _dia(semana: date | None) -> date:
    return semana or ahora().astimezone(trazabilidad._zona()).date()


@router.get("/consolidado", summary="Panel semanal por persona: días, horas conectadas y acciones")
def consolidado(semana: date | None = None, _: Actor = Depends(ve_todo), db: Session = Depends(get_db)):
    return trazabilidad.consolidado(db, _dia(semana))


@router.get("/consolidado/{usuario_id}", summary="Desglose sesión por sesión de una persona en la semana")
def desglose(usuario_id: uuid.UUID, semana: date | None = None, _: Actor = Depends(ve_todo),
             db: Session = Depends(get_db)):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La persona no existe.")
    return trazabilidad.desglose(db, usuario, _dia(semana))


# --- Decisiones de validación asistida por IA (solo administrador) -----------------------------------

TipoDecision = Literal["agente", "lugar", "fecha", "forma_documental", "actividad", "tipo_actividad", "mandato",
                       "titulo", "alcance"]
Decision = Literal["aceptada", "corregida", "rechazada", "agregada"]


def _filtros(tipo, decision, desde, hasta, fondo_id) -> dict:
    if desde and hasta and desde > hasta:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La fecha inicial es posterior a la final.")
    return {"tipo": tipo, "decision": decision, "desde": desde, "hasta": hasta, "fondo_id": fondo_id}


@router.get("/decisiones-ia", summary="Cada propuesta del motor frente a lo que quedó confirmado")
def decisiones(tipo: TipoDecision | None = None, decision: Decision | None = None, desde: date | None = None,
               hasta: date | None = None, fondo_id: uuid.UUID | None = None,
               _: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return decisiones_ia.consultar(db, **_filtros(tipo, decision, desde, hasta, fondo_id))


@router.get("/decisiones-ia/hoja-de-calculo", summary="Las mismas decisiones en una hoja de cálculo (evaluación)")
def decisiones_xlsx(tipo: TipoDecision | None = None, decision: Decision | None = None, desde: date | None = None,
                    hasta: date | None = None, fondo_id: uuid.UUID | None = None,
                    _: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    contenido = decisiones_ia.hoja_de_calculo(db, **_filtros(tipo, decision, desde, hasta, fondo_id))
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="decisiones-ia.xlsx"'})
