"""
Datos abiertos del fondo (hallazgos INS-01, INS-04, INS-05 e INS-08).

Todo lo de aquí sirve solo el subconjunto público: lo publicado, sin lo
clasificado ni lo reservado (la reserva vencida ya es pública, Ley 1712,
art. 22). Sin sesión responde solo si el administrador encendió la
publicación (`rdf_uris_publicas`, apagada por defecto, decisión INS-01); con
sesión de lectura del catálogo responde siempre, con el mismo filtro.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.permisos import Actor
from app.db.session import get_db
from app.models.descripcion import EntidadVocabulario
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.routers.exportacion import _actor_si_hay
from app.routers.fondos import fondo_o_404
from app.servicios import conformidad_rico, derechos, exportacion_rico, intercambio, ley1712, parametros, sparql
from app.servicios.auditoria import ip_de, registrar

router = APIRouter(prefix="/api/publico", tags=["Datos abiertos"])


def acceso_publico(request: Request, db: Session = Depends(get_db),
                   actor: Actor | None = Depends(_actor_si_hay)) -> Actor | None:
    if actor is not None:
        if not actor.puede("catalogo"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Su rol no tiene permiso para esta acción.")
        return actor
    if not parametros.leer(db, "rdf_uris_publicas"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="no_autenticado", headers={"WWW-Authenticate": "Bearer"})
    return None


def _visibles(db: Session, fondo: RecursoDocumental):
    from app.servicios import instrumentos

    return instrumentos.arbol(db, fondo, ver_restringidos=False)


@router.get("/rdf", summary="El subconjunto público del fondo en RiC-O (Turtle o JSON-LD), sin sesión si está encendido")
def rdf(request: Request, fondo_id: uuid.UUID, formato: Literal["turtle", "jsonld"] = "turtle",
        actor: Actor | None = Depends(acceso_publico), db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, fondo_id)
    ex = exportacion_rico.exportar(db, fondo, incluir_restringidos=False)
    conforme = not conformidad_rico.verificar_owl(ex.grafo) and conformidad_rico.validar_shacl(ex.grafo)["conforme"]
    registrar(db, modulo="instrumentos", accion="rdf_publico_descargado", usuario_id=actor.id if actor else None,
              entidad_tipo="recurso_documental", entidad_id=fondo.id, ip=ip_de(request), detalle=fondo.titulo,
              nuevo={"formato": formato, "conforme": conforme, "sin_sesion": actor is None, **ex.resumen()})
    db.commit()
    _, tipo, extension = exportacion_rico.FORMATOS[formato]
    return Response(exportacion_rico.serializar(ex.grafo, formato), media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="ricora-publico-{fondo.id}.{extension}"',
                             "X-RICORA-Conformidad": "conforme" if conforme else "no-conforme",
                             "Vary": "Authorization"})


@router.api_route("/sparql", methods=["GET", "POST"],
                  summary="SPARQL de solo lectura sobre el subconjunto público de un fondo")
async def consulta_sparql(request: Request, fondo_id: uuid.UUID, query: str | None = None,
                          actor: Actor | None = Depends(acceso_publico), db: Session = Depends(get_db)):
    if request.method == "POST":
        tipo = request.headers.get("content-type", "")
        if tipo.startswith("application/sparql-query"):
            query = (await request.body()).decode("utf-8", "replace")
        else:
            query = (await request.form()).get("query") or query
    fondo = fondo_o_404(db, fondo_id)
    ex = exportacion_rico.exportar(db, fondo, incluir_restringidos=False)
    try:
        cuerpo, tipo = sparql.consultar(ex.grafo, query or "")
    except sparql.ErrorSparql as exc:
        return JSONResponse({"detail": str(exc)}, status_code=exc.codigo)
    return Response(cuerpo, media_type=tipo, headers={"Vary": "Authorization"})


@router.get("/ead3", summary="El fondo en EAD3 (solo lo público), validado contra el esquema oficial")
def ead3(request: Request, fondo_id: uuid.UUID, actor: Actor | None = Depends(acceso_publico),
         db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, fondo_id)
    try:
        xml = intercambio.ead3(db, fondo)
    except intercambio.ErrorIntercambio as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    registrar(db, modulo="instrumentos", accion="ead3_exportado", usuario_id=actor.id if actor else None,
              entidad_tipo="recurso_documental", entidad_id=fondo.id, ip=ip_de(request), detalle=fondo.titulo)
    db.commit()
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="ead3-{fondo.id}.xml"'})


@router.get("/eac/{entidad_id}", summary="Ficha de autoridad en EAC-CPF 2.0, validada contra el esquema oficial")
def eac(entidad_id: uuid.UUID, request: Request, actor: Actor | None = Depends(acceso_publico),
        db: Session = Depends(get_db)):
    e = db.get(EntidadVocabulario, entidad_id)
    if e is None or e.estado != "activa":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe.")
    fondo = db.get(RecursoDocumental, e.fondo_id)
    # Una autoridad que solo conocen documentos reservados tampoco es pública (INS-02).
    if e.id in exportacion_rico._entidades_vedadas(db, fondo, _visibles(db, fondo).nodos):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe o no es pública.")
    try:
        xml = intercambio.eac_cpf(db, e)
    except intercambio.ErrorIntercambio as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="eac-cpf-{e.id}.xml"'})


@router.get("/ley1712", summary="Índice de información clasificada y reservada (Ley 1712, art. 20)")
def indice_reservada(fondo_id: uuid.UUID, formato: Literal["json", "xlsx"] = "json",
                     actor: Actor | None = Depends(acceso_publico), db: Session = Depends(get_db)):
    fondo = fondo_o_404(db, fondo_id)
    filas = ley1712.indice(db, fondo)
    if formato == "xlsx":
        return Response(ley1712.xlsx(fondo, filas),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="indice-ley1712-{fondo.id}.xlsx"'})
    return {"fondo": fondo.titulo, "columnas": [{"clave": c, "nombre": n} for c, n in ley1712.COLUMNAS], "filas": filas}


# --- IIIF Presentation 3.0 ------------------------------------------------------------------------


def _recurso_publico(db: Session, recurso_id: uuid.UUID) -> RecursoDocumental:
    r = db.get(RecursoDocumental, recurso_id)
    if r is None or r.publicado_en is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe.")
    fondo = db.get(RecursoDocumental, r.fondo_id)
    if r.id not in _visibles(db, fondo).nodos:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe o no es público.")
    return r


@router.get("/iiif/{recurso_id}/manifest", summary="Manifiesto IIIF Presentation 3.0 de una descripción pública")
def manifiesto(recurso_id: uuid.UUID, actor: Actor | None = Depends(acceso_publico), db: Session = Depends(get_db)):
    r = _recurso_publico(db, recurso_id)
    base = exportacion_rico.base().removesuffix("/id/")
    return JSONResponse(intercambio.manifiesto_iiif(db, r, base),
                        media_type='application/ld+json;profile="http://iiif.io/api/presentation/3/context.json"',
                        headers={"Access-Control-Allow-Origin": "*"})


@router.get("/iiif/imagen/{instanciacion_id}/{pagina}.png", summary="Una página pública (PNG) para el manifiesto IIIF")
def imagen(instanciacion_id: uuid.UUID, pagina: int, actor: Actor | None = Depends(acceso_publico),
           db: Session = Depends(get_db)):
    from app.servicios import recorte

    inst = db.get(Instanciacion, instanciacion_id)
    if inst is None or derechos.instanciacion_restringida(db, inst):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe o no es pública.")
    if not any(_es_publico(db, r) for r in derechos.recursos_de(db, inst)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe o no es pública.")
    try:
        contenido = recorte.pagina_png(inst, pagina)
    except (recorte.ErrorRecorte, OSError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Página no disponible.") from exc
    return Response(contenido, media_type="image/png",
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=3600"})


def _es_publico(db: Session, r: RecursoDocumental) -> bool:
    if r.publicado_en is None:
        return False
    return r.id in _visibles(db, db.get(RecursoDocumental, r.fondo_id)).nodos
