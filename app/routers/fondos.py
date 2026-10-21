"""
Fondos del archivo. El administrador registra cada fondo con su cuadro de
clasificación (y, si la tiene, su TRD), validado en RiC-O antes de crear: no
hay fondos sin cuadro. Las secciones, series y subseries solo salen de la
TRD; la descripción crea expedientes y documentos dentro de ellas.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permisos import Actor, lectura_catalogo, solo_administrador
from app.db.session import get_db
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.schemas import respuestas_cuadro as rc
from app.schemas.ingesta import ExpedienteOut, FondoIn, FondoOut
from app.servicios import fechas
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


def _crear_fondo(db: Session, datos: FondoIn, actor: Actor, request: Request) -> RecursoDocumental:
    if db.scalar(select(RecursoDocumental.id).where(RecursoDocumental.nivel == "fondo",
                                                     func.lower(RecursoDocumental.titulo) == datos.titulo.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Ya existe un fondo con ese nombre.")
    try:
        extremas = fechas.extremas(datos.fechas_extremas)
    except fechas.FechaInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Fechas extremas: {exc} Escríbalas como «1930–1955» o «1930».") from exc
    fondo = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo=datos.titulo,
                              fechas_extremas=(datos.fechas_extremas or "").strip() or None,
                              fechas_extremas_edtf=extremas.edtf if extremas else None,
                              nota=(datos.nota or "").strip() or None, creado_por_id=actor.id)
    fondo.fondo_id = fondo.id
    db.add(fondo)
    db.flush()
    registrar(db, modulo="sistema", accion="fondo_registrado", usuario_id=actor.id, entidad_tipo="recurso_documental",
              entidad_id=fondo.id, nuevo={"titulo": fondo.titulo, "fechas_extremas": fondo.fechas_extremas},
              request=request)
    return fondo


class VersionInicialIn(BaseModel):
    """Datos de la TRD aprobada. Si vienen completos, el fondo nace con la versión 1 vigente."""
    acto_aprobacion: str | None = Field(default=None, max_length=300)
    fecha_aprobacion: date | None = None
    convalidacion: str | None = Field(default=None, max_length=300)
    fecha_convalidacion: date | None = None
    vigente_desde: date | None = None


class ConfigurarFondoIn(BaseModel):
    fondo: FondoIn
    # Las filas del cuadro (CCD) confirmadas en la vista previa de /api/cuadro/vista-previa;
    # la retención (TRD) de cada fila es opcional: un fondo histórico puede no tenerla.
    filas: list[dict] = Field(min_length=1, max_length=3000)
    crear: bool = False
    version: VersionInicialIn | None = None


@router.post("/configurar", response_model=rc.FondoConfigurado,
             summary="Configurar un fondo desde su cuadro de clasificación y su TRD, validado en RiC-O 1.1 antes de crear")
def configurar_fondo(datos: ConfigurarFondoIn, request: Request, actor: Actor = Depends(solo_administrador),
                     db: Session = Depends(get_db)):
    """Arma el fondo con su cuadro (secciones, series, subseries, productor, función, tipos
    documentales y reglas de retención) y lo valida contra RiC-O 1.1 (OWL y SHACL). Con
    `crear=false` solo valida; con `crear=true` lo crea, todo o nada, si es conforme."""
    from app.servicios import cuadro, parametrizacion_trd

    version = datos.version.model_dump() if datos.version else {}
    completa = bool(version.get("acto_aprobacion") and version.get("fecha_aprobacion") and version.get("vigente_desde"))
    punto = db.begin_nested()
    try:
        fondo = _crear_fondo(db, datos.fondo, actor, request)
        if completa:
            # Con el acto y la vigencia, el cuadro sale de la versión 1 de la TRD, aplicada.
            v = parametrizacion_trd.crear_version(db, fondo, version | {"nombre": "TRD versión 1"}, actor.id,
                                                  copiar_vigente=False)
            parametrizacion_trd.importar(db, v, datos.filas, actor.id)
            informe, validacion = parametrizacion_trd.aplicar(db, v, actor.id, crear=True)
        else:
            informe = cuadro.aplicar(db, fondo, datos.filas, actor.id)
            validacion = cuadro.validar_rico(db, fondo)
    except parametrizacion_trd.ErrorTrd as exc:
        punto.rollback()
        db.rollback()
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    except cuadro.ErrorCuadro as exc:
        punto.rollback()
        db.rollback()
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    except HTTPException:
        punto.rollback()
        db.rollback()
        raise
    creado = datos.crear and validacion["conforme"]
    salida = _fondo_out(db, fondo).model_dump(mode="json") if creado else None
    if creado:
        if not completa:
            _primera_version_trd(db, fondo, datos.filas, actor.id, informe)
        punto.commit()
        db.commit()
    else:
        punto.rollback()
        db.rollback()
    return {"creado": creado, "fondo": salida, "informe": informe, "validacion": validacion}


def _primera_version_trd(db: Session, fondo: RecursoDocumental, filas: list[dict], usuario_id, informe: dict) -> None:
    """La TRD cargada al registrar el fondo queda como versión 1 en borrador de la
    parametrización: falta el acto que la aprueba y su vigencia para aplicarla.
    Si el archivo trae dependencias o series sin código, el cuadro se crea igual
    y la matriz se completa a mano."""
    from app.servicios import parametrizacion_trd

    punto = db.begin_nested()
    try:
        v = parametrizacion_trd.crear_version(db, fondo, {"nombre": "TRD versión 1"}, usuario_id, copiar_vigente=False)
        parametrizacion_trd.importar(db, v, filas, usuario_id)
    except parametrizacion_trd.ErrorTrd as exc:
        punto.rollback()
        informe["avisos"].append(f"La matriz de la TRD no se llenó sola ({exc}); complétela en Fondos › "
                                 "Matriz de la TRD.")
        return
    punto.commit()
    informe["avisos"].append("La TRD quedó como versión 1 en borrador: registre el acto que la aprueba y su vigencia "
                             "y aplíquela en Fondos › Versiones de la TRD.")


@router.get("/{fondo_id}/expedientes", response_model=list[ExpedienteOut],
            summary="Expedientes del fondo (destino opcional de la carga)")
def expedientes(fondo_id: uuid.UUID, _: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    filas = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id,
                                                       RecursoDocumental.nivel == "expediente")
                       .order_by(RecursoDocumental.titulo)).all()
    return [ExpedienteOut(id=e.id, titulo=e.titulo, fechas_extremas=e.fechas_extremas, incluido_en_id=e.incluido_en_id)
            for e in filas]
