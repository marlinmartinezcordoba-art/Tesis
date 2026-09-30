"""
Módulo 2 · Descripción multinivel asistida por inteligencia artificial.

Flujo: cola «por describir» → iniciar (marca en edición + propuesta del
motor) → validar cada entidad (con verificación de vocabulario) →
publicar (una sola transacción). Una descripción publicada se reabre y
corrige con auditoría de valores anteriores y nuevos.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.permisos import Actor, acceso_modulo, lectura_catalogo
from app.db.session import get_db
from app.models.descripcion import Relacion, TrabajoDescripcion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import NIVEL_DESCRIPCION, RecursoDocumental
from app.models.usuario import Usuario
from app.routers.fondos import fondo_o_404
from app.schemas.descripcion import (
    CoincidenciaOut, EditarIn, ElementoPorDescribir, IniciarIn, NivelSuperiorOut, PublicadaOut, PublicarIn, VerificarIn,
)
from app.servicios import consulta, descripcion, motor, vocabulario
from app.servicios.auditoria import registrar

router = APIRouter(prefix="/api/descripcion", tags=["Módulo 2 · Descripción"],
                   dependencies=[Depends(acceso_modulo("descripcion"))])


def _error(exc: descripcion.ErrorDescripcion) -> JSONResponse:
    return JSONResponse({"detail": str(exc), **(exc.datos or {})}, status_code=exc.codigo)


def _espacio(db: Session, trabajo: TrabajoDescripcion) -> dict:
    """Todo lo que la pantalla de trabajo necesita, para abrirla o recargarla."""
    documentos = descripcion.documentos_de(db, trabajo)
    fondo = db.get(RecursoDocumental, trabajo.fondo_id)
    return {
        "trabajo_id": str(trabajo.id),
        "nivel": trabajo.nivel,
        "fondo": {"id": str(fondo.id), "titulo": fondo.titulo},
        "recurso_id": str(trabajo.recurso_id) if trabajo.recurso_id else None,
        "documentos": [{"id": str(d.id), "nombre": d.nombre_original, "texto": d.texto_extraido or "",
                        "origen_texto": d.origen_texto, "expediente_destino_id": str(d.expediente_destino_id) if d.expediente_destino_id else None}
                       for d in documentos],
        "propuesta": json.loads(trabajo.propuesta) if trabajo.propuesta else None,
        "minutos_bloqueo": settings.minutos_bloqueo_descripcion,
        "umbral_confianza": settings.umbral_confianza,
    }


# --- Cola --------------------------------------------------------------------------------


@router.get("/cola", response_model=list[ElementoPorDescribir], summary="Documentos listos y todavía sin describir")
def cola(fondo_id: uuid.UUID, db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    filas = descripcion.cola(db, fondo_id)
    db.commit()  # por si venció alguna marca de edición
    expedientes = {e.id: e.titulo for e in db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == fondo_id, RecursoDocumental.nivel == "expediente"))}
    return [ElementoPorDescribir(
        id=i.id, nombre=i.nombre_original, tamano_bytes=i.tamano_bytes, formato=i.formato_nombre,
        expediente=expedientes.get(i.expediente_destino_id), origen_texto=i.origen_texto, cargado_en=i.cargado_en,
        en_edicion_por=quien) for i, quien in filas]


@router.get("/niveles-superiores", response_model=list[NivelSuperiorOut],
            summary="Dónde puede quedar incluido lo que se describe")
def niveles_superiores(fondo_id: uuid.UUID, nivel: str, db: Session = Depends(get_db)):
    if nivel not in NIVEL_DESCRIPCION:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nivel desconocido.")
    fondo_o_404(db, fondo_id)
    filas = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id)).all()
    posibles = [r for r in filas if descripcion.rango(r.nivel) < descripcion.rango(nivel)]
    posibles.sort(key=lambda r: (descripcion.rango(r.nivel), r.titulo))
    return [NivelSuperiorOut(id=r.id, titulo=r.titulo, nivel=r.nivel) for r in posibles]


# --- Espacio de trabajo -----------------------------------------------------------------------


@router.post("/iniciar", summary="Marcar en edición y obtener la propuesta del motor")
async def iniciar(datos: IniciarIn, request: Request, actor: Actor = Depends(acceso_modulo("descripcion")),
                  db: Session = Depends(get_db)):
    try:
        trabajo = await run_in_threadpool(
            descripcion.abrir, db, usuario_id=actor.id, instanciacion_ids=datos.instanciacion_ids, nivel=datos.nivel)
        registrar(db, modulo="descripcion", accion="descripcion_iniciada", usuario_id=actor.id,
                  entidad_tipo="trabajo_descripcion", entidad_id=trabajo.id,
                  nuevo={"nivel": trabajo.nivel, "documentos": [str(i) for i in datos.instanciacion_ids]}, request=request)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    except IntegrityError:
        db.rollback()
        return JSONResponse({"detail": "Otra persona acaba de abrir alguno de estos documentos."}, status_code=409)

    # El motor se consulta con la marca ya tomada (puede tardar unos segundos).
    documentos = [motor.Documento(id=d.id, nombre=d.nombre_original, texto=d.texto_extraido or "")
                  for d in descripcion.documentos_de(db, trabajo)]
    propuesta = await run_in_threadpool(motor.proponer, documentos, trabajo.nivel)
    trabajo.propuesta = json.dumps(propuesta.a_dict(), ensure_ascii=False)
    descripcion.latido(db, trabajo)
    db.commit()
    return _espacio(db, trabajo)


@router.get("/trabajos/{trabajo_id}", summary="Reabrir la pantalla de un trabajo en curso")
def ver_trabajo(trabajo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    try:
        trabajo = descripcion.trabajo_propio(db, trabajo_id, actor.id)
    except descripcion.ErrorDescripcion as exc:
        db.commit()
        return _error(exc)
    return _espacio(db, trabajo)


@router.post("/trabajos/{trabajo_id}/latido", status_code=status.HTTP_204_NO_CONTENT,
             summary="Mantener la marca «en edición» mientras se trabaja")
def mantener(trabajo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    try:
        trabajo = descripcion.trabajo_propio(db, trabajo_id, actor.id)
    except descripcion.ErrorDescripcion as exc:
        db.commit()
        return _error(exc)
    descripcion.latido(db, trabajo)
    db.commit()


@router.post("/{trabajo_id}/cancelar", status_code=status.HTTP_204_NO_CONTENT,
             summary="Salir sin publicar: libera la marca «en edición»")
def cancelar(trabajo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    try:
        trabajo = descripcion.trabajo_propio(db, trabajo_id, actor.id)
    except descripcion.ErrorDescripcion as exc:
        db.commit()
        return _error(exc)
    descripcion.cancelar(db, trabajo, actor.id)
    db.commit()


@router.post("/verificar-vocabulario", response_model=list[CoincidenciaOut],
             summary="¿Ya existe en el vocabulario del fondo? (delegado al servicio de vocabularios)")
def verificar(datos: VerificarIn, db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    return [CoincidenciaOut(**c.__dict__) for c in vocabulario.verificar(db, datos.fondo_id, datos.tipo, datos.valor)]


@router.post("/publicar", status_code=status.HTTP_201_CREATED, summary="Publicar la descripción (una sola transacción)")
def publicar(datos: PublicarIn, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    try:
        trabajo = descripcion.trabajo_propio(db, datos.trabajo_id, actor.id)
        if trabajo.recurso_id is not None:
            raise descripcion.ErrorDescripcion("Este trabajo es una corrección: use la edición de la descripción.", 409)
        recurso = descripcion.publicar(
            db, trabajo=trabajo, usuario_id=actor.id, titulo=datos.titulo, alcance=datos.alcance_contenido,
            incluido_en_id=datos.incluido_en_id,
            entidades=[descripcion.EntidadConfirmada(**e.model_dump()) for e in datos.entidades])
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        # La marca sigue tomada: el archivista corrige y vuelve a publicar.
        return _error(exc)
    return descripcion.detalle(db, recurso)


# --- Descripciones publicadas: consulta interna y corrección ------------------------------------------


def _recurso_o_404(db: Session, recurso_id: uuid.UUID) -> RecursoDocumental:
    recurso = db.get(RecursoDocumental, recurso_id)
    if recurso is None or recurso.publicado_en is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La descripción no existe.")
    return recurso


@router.get("/publicadas", response_model=list[PublicadaOut], summary="Descripciones publicadas del fondo")
def publicadas(fondo_id: uuid.UUID, db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    descripcion.expirar(db)
    db.commit()
    filas = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo_id,
                                                       RecursoDocumental.publicado_en.isnot(None))
                       .order_by(RecursoDocumental.publicado_en.desc()).limit(500)).all()
    documentos = dict(db.execute(select(Relacion.origen_id, func.count(Relacion.id)).where(
        Relacion.codigo_ric == "has_or_had_instantiation", Relacion.estado == "vigente").group_by(Relacion.origen_id)).all())
    editores = dict(db.execute(select(TrabajoDescripcion.recurso_id, Usuario.nombre)
                               .join(Usuario, Usuario.id == TrabajoDescripcion.usuario_id)
                               .where(TrabajoDescripcion.estado == "abierto", TrabajoDescripcion.recurso_id.isnot(None))).all())
    return [PublicadaOut(id=r.id, titulo=r.titulo, nivel=r.nivel, documentos=documentos.get(r.id, 0),
                         publicado_en=r.publicado_en, actualizado_en=r.actualizado_en,
                         en_edicion_por=editores.get(r.id)) for r in filas]


@router.get("/registros/{recurso_id}", summary="Descripción publicada, vista interna (con origen y confianza)")
def ver(recurso_id: uuid.UUID, db: Session = Depends(get_db)):
    return descripcion.detalle(db, _recurso_o_404(db, recurso_id))


@router.post("/registros/{recurso_id}/reabrir", summary="Reabrir una descripción publicada para corregirla")
def reabrir(recurso_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    try:
        trabajo = descripcion.reabrir(db, recurso, actor.id)
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    except IntegrityError:
        db.rollback()
        return JSONResponse({"detail": "Otra persona acaba de abrir esta descripción."}, status_code=409)
    return {"trabajo_id": str(trabajo.id), "descripcion": descripcion.detalle(db, recurso)}


@router.patch("/{recurso_id}", summary="Corregir una descripción publicada (queda en auditoría)")
def editar(recurso_id: uuid.UUID, datos: EditarIn, actor: Actor = Depends(acceso_modulo("descripcion")),
           db: Session = Depends(get_db)):
    recurso = _recurso_o_404(db, recurso_id)
    try:
        trabajo = descripcion.trabajo_propio(db, datos.trabajo_id, actor.id)
        descripcion.editar(
            db, recurso=recurso, trabajo=trabajo, usuario_id=actor.id, titulo=datos.titulo,
            alcance=datos.alcance_contenido, incluido_en_id=datos.incluido_en_id, anular=datos.anular_relaciones,
            quitar_forma=datos.quitar_forma_documental,
            agregar=[descripcion.EntidadConfirmada(**e.model_dump()) for e in datos.agregar_entidades])
        db.commit()
    except descripcion.ErrorDescripcion as exc:
        db.rollback()
        return _error(exc)
    return descripcion.detalle(db, recurso)


# --- Consulta pública (base del catálogo del módulo 4) ------------------------------------------------

catalogo = APIRouter(prefix="/api/catalogo", tags=["Catálogo de consulta"])


@catalogo.get("/registros/{recurso_id}", summary="Ficha de consulta de una descripción publicada")
def ficha(recurso_id: uuid.UUID, _: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    return consulta.ficha_publica(db, _recurso_o_404(db, recurso_id))
