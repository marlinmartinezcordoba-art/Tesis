"""
Importar un fondo descrito en RiC-O 1.1 desde otro sistema. Solo la
administración: registra un fondo con su cuadro. La vista previa no crea nada;
importar valida contra la ontología y el perfil SHACL y crea todo o nada.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.permisos import Actor, solo_administrador
from app.db.session import get_db
from app.schemas.respuestas_importacion import ImportacionRico, VistaPreviaRico
from app.servicios import importacion_rico

router = APIRouter(prefix="/api/importacion", tags=["Importar RiC-O"])


async def _archivo(request: Request) -> tuple[bytes, str, dict]:
    formulario = await request.form()
    archivo = formulario.get("archivo")
    if not isinstance(archivo, StarletteUploadFile):
        raise HTTPException(422, detail="Adjunte el archivo RiC-O.")
    contenido = await archivo.read(importacion_rico.MAX_BYTES + 1)
    datos = {k: v for k, v in formulario.items() if isinstance(v, str)}
    return contenido, archivo.filename or "archivo", datos


def _seccion(datos: dict) -> dict | None:
    nombre, codigo = (datos.get("seccion_nombre") or "").strip(), (datos.get("seccion_codigo") or "").strip()
    return {"codigo": codigo or None, "nombre": nombre} if nombre else None


def _error(exc: importacion_rico.ErrorImportacion) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


@router.post("/rico/vista-previa", response_model=VistaPreviaRico,
             summary="Leer un fondo en RiC-O (Turtle, RDF/XML, JSON-LD o N-Triples) y decir qué se importaría, sin crear nada")
async def vista_previa(request: Request, _: Actor = Depends(solo_administrador)):
    contenido, nombre, datos = await _archivo(request)
    try:
        return await run_in_threadpool(importacion_rico.vista_previa, contenido, nombre, _seccion(datos))
    except importacion_rico.ErrorImportacion as exc:
        raise _error(exc) from exc


def _fecha(valor: str | None) -> date | None:
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError as exc:
        raise HTTPException(422, detail=f"Fecha no válida: «{valor}» (use AAAA-MM-DD).") from exc


@router.post("/rico", response_model=ImportacionRico,
             summary="Importar el fondo: cuadro por la parametrización de la TRD, vocabulario, expedientes, documentos y "
                     "relaciones; validado en RiC-O 1.1 (todo o nada)")
async def importar(request: Request, actor: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    contenido, nombre, datos = await _archivo(request)
    version = {"acto_aprobacion": (datos.get("acto_aprobacion") or "").strip() or None,
               "fecha_aprobacion": _fecha(datos.get("fecha_aprobacion")),
               "vigente_desde": _fecha(datos.get("vigente_desde"))}
    try:
        salida = importacion_rico.importar(db, contenido, nombre, actor.id, titulo=(datos.get("titulo") or "").strip() or None,
                                           version=version, seccion=_seccion(datos), crear=datos.get("crear") in ("1", "true", "si"))
    except importacion_rico.ErrorImportacion as exc:
        db.rollback()
        raise _error(exc) from exc
    if salida["creado"]:
        db.commit()
    else:
        db.rollback()
    return salida
