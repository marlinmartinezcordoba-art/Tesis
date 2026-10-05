"""
Buscador unificado (RF-SEARCH-001 y RF-SEARCH-002): texto completo de la
descripción y de los archivos, identificadores y autoridades, en una sola
ruta. Exige sesión con lectura del catálogo y aplica la reserva de la Ley
1712 según el rol (ver app/servicios/busqueda.py).

No se registra en la auditoría lo que cada persona busca: el texto buscado
puede contener datos personales de terceros (Ley 1581) y no es una acción
sobre el archivo.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.permisos import Actor, lectura_catalogo
from app.db.session import get_db
from app.models.recurso_documental import NIVEL_DESCRIPCION
from app.routers.instrumentos import ve_restringidos
from app.schemas.respuestas_sistema import ResultadoBusquedaOut
from app.servicios import busqueda

router = APIRouter(prefix="/api/buscar", tags=["Búsqueda"])


@router.get("", responses={200: {"model": ResultadoBusquedaOut, "description": "Resultados paginados con sus facetas"}},
            summary="Buscar en descripciones, texto de los documentos, identificadores y autoridades")
def buscar(q: str = Query(..., min_length=2, max_length=busqueda.LARGO_MAXIMO),
           fondo_id: uuid.UUID | None = None,
           alcance: Literal["todo", "descripcion", "texto", "autoridades"] = "todo",
           nivel: Literal[NIVEL_DESCRIPCION] | None = None,  # type: ignore[valid-type]
           desde: int | None = Query(None, ge=1, le=2999), hasta: int | None = Query(None, ge=1, le=2999),
           agente_id: uuid.UUID | None = None,
           pagina: int = Query(1, ge=1, le=500),
           actor: Actor = Depends(lectura_catalogo), db: Session = Depends(get_db)):
    try:
        return busqueda.buscar(db, q, ver_restringidos=ve_restringidos(actor), fondo_id=fondo_id, alcance=alcance,
                               nivel=nivel, desde=desde, hasta=hasta, agente_id=agente_id, pagina=pagina)
    except busqueda.ErrorBusqueda as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
