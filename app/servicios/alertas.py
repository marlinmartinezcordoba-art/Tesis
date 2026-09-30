"""
Panel central de alertas: una sola función para crear alertas desde
cualquier módulo y una para atenderlas. Ningún módulo lleva su propia
lista de pendientes.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.alerta import Alerta


def crear(db: Session, *, tipo: str, severidad: str, modulo: str, entidad_tipo: str, entidad_id,
          mensaje: str, fondo_id: uuid.UUID | None = None, detalle: dict | None = None) -> Alerta:
    """Crea la alerta si no hay ya una pendiente del mismo tipo sobre la
    misma entidad (en ese caso devuelve la existente)."""
    existente = db.scalar(
        select(Alerta).where(Alerta.tipo == tipo, Alerta.entidad_id == str(entidad_id), Alerta.atendida_en.is_(None))
    )
    if existente is not None:
        return existente
    alerta = Alerta(tipo=tipo, severidad=severidad, modulo=modulo, entidad_tipo=entidad_tipo,
                    entidad_id=str(entidad_id), mensaje=mensaje, fondo_id=fondo_id, detalle=detalle)
    db.add(alerta)
    return alerta


def atender(db: Session, alerta: Alerta, usuario_id: uuid.UUID | None, nota: str | None = None) -> None:
    if alerta.atendida_en is None:
        alerta.atendida_en = ahora()
        alerta.atendida_por_id = usuario_id
        alerta.nota_atencion = nota
