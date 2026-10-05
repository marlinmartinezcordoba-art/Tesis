"""
Grafo de contexto del fondo (vista Grafo de Instrumentos).

Solo lectura: devuelve el subgrafo RiC alrededor de una entidad raíz,
acotado a 1–3 saltos y a los filtros del panel; la ficha de una entidad y
sus relaciones; y la exportación RiC-O del fragmento visible. Lo único que
escribe es la auditoría de esa exportación.

Quien no tiene sesión de archivista (escritura en descripción o en el
catálogo; en la práctica, el rol de consulta) no ve lo clasificado ni lo
reservado: la misma función de visibilidad de la exportación RiC-O.
"""

import re
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.permisos import Actor, lectura_catalogo
from app.db.session import get_db
from app.routers.fondos import fondo_o_404
from app.schemas import respuestas_grafo as rg
from app.servicios import exportacion_rico, grafo
from app.servicios.auditoria import ip_de, registrar
from app.servicios.instrumentos import ErrorInstrumento

router = APIRouter(prefix="/api/grafo", tags=["Grafo de contexto"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _ver_restringidos(actor: Actor) -> bool:
    """Sesión de archivista: quien describe o escribe en el catálogo ve lo
    clasificado o reservado; el rol de consulta, no."""
    return actor.puede("descripcion", "escribir") or actor.puede("catalogo", "escribir")


def _filtros(tipo_entidad: list[str] = Query(default=[]), tipo_relacion: list[str] = Query(default=[]),
             fecha_desde: date | None = None, fecha_hasta: date | None = None,
             estado: list[str] = Query(default=[])) -> grafo.Filtros:
    desconocidas = set(tipo_entidad) - set(grafo.FAMILIAS)
    if desconocidas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Tipo de entidad desconocido: {', '.join(sorted(desconocidas))}.")
    if set(estado) - set(grafo.ESTADOS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Estado desconocido.")
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La fecha inicial es posterior a la final.")
    return grafo.Filtros(set(tipo_entidad), set(tipo_relacion), fecha_desde, fecha_hasta, set(estado))


def _fondo(db: Session, tipo: str, ident: uuid.UUID, fondo_id: uuid.UUID | None):
    if fondo_id is None:
        fondo_id = grafo.fondo_de(db, tipo, ident)
        if fondo_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND if tipo != "fecha" else status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Indique el fondo." if tipo == "fecha" else "Esa entidad no existe.")
    return fondo_o_404(db, fondo_id)


def _error(exc: ErrorInstrumento) -> HTTPException:
    return HTTPException(exc.codigo, detail=str(exc))


@router.get("/opciones", responses={200: {"model": rg.OpcionesGrafo, "description": "Opciones de filtro y entidades raíz posibles"}},
             summary="Opciones del panel de filtros y entidades que pueden ser raíz")
def opciones(fondo_id: uuid.UUID, actor: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    return grafo.opciones(db, fondo_o_404(db, fondo_id), _ver_restringidos(actor))


@router.get("/{tipo}/{ident}", responses={200: {"model": rg.Subgrafo, "description": "Nodos y relaciones del subgrafo"}},
             summary="Subgrafo acotado alrededor de una entidad raíz (1 a 3 saltos, con filtros)")
def subgrafo(tipo: str, ident: uuid.UUID, fondo_id: uuid.UUID | None = None, saltos: int = Query(1, ge=1, le=3),
             filtros: grafo.Filtros = Depends(_filtros), actor: Actor = Depends(lectura_catalogo),
             db: Session = Depends(get_db)):
    try:
        return grafo.subgrafo(db, _fondo(db, tipo, ident, fondo_id), tipo, ident, saltos, filtros, _ver_restringidos(actor))
    except ErrorInstrumento as exc:
        raise _error(exc) from exc


@router.get("/{tipo}/{ident}/ficha", responses={200: {"model": rg.FichaGrafo, "description": "Ficha de la entidad seleccionada"}},
             summary="Resumen, atributos y relaciones de la entidad seleccionada")
def ficha(tipo: str, ident: uuid.UUID, fondo_id: uuid.UUID | None = None, actor: Actor = Depends(lectura_catalogo),
          db: Session = Depends(get_db)):
    try:
        return grafo.ficha(db, _fondo(db, tipo, ident, fondo_id), tipo, ident, _ver_restringidos(actor))
    except ErrorInstrumento as exc:
        raise _error(exc) from exc


@router.get("/{tipo}/{ident}/relaciones/exportar", responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}, "description": "Libro de Excel con todas las relaciones de la entidad"}},
             summary="Todas las relaciones de la entidad, en Excel")
def relaciones_excel(tipo: str, ident: uuid.UUID, fondo_id: uuid.UUID | None = None,
                     actor: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    try:
        contenido = grafo.hoja_relaciones(db, _fondo(db, tipo, ident, fondo_id), tipo, ident, _ver_restringidos(actor))
    except ErrorInstrumento as exc:
        raise _error(exc) from exc
    return Response(contenido, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="relaciones-{ident}.xlsx"'})


@router.get("/{tipo}/{ident}/exportar", responses={200: {"content": {"text/turtle": {}, "application/ld+json": {}}, "description": "Fragmento del grafo en RiC-O (Turtle o JSON-LD)"}},
             summary="El fragmento visible del grafo en RiC-O (Turtle o JSON-LD); GET como toda consulta")
def exportar(request: Request, tipo: str, ident: uuid.UUID, fondo_id: uuid.UUID | None = None,
             saltos: int = Query(1, ge=1, le=3), formato: Literal["turtle", "jsonld"] = "turtle",
             filtros: grafo.Filtros = Depends(_filtros), actor: Actor = Depends(lectura_catalogo),
             db: Session = Depends(get_db)):
    fondo = _fondo(db, tipo, ident, fondo_id)
    try:
        g, datos = grafo.exportar_fragmento(db, fondo, tipo, ident, saltos, filtros, _ver_restringidos(actor))
    except ErrorInstrumento as exc:
        raise _error(exc) from exc
    _, media, extension = exportacion_rico.FORMATOS[formato]
    registrar(db, modulo="instrumentos", accion="grafo_exportado", usuario_id=actor.id, entidad_tipo=tipo,
              entidad_id=ident, ip=ip_de(request), detalle=fondo.titulo,
              nuevo={"formato": formato, "saltos": datos["saltos"], "filtros": filtros.describir(),
                     "nodos": len(datos["nodos"]), "relaciones": len(datos["aristas"]), "tripletas": len(g)})
    db.commit()
    raiz = next(n for n in datos["nodos"] if n["clave"] == datos["centro"])
    nombre = re.sub(r"[^A-Za-z0-9_-]+", "-", raiz["etiqueta"]).strip("-")[:40] or "entidad"
    archivo = f"ricora-fragmento-{nombre}-{datos['saltos']}-saltos-{re.sub(r'[^A-Za-z0-9_-]+', '-', filtros.describir())[:80]}.{extension}"
    return Response(exportacion_rico.serializar(g, formato), media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{archivo}"'})
