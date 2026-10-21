"""
Registro de un fondo (RiC-CM: Record Set de nivel fondo). Lo usan el asistente
de registro (desde el CCD y la TRD) y la importación de RiC-O: en los dos casos
el fondo nace junto con su cuadro de clasificación, nunca solo.
"""

import uuid

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental
from app.servicios import fechas
from app.servicios.auditoria import registrar


class ErrorFondo(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def crear(db: Session, *, titulo: str, fechas_extremas: str | None, nota: str | None, usuario_id: uuid.UUID,
          request: Request | None = None, origen: str | None = None) -> RecursoDocumental:
    titulo = " ".join((titulo or "").split())
    if len(titulo) < 3:
        raise ErrorFondo("El fondo necesita un nombre.")
    if db.scalar(select(RecursoDocumental.id).where(RecursoDocumental.nivel == "fondo",
                                                     func.lower(RecursoDocumental.titulo) == titulo.lower())):
        raise ErrorFondo("Ya existe un fondo con ese nombre.", 409)
    try:
        extremas = fechas.extremas(fechas_extremas)
    except fechas.FechaInvalida as exc:
        raise ErrorFondo(f"Fechas extremas: {exc} Escríbalas como «1930–1955» o «1930».") from exc
    fondo = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo=titulo,
                              fechas_extremas=(fechas_extremas or "").strip() or None,
                              fechas_extremas_edtf=extremas.edtf if extremas else None,
                              nota=(nota or "").strip() or None, creado_por_id=usuario_id)
    fondo.fondo_id = fondo.id
    db.add(fondo)
    db.flush()
    registrar(db, modulo="sistema", accion="fondo_registrado", usuario_id=usuario_id, entidad_tipo="recurso_documental",
              entidad_id=fondo.id, nuevo={"titulo": fondo.titulo, "fechas_extremas": fondo.fechas_extremas,
                                          **({"origen": origen} if origen else {})}, request=request)
    return fondo
