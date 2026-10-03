"""
Exportación del fondo en RiC-O 1.1 (RDF), reporte de conformidad y
resolución de las URI de cada nodo (/id/…).

- `GET /api/exportacion/rdf`: el fondo en Turtle o JSON-LD.
- `GET /api/exportacion/conformidad`: validación contra el OWL oficial y el
  perfil SHACL del sistema.
- `GET` y `PUT /api/exportacion/uris-publicas`: si /id/… se resuelve sin
  sesión (solo administrador; apagado por defecto).
- `GET /id/{uuid}[.ttl|.jsonld]`: la descripción RDF de un nodo, con
  negociación de contenido. Sin sesión, solo si el administrador lo
  encendió, y nunca lo clasificado o reservado.
"""

import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from rdflib import RDF, URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permisos import Actor, lectura_catalogo, solo_administrador, usuario_actual
from app.db.session import get_db
from app.models.descripcion import EntidadVocabulario, Fecha, Hito, Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.routers.fondos import fondo_o_404
from app.servicios import alertas, conformidad_rico, exportacion_rico, parametros
from app.servicios.auditoria import ip_de, registrar

router = APIRouter(prefix="/api/exportacion", tags=["Exportación RiC-O"])
uris = APIRouter(tags=["Exportación RiC-O"])


def _exportacion(db: Session, actor: Actor, fondo_id: uuid.UUID, incluir_restringidos: bool):
    fondo = fondo_o_404(db, fondo_id)
    if incluir_restringidos and not actor.puede("catalogo", "escribir"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Incluir lo clasificado o reservado exige permiso de "
                                                              "escritura en el catálogo.")
    return fondo, exportacion_rico.exportar(db, fondo, incluir_restringidos)


@router.get("/rdf", summary="El fondo en RiC-O 1.1 (Turtle o JSON-LD)")
def rdf(request: Request, fondo_id: uuid.UUID, formato: Literal["turtle", "jsonld"] = "turtle",
        incluir_restringidos: bool = False, actor: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    fondo, ex = _exportacion(db, actor, fondo_id, incluir_restringidos)
    cuerpo = exportacion_rico.serializar(ex.grafo, formato)
    _, tipo, extension = exportacion_rico.FORMATOS[formato]
    # Cada descarga completa se valida (OWL y SHACL) y el resultado queda en la
    # auditoría (hallazgo O-32). No se niega la descarga: los datos son de la
    # entidad; se marca y se avisa a la administración para corregir el defecto.
    owl = conformidad_rico.verificar_owl(ex.grafo)
    shacl = conformidad_rico.validar_shacl(ex.grafo)
    conforme = not owl and shacl["conforme"]
    registrar(db, modulo="instrumentos", accion="rdf_exportado", usuario_id=actor.id, entidad_tipo="recurso_documental",
              entidad_id=fondo.id, ip=ip_de(request), detalle=fondo.titulo,
              nuevo={"formato": formato, "incluir_restringidos": incluir_restringidos, "conforme": conforme,
                     "problemas_owl": len(owl), "resultados_shacl": len(shacl["resultados"]), **ex.resumen()})
    if not conforme:
        alertas.crear(db, tipo="exportacion_no_conforme", severidad="media", modulo="instrumentos",
                      entidad_tipo="recurso_documental", entidad_id=fondo.id, fondo_id=fondo.id,
                      mensaje=f"La exportación RiC-O de «{fondo.titulo}» no pasó la validación: "
                              f"{len(owl)} problemas OWL y {len(shacl['resultados'])} resultados SHACL. "
                              "Revise el reporte de conformidad.",
                      detalle={"owl": owl[:20], "shacl": shacl["resultados"][:20]})
    db.commit()
    nombre = re.sub(r"[^A-Za-z0-9_-]+", "-", fondo.titulo).strip("-")[:60] or "fondo"
    return Response(cuerpo, media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="ricora-rico-{nombre}.{extension}"',
                             "X-RICORA-Conformidad": "conforme" if conforme else "no-conforme"})


@router.get("/conformidad", summary="Conformidad de la exportación con RiC-O 1.1 (OWL y SHACL)")
def conformidad(request: Request, fondo_id: uuid.UUID, incluir_restringidos: bool = False,
                actor: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    fondo, ex = _exportacion(db, actor, fondo_id, incluir_restringidos)
    reporte = conformidad_rico.reporte(ex)
    registrar(db, modulo="instrumentos", accion="conformidad_rico_validada", usuario_id=actor.id,
              entidad_tipo="recurso_documental", entidad_id=fondo.id, ip=ip_de(request), detalle=fondo.titulo,
              nuevo={"conforme": reporte["conforme"], "problemas_owl": len(reporte["owl"]["problemas"]),
                     "resultados_shacl": len(reporte["shacl"]["resultados"]), "tripletas": reporte["tripletas"]})
    db.commit()
    return reporte | {"fondo": {"id": str(fondo.id), "titulo": fondo.titulo},
                      "uri_fondo": str(exportacion_rico.uri(fondo.id)),
                      "uris_publicas": bool(parametros.leer(db, "rdf_uris_publicas"))}


class UrisPublicasIO(BaseModel):
    publicas: bool


@router.get("/uris-publicas", summary="¿Se resuelven las URI sin sesión?")
def ver_uris(_: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)) -> UrisPublicasIO:
    return UrisPublicasIO(publicas=bool(parametros.leer(db, "rdf_uris_publicas")))


