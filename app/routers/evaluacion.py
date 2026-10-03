"""
Evaluación ciega del motor frente a archivistas (objetivo 3 de la tesis).

- Administración (solo administrador): crear la evaluación, agregar
  documentos, generar las propuestas del motor, iniciarla, cerrarla, ver
  los resultados y anular una anotación.
- Archivistas (permiso de escribir en Descripción): sus tareas, describir
  a ciegas, describir con la propuesta (asistida), y calificar la propuesta.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permisos import Actor, sin_permiso, solo_administrador, usuario_actual
from app.db.session import get_db
from app.models.evaluacion import Anotacion, Evaluacion
from app.routers.fondos import fondo_o_404
from app.servicios import evaluacion
from app.servicios.auditoria import registrar

router = APIRouter(prefix="/api/evaluacion", tags=["Evaluación ciega"])


def evaluador(actor: Actor = Depends(usuario_actual)) -> Actor:
    if not (actor.es_administrador or actor.puede("descripcion", "escribir")):
        raise sin_permiso()
    return actor


def _error(exc: evaluacion.ErrorEvaluacion) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


def _ev(db: Session, evaluacion_id: uuid.UUID) -> Evaluacion:
    try:
        return evaluacion._evaluacion(db, evaluacion_id)
    except evaluacion.ErrorEvaluacion as exc:
        raise _error(exc) from exc


class EvaluacionIn(BaseModel):
    fondo_id: uuid.UUID
    nombre: str = Field(min_length=3, max_length=200)
    protocolo: str | None = Field(default=None, max_length=10000)
    umbral_similitud: float = Field(default=0.85, ge=0.5, le=1)


class DocumentosIn(BaseModel):
    instanciacion_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class EstadoIn(BaseModel):
    estado: Literal["en_curso", "cerrada"]


class AnotarIn(BaseModel):
    condicion: Literal["ciega", "asistida"]


class DatosIn(BaseModel):
    titulo: str | None = Field(default=None, max_length=300)
    alcance: str | None = Field(default=None, max_length=5000)
    entidades: list[dict] = Field(default_factory=list, max_length=200)
    enviar: bool = False


class CalificacionIn(BaseModel):
    exactitud: int = Field(ge=1, le=5)
    completitud: int = Field(ge=1, le=5)
    pertinencia: int = Field(ge=1, le=5)


def _hecho(db: Session, funcion, *args, **kwargs):
    try:
        resultado = funcion(*args, **kwargs)
    except evaluacion.ErrorEvaluacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return resultado


@router.get("", summary="Evaluaciones: todas para la administración; las en curso para quien anota")
def listar(fondo_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    consulta = select(Evaluacion).where(Evaluacion.fondo_id == fondo_id).order_by(Evaluacion.creada_en.desc())
    if not actor.es_administrador:
        consulta = consulta.where(Evaluacion.estado == "en_curso")
    return [evaluacion.evaluacion_out(db, e) for e in db.scalars(consulta).all()]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Crear una evaluación")
def crear(datos: EvaluacionIn, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    ev = _hecho(db, evaluacion.crear, db, fondo_id=datos.fondo_id, nombre=datos.nombre, protocolo=datos.protocolo,
                umbral=datos.umbral_similitud, usuario_id=actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.post("/{evaluacion_id}/documentos", summary="Agregar documentos aún no descritos")
def documentos(evaluacion_id: uuid.UUID, datos: DocumentosIn, actor: Actor = Depends(solo_administrador),
               db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.agregar_documentos, db, ev, datos.instanciacion_ids, actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.post("/{evaluacion_id}/propuestas", summary="Generar, sin mostrarlas, las propuestas del motor")
def propuestas(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    resultado = _hecho(db, evaluacion.generar_propuestas, db, ev, actor.id)
    return resultado | {"evaluacion": evaluacion.evaluacion_out(db, ev)}


@router.post("/{evaluacion_id}/estado", summary="Iniciar o cerrar la evaluación")
def estado(evaluacion_id: uuid.UUID, datos: EstadoIn, actor: Actor = Depends(solo_administrador),
           db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.cambiar_estado, db, ev, datos.estado, actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.get("/{evaluacion_id}/tareas", summary="Los documentos de la evaluación y lo que la persona ya hizo")
def tareas(evaluacion_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    return {"evaluacion": evaluacion.evaluacion_out(db, ev), "tareas": evaluacion.tareas(db, ev, actor.id)}


@router.post("/{evaluacion_id}/documentos/{inst_id}/anotar", summary="Empezar (o retomar) una descripción ciega o asistida")
def anotar(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, datos: AnotarIn, actor: Actor = Depends(evaluador),
           db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    a = _hecho(db, evaluacion.iniciar_anotacion, db, ev, inst_id, datos.condicion, actor.id)
    return evaluacion.anotacion_out(db, a)


@router.put("/anotaciones/{anotacion_id}", summary="Guardar o enviar una descripción")
def guardar(anotacion_id: uuid.UUID, datos: DatosIn, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    a = db.get(Anotacion, anotacion_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La anotación no existe.")
    a = _hecho(db, evaluacion.guardar, db, a, datos.model_dump(exclude={"enviar"}), actor.id, datos.enviar)
    return evaluacion.anotacion_out(db, a)


@router.post("/{evaluacion_id}/documentos/{inst_id}/propuesta",
             summary="Ver la propuesta del motor para calificarla (desde ahí ya no se describe a ciegas)")
def ver_propuesta(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, actor: Actor = Depends(evaluador),
                  db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    return _hecho(db, evaluacion.ver_propuesta, db, ev, inst_id, actor.id)


@router.put("/{evaluacion_id}/documentos/{inst_id}/calificacion", summary="Calificar la propuesta con la rúbrica 1–5")
def calificar(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, datos: CalificacionIn, actor: Actor = Depends(evaluador),
              db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.calificar, db, ev, inst_id, datos.model_dump(), actor.id)
    return {"calificado": True}


@router.post("/anotaciones/{anotacion_id}/anular", summary="Anular una anotación (no se borra)")
def anular(anotacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    a = db.get(Anotacion, anotacion_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La anotación no existe.")
    anterior, a.estado = a.estado, "anulada"
    registrar(db, modulo="evaluacion", accion="anotacion_anulada", usuario_id=actor.id, entidad_tipo="instanciacion",
              entidad_id=a.instanciacion_id, anterior={"estado": anterior},
              nuevo={"estado": "anulada", "anotacion_id": str(a.id), "condicion": a.condicion})
    db.commit()
    return {"estado": a.estado}


@router.get("/{evaluacion_id}/resultados", summary="Precisión, exhaustividad, F1, acuerdo, tiempos y rúbrica")
def resultados(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    return _hecho(db, evaluacion.resultados, db, ev, actor.id)


@router.get("/{evaluacion_id}/resultados/hoja-de-calculo", summary="Los resultados en una hoja de cálculo")
def resultados_xlsx(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    datos = _hecho(db, evaluacion.resultados, db, ev, actor.id)
    return Response(evaluacion.hoja_de_calculo(datos),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="evaluacion-ciega.xlsx"'})
