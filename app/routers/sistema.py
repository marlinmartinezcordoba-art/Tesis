"""
Puesta en marcha del sistema (app/servicios/reinicio.py): dejar RICORA en blanco.

Solo para la administración, con contraseña y frase de confirmación. Antes de
borrar se hace un respaldo completo; si falla, no se borra nada.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permisos import Actor, solo_administrador
from app.db.session import get_db
from app.schemas.respuestas_sistema import InventarioReinicioOut, ReinicioOut
from app.servicios import reinicio

router = APIRouter(prefix="/api/sistema", tags=["Puesta en marcha"])


class ReinicioIn(BaseModel):
    contrasena: str = Field(min_length=1, max_length=200)
    frase: str = Field(min_length=1, max_length=100)
    incluir_tesauros: bool = False


@router.get("/reinicio", responses={200: {"model": InventarioReinicioOut, "description": "Inventario"}},
            summary="Qué se borraría y qué se conserva al dejar el sistema en blanco (no cambia nada)")
def ver_reinicio(_: Actor = Depends(solo_administrador), db: Session = Depends(get_db)):
    return reinicio.inventario(db)


@router.post("/reinicio", responses={200: {"model": ReinicioOut, "description": "Sistema en blanco"}},
             summary="Dejar el sistema en blanco: respaldo completo y después borrar todo lo cargado y descrito")
def reiniciar(datos: ReinicioIn, request: Request, actor: Actor = Depends(solo_administrador),
              db: Session = Depends(get_db)):
    try:
        return reinicio.reiniciar(db, actor.usuario, datos.contrasena, datos.frase, datos.incluir_tesauros)
    except reinicio.ReinicioRechazado as exc:
        db.rollback()
        raise HTTPException(exc.codigo, detail=exc.mensaje) from exc


@router.get("/reinicio/respaldos/{respaldo_id}/descargar",
            responses={200: {"content": {"application/octet-stream": {}},
                             "description": "Archivo del respaldo; su huella SHA-256 va en X-Huella-SHA256"}},
            summary="Descargar el respaldo hecho antes de dejar el sistema en blanco (administración)")
def descargar_respaldo(respaldo_id: uuid.UUID, request: Request, actor: Actor = Depends(solo_administrador),
                       db: Session = Depends(get_db)):
    # Con el módulo de preservación apagado, esta es la única forma de sacar del servidor el
    # respaldo de la puesta en marcha sin acceso técnico. Solo los de origen «reinicio».
    from app.models.preservacion import RespaldoBaseDatos
    from app.servicios import respaldo
    from app.servicios.auditoria import ip_de

    r = db.get(RespaldoBaseDatos, respaldo_id)
    if (r is None or r.origen != "reinicio" or r.estado != "correcto" or r.depurado_en is not None or not r.archivo
            or not Path(r.archivo).exists()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ese respaldo no está disponible en el servidor.")
    respaldo.registrar_descarga(db, r, actor.id, ip_de(request))
    db.commit()
    return FileResponse(r.archivo, filename=Path(r.archivo).name, media_type="application/octet-stream",
                        headers={"X-Huella-SHA256": r.huella or ""})
