"""
Fondos del archivo. El administrador registra cada fondo histórico como
punto de partida (RiC-CM: Record Set de nivel fondo); los niveles
inferiores los crea el módulo de descripción.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permisos import Actor, lectura_catalogo, solo_administrador
from app.db.session import get_db
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.schemas.ingesta import ExpedienteOut, FondoIn, FondoOut
from app.servicios.auditoria import registrar

router = APIRouter(prefix="/api/fondos", tags=["Fondos"])


def fondo_o_404(db: Session, fondo_id: uuid.UUID) -> RecursoDocumental:
    fondo = db.get(RecursoDocumental, fondo_id)
    if fondo is None or fondo.nivel != "fondo":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El fondo no existe.")
    return fondo


def _fondo_out(db: Session, f: RecursoDocumental) -> FondoOut:
    documentos = db.scalar(select(func.count(Instanciacion.id)).where(Instanciacion.fondo_id == f.id)) or 0
    return FondoOut(id=f.id, titulo=f.titulo, fechas_extremas=f.fechas_extremas, documentos=documentos)


@router.get("", response_model=list[FondoOut], summary="Fondos registrados")
def listar(_: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    filas = db.scalars(select(RecursoDocumental).where(RecursoDocumental.nivel == "fondo")
                       .order_by(RecursoDocumental.titulo)).all()
    return [_fondo_out(db, f) for f in filas]


@router.post("", response_model=FondoOut, status_code=status.HTTP_201_CREATED, summary="Registrar un fondo")
def registrar_fondo(datos: FondoIn, request: Request, actor: Actor = Depends(solo_administrador),
                    db: Session = Depends(get_db)):
    if db.scalar(select(RecursoDocumental.id).where(RecursoDocumental.nivel == "fondo",
                                                     func.lower(RecursoDocumental.titulo) == datos.titulo.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Ya existe un fondo con ese nombre.")
    fondo = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo=datos.titulo,
                              fechas_extremas=(datos.fechas_extremas or "").strip() or None,
                              nota=(datos.nota or "").strip() or None, creado_por_id=actor.id)
    fondo.fondo_id = fondo.id
    db.add(fondo)
    db.flush()
    registrar(db, modulo="sistema", accion="fondo_registrado", usuario_id=actor.id, entidad_tipo="recurso_documental",
              entidad_id=fondo.id, nuevo={"titulo": fondo.titulo, "fechas_extremas": fondo.fechas_extremas},
              request=request)
    db.commit()
    return _fondo_out(db, fondo)


@router.get("/{fondo_id}/expedientes", response_model=list[ExpedienteOut],
            summary="Expedientes del fondo (destino opcional de la carga)")
def expedientes(fondo_id: uuid.UUID, _: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    filas = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id,
                                                       RecursoDocumental.nivel == "expediente")
                       .order_by(RecursoDocumental.titulo)).all()
    return [ExpedienteOut(id=e.id, titulo=e.titulo, fechas_extremas=e.fechas_extremas) for e in filas]
