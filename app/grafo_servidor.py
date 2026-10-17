"""
Servicio del grafo RiC-O persistente (producción).

Un solo proceso abre el almacén Oxigraph en disco (RICORA_GRAFO_DIRECTORIO)
y lo sirve por HTTP, solo dentro de la red interna de Docker, a la web y al
trabajador, que se identifican con la ficha derivada de la clave del
sistema. Así nunca hay dos procesos escribiendo en el mismo almacén.

- PUT  /grafos?grafo=…   reemplaza un grafo con nombre (N-Triples), de una vez
- GET  /grafos?grafo=…   el grafo en N-Triples
- POST /consulta         SPARQL de lectura sobre un grafo
- GET  /estado           grafos y tripletas
"""

import hmac

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.config import settings
from app.servicios.grafo_rdf import CABECERA, Embebido, ErrorGrafo, ficha_servicio, validar_nombre

app = FastAPI(title="RICORA · grafo RiC-O", docs_url=None, redoc_url=None, openapi_url=None)
_almacen = Embebido(settings.grafo_directorio)


def autorizado(request: Request) -> None:
    if not hmac.compare_digest(request.headers.get(CABECERA, ""), ficha_servicio()):
        raise HTTPException(status_code=401, detail="Sin autorización.")


def _grafo(grafo: str) -> str:
    try:
        return validar_nombre(grafo)
    except ErrorGrafo as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/grafos", dependencies=[Depends(autorizado)])
async def reemplazar(grafo: str, request: Request):
    _almacen.reemplazar(_grafo(grafo), await request.body())
    return {"ok": True}


@app.get("/grafos", dependencies=[Depends(autorizado)])
def leer(grafo: str):
    return Response(_almacen.leer(_grafo(grafo)), media_type="application/n-triples")


class Consulta(BaseModel):
    grafo: str
    consulta: str
    maximo: int = 10_000


@app.post("/consulta", dependencies=[Depends(autorizado)])
def consultar(datos: Consulta):
    try:
        cuerpo, tipo = _almacen.consultar(_grafo(datos.grafo), datos.consulta, datos.maximo)
    except ErrorGrafo as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (SyntaxError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"La consulta no se pudo resolver: {exc}") from exc
    return Response(cuerpo, media_type=tipo)


@app.get("/estado", dependencies=[Depends(autorizado)])
def estado():
    return _almacen.estado()


@app.get("/salud")
def salud():
    return {"ok": True}
