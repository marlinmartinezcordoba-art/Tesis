"""
Evaluación del rendimiento del motor con la medida F1 (objetivo 3).

- Administración (solo administrador): crear la evaluación, agregar o quitar documentos, sortear
  los conjuntos de desarrollo y prueba, fijar los umbrales, iniciar y cerrar, ver los resultados y
  descargarlos en Excel.
- Validadoras (permiso de escribir en Descripción): la validación de control de un documento de
  prueba y la causa de cada error. La validación principal se hace en Descripción, como siempre.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permisos import Actor, evaluacion_encendida, sin_permiso, solo_administrador, usuario_actual
from app.db.session import get_db
from app.models.evaluacion import Evaluacion
from app.routers.fondos import fondo_o_404
from app.schemas import respuestas_evaluacion as re_
from app.servicios import evaluacion

router = APIRouter(prefix="/api/evaluacion", tags=["Evaluación del rendimiento (medida F1)"],
                   dependencies=[Depends(evaluacion_encendida)])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


def _hecho(db: Session, funcion, *args, **kwargs):
    try:
        resultado = funcion(*args, **kwargs)
    except evaluacion.ErrorEvaluacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return resultado


def _leer(funcion, *args, **kwargs):
    try:
        return funcion(*args, **kwargs)
    except evaluacion.ErrorEvaluacion as exc:
        raise _error(exc) from exc


class EvaluacionIn(BaseModel):
    fondo_id: uuid.UUID
    nombre: str = Field(min_length=3, max_length=200)
    protocolo: str | None = Field(default=None, max_length=10000)


class DocumentosIn(BaseModel):
    instanciacion_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class SorteoIn(BaseModel):
    semilla: int = Field(ge=0, le=2_147_483_647)
    desarrollo: int = Field(ge=1, le=199)


class CriterioIn(BaseModel):
    """Umbrales de aceptación, fijados antes de iniciar."""
    f1: float = Field(default=0.80, gt=0, le=1)
    precision: float = Field(default=0.85, gt=0, le=1)
    exhaustividad: float = Field(default=0.80, gt=0, le=1)
    acuerdo: float = Field(default=0.80, gt=0, le=1)


class EstadoIn(BaseModel):
    estado: Literal["en_curso", "cerrada"]


class ControlIn(BaseModel):
    decision: Literal["aceptada", "corregida", "rechazada"]


class CausaIn(BaseModel):
    causa: Literal["lectura", "ambiguedad", "regla", "invencion"]
    nota: str | None = Field(default=None, max_length=2000)


@router.get("", responses={200: {"model": list[re_.EvaluacionOut], "description": "Evaluaciones del fondo"}},
            summary="Evaluaciones del fondo")
def listar(fondo_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    consulta = select(Evaluacion).where(Evaluacion.fondo_id == fondo_id).order_by(Evaluacion.creada_en.desc())
    if not actor.es_administrador:  # las validadoras ven las evaluaciones en curso
        consulta = consulta.where(Evaluacion.estado == "en_curso")
    return [evaluacion.evaluacion_out(db, e) for e in db.scalars(consulta).all()]


@router.get("/automatica", response_model=re_.AutomaticaOut, summary="Evaluación automática: la calculan las descripciones publicadas del fondo")
def automatica(fondo_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    return evaluacion.automatica(db, fondo_id)


@router.post("", status_code=status.HTTP_201_CREATED,
             responses={201: {"model": re_.EvaluacionOut, "description": "Evaluación creada"}}, summary="Crear una evaluación")
def crear(datos: EvaluacionIn, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    ev = _hecho(db, evaluacion.crear, db, fondo_id=datos.fondo_id, nombre=datos.nombre, protocolo=datos.protocolo,
                usuario_id=actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.get("/{evaluacion_id}", responses={200: {"model": re_.EvaluacionOut, "description": "Evaluación"}},
            summary="Una evaluación")
def ver(evaluacion_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    return evaluacion.evaluacion_out(db, _ev(db, evaluacion_id))


@router.get("/{evaluacion_id}/documentos", responses={200: {"model": list[re_.DocumentoOut],
                                                               "description": "Documentos con su conjunto"}},
            summary="Documentos de la evaluación, su conjunto y si ya se publicaron")
def listar_documentos(evaluacion_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    return evaluacion.documentos_out(db, _ev(db, evaluacion_id))


@router.post("/{evaluacion_id}/documentos", responses={200: {"model": re_.EvaluacionOut, "description": "Documentos agregados"}},
             summary="Agregar documentos aún no descritos")
def agregar(evaluacion_id: uuid.UUID, datos: DocumentosIn, actor: Actor = Depends(solo_administrador),
            db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.agregar_documentos, db, ev, datos.instanciacion_ids, actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.delete("/{evaluacion_id}/documentos/{inst_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses={204: {"description": "Documento quitado"}}, summary="Quitar un documento antes del sorteo")
def quitar(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, actor: Actor = Depends(solo_administrador),
           db: Session = Depends(get_db)):
    _hecho(db, evaluacion.quitar_documento, db, _ev(db, evaluacion_id), inst_id, actor.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{evaluacion_id}/sorteo", responses={200: {"model": re_.SorteoOut, "description": "Resultado del sorteo"}},
             summary="Sortear los conjuntos de desarrollo y de prueba con una semilla")
def sorteo(evaluacion_id: uuid.UUID, datos: SorteoIn, actor: Actor = Depends(solo_administrador),
           db: Session = Depends(get_db)):
    return _hecho(db, evaluacion.sortear, db, _ev(db, evaluacion_id), datos.semilla, datos.desarrollo, actor.id)


@router.put("/{evaluacion_id}/criterio", responses={200: {"model": re_.EvaluacionOut, "description": "Umbrales fijados"}},
            summary="Fijar los umbrales de aceptación (solo en preparación)")
def criterio(evaluacion_id: uuid.UUID, datos: CriterioIn, actor: Actor = Depends(solo_administrador),
             db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.fijar_criterio, db, ev, datos.model_dump(), actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.post("/{evaluacion_id}/estado", responses={200: {"model": re_.EvaluacionOut, "description": "Nuevo estado"}},
             summary="Iniciar (congela la versión) o cerrar la evaluación")
def estado(evaluacion_id: uuid.UUID, datos: EstadoIn, actor: Actor = Depends(solo_administrador),
           db: Session = Depends(get_db)):
    ev = _ev(db, evaluacion_id)
    _hecho(db, evaluacion.cambiar_estado, db, ev, datos.estado, actor.id)
    return evaluacion.evaluacion_out(db, ev)


@router.get("/{evaluacion_id}/resultados", responses={200: {"model": re_.ResultadosOut, "description": "Resultados"}},
            summary="Medida F1, precisión y exhaustividad con intervalos, dictamen y acuerdo")
def resultados(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return evaluacion.resultados(db, _ev(db, evaluacion_id))


@router.get("/{evaluacion_id}/resultados/hoja-de-calculo",
            responses={200: {"content": {XLSX: {}}, "description": "Resultados y decisiones en Excel"}},
            summary="Resultados y decisiones en Excel (la hoja Decisiones se importa al Anexo D)")
def hoja(evaluacion_id: uuid.UUID, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    contenido = evaluacion.hoja_de_calculo(db, _ev(db, evaluacion_id))
    return Response(contenido, media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="evaluacion-f1.xlsx"'})


@router.get("/{evaluacion_id}/control/{inst_id}",
            responses={200: {"model": re_.ControlOut, "description": "Propuestas originales para la validación de control"}},
            summary="Las propuestas originales de un documento de prueba, sin la decisión de la primera validadora")
def control(evaluacion_id: uuid.UUID, inst_id: uuid.UUID, actor: Actor = Depends(evaluador),
            db: Session = Depends(get_db)):
    return _leer(evaluacion.control_pendiente, db, _ev(db, evaluacion_id), inst_id, actor.id)


@router.put("/{evaluacion_id}/control/decisiones/{evento_id}",
            responses={200: {"model": re_.HechoOut, "description": "Decisión de control registrada"}},
            summary="Registrar la decisión de la segunda validadora sobre una propuesta")
def guardar_control(evaluacion_id: uuid.UUID, evento_id: int, datos: ControlIn, actor: Actor = Depends(evaluador),
                    db: Session = Depends(get_db)):
    _hecho(db, evaluacion.guardar_control, db, _ev(db, evaluacion_id), evento_id, datos.decision, actor.id)
    return {"ok": True}


@router.get("/{evaluacion_id}/errores", responses={200: {"model": list[re_.ErrorOut], "description": "Errores del motor"}},
            summary="Las propuestas corregidas, rechazadas o agregadas, con su causa")
def errores(evaluacion_id: uuid.UUID, actor: Actor = Depends(evaluador), db: Session = Depends(get_db)):
    return evaluacion.errores(db, _ev(db, evaluacion_id))


@router.put("/{evaluacion_id}/errores/{evento_id}", responses={200: {"model": re_.HechoOut, "description": "Causa registrada"}},
            summary="Registrar la causa de un error")
def causa(evaluacion_id: uuid.UUID, evento_id: int, datos: CausaIn, actor: Actor = Depends(evaluador),
          db: Session = Depends(get_db)):
    _hecho(db, evaluacion.clasificar, db, _ev(db, evaluacion_id), evento_id, datos.causa, datos.nota, actor.id)
    return {"ok": True}