@router.put("/uris-publicas", summary="Encender o apagar la resolución sin sesión (solo administrador)")
def cambiar_uris(datos: UrisPublicasIO, request: Request, actor: Actor = Depends(solo_administrador),
                 db: Session = Depends(get_db)) -> UrisPublicasIO:
    parametros.cambiar(db, "rdf_uris_publicas", datos.publicas, actor.id, "instrumentos", ip=ip_de(request))
    db.commit()
    return datos


# --- Resolución de URI ----------------------------------------------------------------------------

_UUID = re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)


def _fondo_de(db: Session, ident: uuid.UUID) -> uuid.UUID | None:
    r = db.get(RecursoDocumental, ident)
    if r is not None:
        return r.fondo_id or r.id
    for modelo in (EntidadVocabulario, Instanciacion, Hito):
        fila = db.get(modelo, ident)
        if fila is not None:
            return fila.fondo_id
    if db.get(Fecha, ident) is not None:
        for tipo, otro in db.execute(select(Relacion.origen_tipo, Relacion.origen_id).where(Relacion.destino_id == ident)
                                     .union_all(select(Relacion.destino_tipo, Relacion.destino_id)
                                                .where(Relacion.origen_id == ident))).all():
            if tipo != "fecha":
                return _fondo_de(db, otro)
    return None


def _formato(ruta: str, aceptar: str) -> tuple[str, str]:
    """(ruta sin extensión, formato). La extensión manda; si no hay, la
    cabecera Accept; por defecto, Turtle."""
    for formato, (_, _, extension) in exportacion_rico.FORMATOS.items():
        if ruta.endswith("." + extension):
            return ruta[: -len(extension) - 1], formato
    if "application/ld+json" in aceptar or "application/json" in aceptar:
        return ruta, "jsonld"
    return ruta, "turtle"


def _actor_si_hay(request: Request, db: Session = Depends(get_db)) -> Actor | None:
    try:
        from fastapi.security.utils import get_authorization_scheme_param

        esquema, valor = get_authorization_scheme_param(request.headers.get("Authorization"))
        if not valor:
            return None
        from fastapi.security import HTTPAuthorizationCredentials

        return usuario_actual(request, HTTPAuthorizationCredentials(scheme=esquema, credentials=valor), db)
    except HTTPException:
        return None


@uris.get("/id/{ruta:path}", summary="Descripción RDF de un nodo (URI de RiC-O)", include_in_schema=True)
def resolver(ruta: str, request: Request, db: Session = Depends(get_db), actor: Actor | None = Depends(_actor_si_hay)):
    if actor is None and not parametros.leer(db, "rdf_uris_publicas"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="no_autenticado", headers={"WWW-Authenticate": "Bearer"})
    if actor is not None and not actor.puede("catalogo"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Su rol no tiene permiso para esta acción.")
    pedida = ruta.strip("/")
    ruta, formato = _formato(pedida, request.headers.get("accept", ""))
    m = _UUID.match(ruta)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe.")
    # Una entidad fusionada conserva su URI: redirige, para siempre, a la definitiva.
    absorbida = db.get(EntidadVocabulario, uuid.UUID(m.group(1)))
    if absorbida is not None and absorbida.estado == "fusionada" and absorbida.fusionada_en_id:
        from fastapi.responses import RedirectResponse

        resto = pedida[len(m.group(1)):]  # con su extensión, si la traía
        return RedirectResponse(f"/id/{absorbida.fusionada_en_id}{resto}", status_code=status.HTTP_301_MOVED_PERMANENTLY)
    fondo_id = _fondo_de(db, uuid.UUID(m.group(1)))
    fondo = db.get(RecursoDocumental, fondo_id) if fondo_id else None
    if fondo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe.")
    # Ni con sesión se resuelve aquí lo clasificado o reservado: para eso
    # está la exportación completa, con permiso y con registro.
    ex = exportacion_rico.exportar(db, fondo, incluir_restringidos=False)
    nodo = URIRef(exportacion_rico.base() + ruta)
    if (nodo, RDF.type, None) not in ex.grafo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe o no es público.")
    cuerpo = exportacion_rico.serializar(exportacion_rico.descripcion_de(ex, nodo), formato)
    return Response(cuerpo, media_type=exportacion_rico.FORMATOS[formato][1], headers={"Vary": "Accept, Authorization"})
