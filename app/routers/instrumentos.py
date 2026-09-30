"""
Módulo 4 · Generación de instrumentos de descripción.

Catálogo navegable (cualquier rol con consulta del catálogo), inventario
FUID y guía (permiso de escritura en instrumentos) e índice. Solo lectura
del grafo; lo único que escribe es la auditoría de sus exportaciones y la
alerta de campos pendientes.
"""

import re
import unicodedata
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo, lectura_catalogo
from app.db.session import get_db
from app.models.recurso_documental import RecursoDocumental
from app.routers.fondos import fondo_o_404
from app.servicios import instrumentos
from app.servicios.auditoria import registrar

router = APIRouter(prefix="/api/instrumentos", tags=["Módulo 4 · Instrumentos"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class NivelIn(BaseModel):
    recurso_id: uuid.UUID


class GuiaIn(BaseModel):
    fondo_id: uuid.UUID


class GuiaExportarIn(BaseModel):
    fondo_id: uuid.UUID
    texto: str = Field(max_length=50_000)


def _recurso_o_404(db: Session, recurso_id: uuid.UUID) -> RecursoDocumental:
    r = db.get(RecursoDocumental, recurso_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La descripción no existe.")
    return r


def _error(exc: instrumentos.ErrorInstrumento) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


def _nombre_archivo(prefijo: str, titulo: str, extension: str) -> str:
    base = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")[:60] or "fondo"
    return f"{prefijo}_{base}.{extension}"


def _descarga(contenido: bytes, tipo: str, nombre: str, extra: dict | None = None) -> Response:
    return Response(contenido, media_type=tipo, headers={
        "Content-Disposition": f'attachment; filename="{nombre}"', **(extra or {})})


# --- Consulta ----------------------------------------------------------------------------------


@router.get("/catalogo", summary="Un nivel del árbol del fondo, para navegar por migas de pan")
def catalogo(fondo_id: uuid.UUID, nodo_id: uuid.UUID | None = None, _: Actor = Depends(lectura_catalogo),
             db: Session = Depends(get_db)):
    try:
        return instrumentos.nivel(db, fondo_o_404(db, fondo_id), nodo_id)
    except instrumentos.ErrorInstrumento as exc:
        raise _error(exc) from exc


@router.get("/catalogo/{recurso_id}", summary="Ficha de consulta: descripción, entidades y preservación")
def ficha(recurso_id: uuid.UUID, _: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    try:
        return instrumentos.ficha(db, _recurso_o_404(db, recurso_id))
    except instrumentos.ErrorInstrumento as exc:
        raise _error(exc) from exc


@router.get("/indice", summary="Índice de términos: vocabulario del fondo por tipo y en orden alfabético")
def indice(fondo_id: uuid.UUID, _: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    return instrumentos.indice(db, fondo_o_404(db, fondo_id))


# --- Inventario --------------------------------------------------------------------------------


def _inventario(db: Session, recurso_id: uuid.UUID) -> tuple[dict, dict | None]:
    try:
        datos = instrumentos.filas_inventario(db, _recurso_o_404(db, recurso_id))
    except instrumentos.ErrorInstrumento as exc:
        raise _error(exc) from exc
    alerta = instrumentos.alerta_pendientes(db, datos)
    return datos, alerta


@router.post("/inventario/vista-previa", summary="Arma el inventario FUID en pantalla y avisa los pendientes")
def vista_previa(datos: NivelIn, _: Actor = Depends(acceso_modulo("instrumentos")), db: Session = Depends(get_db)):
    inventario, alerta = _inventario(db, datos.recurso_id)
    db.commit()
    return {**inventario, "alerta": alerta}


@router.post("/inventario", summary="Genera y descarga el inventario FUID en hoja de cálculo")
def inventario(datos: NivelIn, request: Request, actor: Actor = Depends(acceso_modulo("instrumentos")),
               db: Session = Depends(get_db)):
    inventario, alerta = _inventario(db, datos.recurso_id)
    contenido = instrumentos.inventario_xlsx(inventario)
    registrar(db, modulo="instrumentos", accion="inventario_exportado", usuario_id=actor.id,
              entidad_tipo="recurso_documental", entidad_id=datos.recurso_id, request=request,
              nuevo={"renglones": len(inventario["filas"]), "pendientes": inventario["pendientes"]},
              detalle=f"Inventario de «{inventario['nivel']['titulo']}»")
    db.commit()
    return _descarga(contenido, XLSX, _nombre_archivo("Inventario", inventario["nivel"]["titulo"], "xlsx"), {
        "X-Campos-Pendientes": str(inventario["pendientes"]), "X-Alerta": "1" if alerta else "0"})


# --- Guía --------------------------------------------------------------------------------------


@router.post("/guia", summary="Borrador de la nota de presentación, redactado por el motor")
def guia(datos: GuiaIn, _: Actor = Depends(acceso_modulo("instrumentos")), db: Session = Depends(get_db)):
    return instrumentos.redactar_guia(db, fondo_o_404(db, datos.fondo_id))


@router.post("/guia/exportar", summary="Descarga la guía con el texto que dejó el archivista")
def guia_exportar(datos: GuiaExportarIn, request: Request, actor: Actor = Depends(acceso_modulo("instrumentos")),
                  db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, datos.fondo_id)
    if not datos.texto.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La nota de presentación está vacía.")
    contenido = instrumentos.guia_docx(db, fondo, datos.texto)
    registrar(db, modulo="instrumentos", accion="guia_exportada", usuario_id=actor.id, entidad_tipo="recurso_documental",
              entidad_id=fondo.id, request=request, nuevo={"caracteres": len(datos.texto)},
              detalle=f"Guía del fondo «{fondo.titulo}»")
    db.commit()
    return _descarga(contenido, DOCX, _nombre_archivo("Guia", fondo.titulo, "docx"))
