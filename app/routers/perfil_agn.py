"""
Perfil RiC-Col del AGN (Esquema de Metadatos v1.4) aplicado a RICORA.

Consulta del catálogo de correspondencias AGN ↔ RiC-CM 1.0 ↔ RiC-O 1.1 ↔
RICORA, con las erratas del esquema y la medición de calidad de metadatos
por descripción y por fondo. Solo lectura: vive en el módulo de
instrumentos, porque es el instrumento con que se mide la descripción.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo
from app.db.session import get_db
from app.models.recurso_documental import RecursoDocumental
from app.routers.fondos import fondo_o_404
from app.servicios import perfil_agn

router = APIRouter(prefix="/api/perfil-agn", tags=["Perfil AGN (RiC-Col)"])


@router.get("", summary="Catálogo AGN ↔ RiC-CM ↔ RiC-O ↔ RICORA, con fuentes, capas y erratas del esquema")
def catalogo(_: Actor = Depends(acceso_modulo("instrumentos"))):
    return perfil_agn.catalogo()


@router.get("/catalogo.xlsx", summary="El catálogo y las erratas en Excel")
def catalogo_xlsx(_: Actor = Depends(acceso_modulo("instrumentos"))):
    return Response(perfil_agn.catalogo_xlsx(), media_type="application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="perfil-agn-ric-col.xlsx"'})


@router.get("/calidad/{recurso_id}", summary="Calidad de metadatos de una descripción según el perfil del AGN")
def calidad(recurso_id: uuid.UUID, _: Actor = Depends(acceso_modulo("instrumentos")), db: Session = Depends(get_db)):
    recurso = db.get(RecursoDocumental, recurso_id)
    if recurso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La descripción no existe.")
    return perfil_agn.calidad(db, recurso)


@router.get("/fondos/{fondo_id}", summary="Indicadores de calidad del fondo según el perfil del AGN")
def calidad_fondo(fondo_id: uuid.UUID, _: Actor = Depends(acceso_modulo("instrumentos")),
                  db: Session = Depends(get_db)):
    return perfil_agn.calidad_fondo(db, fondo_o_404(db, fondo_id))
