"""
Cuadro de clasificación (CCD) y tabla de retención documental (TRD).

- Consultar el cuadro del fondo y descargar la plantilla: quien lee la descripción.
- Vista previa y validación: solo la administración; no crean nada. El cuadro
  se crea al aplicar una versión de la TRD (/api/trd) o al registrar el fondo.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from app.routers.archivos import leer_archivo

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
    contenido, nombre, _ = await leer_archivo(request, 3 * cuadro.MAX_BYTES)
    try:
        vista = await run_in_threadpool(cuadro.vista_previa, contenido, nombre)
    except cuadro.ErrorCuadro as exc:
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    # El archivo tal como llegó se guarda por su huella (requisito 3): al cargar, la versión lo cita.
    from app.servicios import versiones_trd

    original = await run_in_threadpool(versiones_trd.guardar_original, contenido, nombre)
    return {**vista, "original": {k: original[k] for k in ("huella", "archivo", "tamano")}}


@router.post("/lecturas", status_code=202, response_model=rc.LecturaCuadro,
             summary="Empezar a leer en segundo plano un CCD, una TRD o una TVD (uno o varios archivos en un .zip)")
async def empezar_lectura(request: Request, actor: Actor = Depends(solo_administrador)):
    """Como la vista previa, pero la lectura corre aparte: la pantalla consulta su avance
    (cuántos archivos van, cuántos faltan y cuál se lee) con GET /lecturas/{id}."""
    from app.servicios import lecturas_cuadro

    contenido, nombre, _ = await leer_archivo(request, 3 * cuadro.MAX_BYTES)
    if not contenido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El archivo está vacío.")
    return lecturas_cuadro.empezar(contenido, nombre, actor.id)


@router.get("/lecturas/{lectura_id}", response_model=rc.LecturaCuadro,
            summary="Avance de una lectura: archivos leídos, los que faltan y, al terminar, la vista previa")
def avance_lectura(lectura_id: str, actor: Actor = Depends(solo_administrador)):
    from app.servicios import lecturas_cuadro

    e = lecturas_cuadro.consultar(lectura_id, actor.id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Esa lectura ya no existe: vuelva a subir los archivos.")
    return e


class AplicarIn(BaseModel):
    fondo_id: uuid.UUID
    filas: list[dict] = Field(min_length=1, max_length=3000)


@router.post("/validar", response_model=rc.PruebaCuadro,
             summary="Validar en RiC-O 1.1 (OWL y SHACL) el cuadro confirmado, sin crear nada")
def validar(datos: AplicarIn, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, datos.fondo_id)
    try:
        informe, validacion = cuadro.probar_y_aplicar(db, fondo, datos.filas, actor.id, crear=False)
    except cuadro.ErrorCuadro as exc:
        db.rollback()
        raise HTTPException(exc.codigo, detail=str(exc)) from exc
    db.rollback()
    return {"creado": False, "informe": informe, "validacion": validacion}


class RenombrarIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=300)


@router.patch("/agrupaciones/{recurso_id}", response_model=rc.AgrupacionRenombrada,
              summary="Corregir el nombre de una sección, subsección, serie o subserie del cuadro")
def renombrar(recurso_id: uuid.UUID, datos: RenombrarIn, actor: Actor = Depends(solo_administrador),
              db: Session = Depends(get_db)):
    from app.models.recurso_documental import RecursoDocumental

    r = db.get(RecursoDocumental, recurso_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La agrupación no existe.")
    try:
        salida = cuadro.renombrar_agrupacion(db, r, datos.nombre, actor.id)
    except cuadro.ErrorRenombrar as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return salida
