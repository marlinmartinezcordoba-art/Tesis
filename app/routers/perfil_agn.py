"""
Completitud de la descripción según las reglas del Esquema de Metadatos
del AGN v1.4 (adaptación colombiana de RiC-CM), aplicadas como lógica del
sistema y no como un módulo aparte: la ficha de cada descripción muestra lo
que le falta y el resumen del fondo, cuántas están completas por nivel.

Las correspondencias AGN ↔ RiC-CM 1.0 ↔ RiC-O 1.1 ↔ RICORA y las erratas
del esquema se consultan por API (documentación y anexos de la tesis); no
tienen pantalla.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.permisos import Actor, acceso_modulo
from app.db.session import get_db
from app.models.recurso_documental import RecursoDocumental
from app.routers.fondos import fondo_o_404
from app.schemas import respuestas_perfil_agn as rp
from app.servicios import perfil_agn

router = APIRouter(prefix="/api/calidad", tags=["Completitud de la descripción (reglas del AGN)"])


@router.get("/correspondencias", responses={200: {"model": rp.CatalogoCorrespondencias, "description": "Correspondencias, resumen por estado y erratas del esquema"}},
             summary="Correspondencias AGN ↔ RiC-CM ↔ RiC-O ↔ RICORA, con fuentes, capas y erratas")
def catalogo(_: Actor = Depends(acceso_modulo("instrumentos"))):
    return perfil_agn.catalogo()


@router.get("/correspondencias.xlsx", responses={200: {"content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}, "description": "Libro de Excel con las correspondencias y las erratas"}},
             summary="Las correspondencias y las erratas en Excel")
def catalogo_xlsx(_: Actor = Depends(acceso_modulo("instrumentos"))):
    return Response(perfil_agn.catalogo_xlsx(), media_type="application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="perfil-agn-ric-col.xlsx"'})


@router.get("/descripciones/{recurso_id}", responses={200: {"model": rp.CalidadDescripcion, "description": "Criterios cumplidos y faltantes de la descripción"}},
             summary="Qué datos tiene y cuáles le faltan a una descripción, por nivel")
def calidad(recurso_id: uuid.UUID, _: Actor = Depends(acceso_modulo("descripcion")), db: Session = Depends(get_db)):
    recurso = db.get(RecursoDocumental, recurso_id)
    if recurso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="La descripción no existe.")
    return perfil_agn.calidad(db, recurso)


@router.get("/fondos/{fondo_id}", responses={200: {"model": rp.CalidadFondo, "description": "Completitud de las descripciones del fondo"}},
             summary="Completitud de las descripciones del fondo, por nivel")
def calidad_fondo(fondo_id: uuid.UUID, _: Actor = Depends(acceso_modulo("instrumentos")),
                  db: Session = Depends(get_db)):
    return perfil_agn.calidad_fondo(db, fondo_o_404(db, fondo_id))
