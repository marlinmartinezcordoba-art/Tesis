"""
Cuadro de clasificación (CCD) y tabla de retención documental (TRD).

- Consultar el cuadro del fondo y descargar la plantilla: quien lee la descripción.
- Vista previa y aplicar (crear secciones, series, subseries y reglas): solo
  la administración. La vista previa no crea nada.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.permisos import Actor, acceso_modulo, solo_administrador
from app.db.session import get_db
from app.routers.fondos import fondo_o_404
from app.schemas import respuestas_cuadro as rc
from app.servicios import cuadro

router = APIRouter(prefix="/api/cuadro", tags=["Cuadro de clasificación y TRD"])


@router.get("", responses={200: {"model": list[rc.NodoCuadro], "description": "Cuadro de clasificación del fondo"}},
            summary="El cuadro de clasificación del fondo, con la retención de cada serie y subserie")
def arbol(fondo_id: uuid.UUID, actor: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    return cuadro.arbol(db, fondo_o_404(db, fondo_id))


@router.get("/plantilla", responses={200: {"content": {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}, "description": "Plantilla Excel del CCD y la TRD"}},
            summary="Descargar la plantilla Excel del cuadro de clasificación y la tabla de retención")
def plantilla(actor: Actor = Depends(acceso_modulo("descripcion"))):
    return Response(cuadro.plantilla_xlsx(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="plantilla-ccd-trd.xlsx"'})


@router.post("/vista-previa", responses={200: {"model": rc.VistaPreviaCuadro, "description": "Lo que se entendió"}},
             summary="Leer un CCD o una TRD (plantilla Excel, o TRD del AGN en Excel o PDF) sin crear nada")
async def vista_previa(request: Request, actor: Actor = Depends(solo_administrador)):
    formulario = await request.form(max_files=1)
    try:
        archivo = formulario.get("archivo")
        if not isinstance(archivo, StarletteUploadFile):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No llegó el archivo.")
        contenido = await archivo.read(cuadro.MAX_BYTES + 1)
        nombre = archivo.filename or ""
    finally:
        await formulario.close()
    try:
        return await run_in_threadpool(cuadro.vista_previa, contenido, nombre)
    except cuadro.ErrorCuadro as exc:
        raise HTTPException(exc.codigo, detail=str(exc)) from exc


class AplicarIn(BaseModel):
    fondo_id: uuid.UUID
    filas: list[dict] = Field(min_length=1, max_length=3000)


@router.post("/aplicar", responses={200: {"model": rc.InformeCuadro, "description": "Lo que se creó"}},
             summary="Crear el cuadro y las reglas de retención confirmados en la vista previa (todo o nada)")
def aplicar(datos: AplicarIn, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, datos.fondo_id)
    try:
        informe = cuadro.aplicar(db, fondo, datos.filas, actor.id)
    except cuadro.ErrorCuadro as exc:
        db.rollback()
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    db.commit()
    return informe
