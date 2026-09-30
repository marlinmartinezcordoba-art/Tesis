"""
Módulo 5 · Preservación digital.

Panel, ficha técnica, verificación de integridad y migración de formato
(permiso del módulo «preservacion»: consultar para ver, trabajar para
actuar). La configuración es solo del administrador.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.permisos import Actor, acceso_modulo, solo_administrador
from app.db.session import get_db
from app.models.preservacion import Migracion
from app.routers.fondos import fondo_o_404
from app.servicios import almacen, parametros, preservacion
from app.servicios.auditoria import ip_de

router = APIRouter(prefix="/api/preservacion", tags=["Módulo 5 · Preservación"])
modulo = acceso_modulo("preservacion")


class MigrarIn(BaseModel):
    destino: str = Field(max_length=40)
    # La aprobación es explícita: sin esta marca no se migra nada.
    aprobada: bool


class FilaFormato(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    origen: str = Field(min_length=1, max_length=80)
    origen_mime: list[str] = Field(min_length=1, max_length=20)
    destino: str
    conversor: str
    activo: bool


class ConfiguracionIO(BaseModel):
    frecuencia_dias: int
    formatos: list[FilaFormato]


def _error(exc: preservacion.ErrorPreservacion) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


def _inst(db: Session, inst_id: uuid.UUID):
    try:
        return preservacion.instanciacion_o_error(db, inst_id)
    except preservacion.ErrorPreservacion as exc:
        raise _error(exc) from exc


@router.get("/panel", summary="Resumen por nivel de riesgo e instanciaciones que requieren atención")
def panel(fondo_id: uuid.UUID, _: Actor = Depends(modulo), db: Session = Depends(get_db)):
    fondo_o_404(db, fondo_id)
    datos = preservacion.panel(db, fondo_id)
    db.commit()  # las alertas de riesgo que se hayan creado o cerrado al evaluar
    return datos


@router.get("/instanciacion/{inst_id}", summary="Ficha técnica, historial de verificaciones y de migraciones")
def detalle(inst_id: uuid.UUID, _: Actor = Depends(modulo), db: Session = Depends(get_db)):
    return preservacion.detalle(db, _inst(db, inst_id))


@router.post("/instanciacion/{inst_id}/verificar", summary="Verificar la integridad ahora")
def verificar(inst_id: uuid.UUID, request: Request, actor: Actor = Depends(modulo), db: Session = Depends(get_db)):
    inst = _inst(db, inst_id)
    v = preservacion.verificar(db, inst, origen="manual", usuario_id=actor.id, ip=ip_de(request))
    db.commit()
    return {"resultado": v.resultado, "fecha": v.fecha, "huella_registrada": v.huella_registrada,
            "huella_calculada": v.huella_calculada}


def _migracion_out(db: Session, m: Migracion) -> dict:
    return {"id": str(m.id), "estado": m.estado, "modo": m.modo, "destino": m.destino, "destino_nombre": m.destino_nombre,
            "mensaje": m.mensaje, "herramienta": m.herramienta,
            "nueva_instanciacion": preservacion.detalle(db, db.get(preservacion.Instanciacion, m.instanciacion_resultado_id))
            if m.instanciacion_resultado_id else None}


@router.post("/instanciacion/{inst_id}/migrar", summary="Aprobar la migración a un formato destino")
def migrar(inst_id: uuid.UUID, datos: MigrarIn, request: Request, actor: Actor = Depends(modulo),
           db: Session = Depends(get_db)):
    if not datos.aprobada:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="La migración necesita la aprobación explícita de la archivista.")
    inst = _inst(db, inst_id)
    try:
        m = preservacion.migrar(db, inst, datos.destino, actor.id, ip=ip_de(request))
    except preservacion.ErrorPreservacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _migracion_out(db, m)


@router.post("/instanciacion/{inst_id}/migrar/cargar", summary="Cargar el archivo convertido por fuera")
async def cargar(inst_id: uuid.UUID, request: Request, actor: Actor = Depends(modulo), db: Session = Depends(get_db)):
    # Como en la ingesta: el archivo se lee solo después de verificar sesión y permiso.
    formulario = await request.form(max_files=1)
    try:
        archivo = formulario.get("archivo")
        migracion_id = formulario.get("migracion_id")
        if not isinstance(archivo, StarletteUploadFile) or not migracion_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Falta el archivo o la migración.")
        return await run_in_threadpool(_cargar, db, request, actor, inst_id, str(migracion_id), archivo)
    finally:
        await formulario.close()


def _cargar(db: Session, request: Request, actor: Actor, inst_id: uuid.UUID, migracion_id: str,
            archivo: StarletteUploadFile) -> dict:
    try:
        m = db.get(Migracion, uuid.UUID(migracion_id))
    except ValueError:
        m = None
    if m is None or m.instanciacion_origen_id != inst_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Esa migración no existe para esta instanciación.")
    nombre = (archivo.filename or "convertido").replace("\\", "/").rsplit("/", 1)[-1][:500] or "convertido"
    try:
        preservacion.cargar_convertido(db, m, archivo.file, nombre, actor.id, ip=ip_de(request))
    except preservacion.ErrorPreservacion as exc:
        db.rollback()
        raise _error(exc) from exc
    db.commit()
    return _migracion_out(db, m)


# --- Configuración (solo administrador) ---------------------------------------------------------


def _configuracion(db: Session) -> dict:
    return {"frecuencia_dias": int(parametros.leer(db, "preservacion_frecuencia_dias")),
            "formatos": preservacion.formatos_soportados(db),
            "conversores": [{"clave": c.clave, "nombre": c.nombre, "destino": c.destino}
                            for c in preservacion.CONVERSORES.values()],
            "destinos": [{"clave": d.clave, "nombre": d.nombre} for d in preservacion.DESTINOS.values()],
            "herramientas": preservacion.herramientas_disponibles()}


@router.get("/configuracion", summary="Frecuencia de verificación y tabla de formatos soportados")
def ver_configuracion(_: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return _configuracion(db)


@router.put("/configuracion", summary="Cambiar la frecuencia y la tabla de formatos soportados")
def cambiar_configuracion(datos: ConfiguracionIO, request: Request, actor: Actor = Depends(solo_administrador),
                          db: Session = Depends(get_db)):
    try:
        parametros.cambiar(db, "preservacion_frecuencia_dias", datos.frecuencia_dias, actor.id, "preservacion",
                           ip=ip_de(request))
        parametros.cambiar(db, "preservacion_formatos", [f.model_dump() for f in datos.formatos], actor.id,
                           "preservacion", ip=ip_de(request))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return _configuracion(db)
