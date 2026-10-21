"""Esquemas de respuesta (solo documentación OpenAPI) de la disposición final. Admiten campos adicionales."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class ElementoCalendario(BaseModel):
    """Un expediente (o documento de serie) con su regla, su vencimiento y su disposición."""
    model_config = ConfigDict(extra="allow")

    id: str
    nivel: str
    titulo: str
    codigo: str | None
    serie: str | None
    fechas: str | None
    regla: str | None
    disposicion: str | None
    disposicion_nombre: str | None
    vence: str | None
    cumplida: bool
    motivo: str | None
    ejecutada: dict[str, Any] | None


class ActividadDisposicion(BaseModel):
    """Una disposición ejecutada (rico:Activity)."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    tipo: str
    tipo_nombre: str
    fecha: str | None
    ejecutor: str | None
    elementos: int
    observaciones: str | None
