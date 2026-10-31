"""
Puesta en marcha del sistema (app/servicios/reinicio.py): dejar RICORA en blanco.

Solo para la administración, con contraseña y frase de confirmación. Antes de
borrar se hace un respaldo completo; si falla, no se borra nada.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
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
