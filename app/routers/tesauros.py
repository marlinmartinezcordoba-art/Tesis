"""
Tesauros para normalizar las materias de la descripción.

- Consultar (quien lee vocabularios): los tesauros, un concepto, y la
  normalización de un término.
- Importar y anular (solo administración): un archivo SKOS, Excel o CSV.
- Materia (quien escribe en vocabularios): la materia del fondo para un concepto.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.permisos import Actor, acceso_modulo, solo_administrador
from app.db.session import get_db
from app.models.tesauro import ConceptoTesauro, Tesauro
from app.routers.fondos import fondo_o_404
from app.schemas import respuestas_tesauros as rt
from app.servicios import tesauros

router = APIRouter(prefix="/api/tesauros", tags=["Tesauros"], dependencies=[Depends(acceso_modulo("vocabularios"))])


def _error(exc: tesauros.ErrorTesauro) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


def _tesauro(db: Session, tesauro_id: uuid.UUID) -> Tesauro:
    t = db.get(Tesauro, tesauro_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El tesauro no existe.")
    return t


@router.get("", responses={200: {"model": list[rt.TesauroOut], "description": "Tesauros importados"}},
            summary="Los tesauros importados (vigentes y anulados)")
def listar(db: Session = Depends(get_db)):
    return [tesauros.tesauro_out(t) for t in db.scalars(select(Tesauro).order_by(Tesauro.importado_en.desc())).all()]


@router.post("", status_code=status.HTTP_201_CREATED,
             responses={201: {"model": rt.TesauroOut, "description": "Tesauro importado"}},
             summary="Importar un tesauro (multipart: archivo SKOS, Excel o CSV; nombre, fuente, licencia, idioma)")
async def importar(request: Request, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    formulario = await request.form(max_files=1)
    try:
        archivo = formulario.get("archivo")
        if not isinstance(archivo, StarletteUploadFile):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No llegó el archivo del tesauro.")
        nombre = str(formulario.get("nombre") or "").strip()
        if len(nombre) < 3:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Escriba el nombre del tesauro.")
        contenido = await archivo.read(tesauros.MAX_BYTES + 1)
        datos = {"nombre": nombre, "contenido": contenido, "archivo": archivo.filename or "tesauro",
                 "fuente": formulario.get("fuente"), "licencia": formulario.get("licencia"),
                 "idioma": str(formulario.get("idioma") or "es")[:8]}
    finally:
        await formulario.close()

    def hacer():
        try:
            t = tesauros.importar(db, usuario_id=actor.id, **datos)
        except tesauros.ErrorTesauro as exc:
            db.rollback()
            raise _error(exc) from exc
        db.commit()
        return tesauros.tesauro_out(t)
    return await run_in_threadpool(hacer)


class AnularIn(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


@router.post("/{tesauro_id}/anular", responses={200: {"model": rt.TesauroOut, "description": "Tesauro anulado"}},
             summary="Anular un tesauro (no se borra; las materias ya normalizadas no cambian)")
def anular(tesauro_id: uuid.UUID, datos: AnularIn, actor: Actor = Depends(solo_administrador),
           db: Session = Depends(get_db)):
    try:
        t = tesauros.anular(db, _tesauro(db, tesauro_id), datos.motivo, actor.id)
    except tesauros.ErrorTesauro as exc:
        raise _error(exc) from exc
    db.commit()
    return tesauros.tesauro_out(t)


@router.get("/normalizar", responses={200: {"model": rt.NormalizacionOut, "description": "Concepto que corresponde"}},
            summary="Normalizar un término: el concepto exacto (también por un término no preferente) y los parecidos")
def normalizar(texto: str, tesauro_id: uuid.UUID | None = None, db: Session = Depends(get_db)):
    return tesauros.normalizar_termino(db, texto[:300], tesauro_id=tesauro_id)


@router.get("/conceptos/{concepto_id}", responses={200: {"model": rt.ConceptoOut, "description": "Concepto"}},
            summary="Un concepto con sus términos no preferentes, su nota de alcance y sus términos generales")
def concepto(concepto_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(ConceptoTesauro, concepto_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="El concepto no existe.")
    return tesauros.concepto_out(db, c)


class MateriaIn(BaseModel):
    fondo_id: uuid.UUID
    concepto_id: uuid.UUID


@router.post("/materias", responses={200: {"model": rt.MateriaOut, "description": "Materia del fondo"}},
             summary="La materia del fondo para un concepto (la existente o una nueva con el término preferente)")
def materia(datos: MateriaIn, actor: Actor = Depends(acceso_modulo("vocabularios")), db: Session = Depends(get_db)):
    fondo_o_404(db, datos.fondo_id)
    try:
        m = tesauros.materia_de_concepto(db, fondo_id=datos.fondo_id, concepto_id=datos.concepto_id, usuario_id=actor.id)
    except tesauros.ErrorTesauro as exc:
        raise _error(exc) from exc
    db.commit()
    return {"id": str(m.id), "nombre": m.nombre,
            "concepto": tesauros.concepto_out(db, db.get(ConceptoTesauro, m.concepto_tesauro_id))}
