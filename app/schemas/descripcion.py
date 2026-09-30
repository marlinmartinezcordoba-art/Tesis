import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TipoEntidad = Literal["agente", "lugar", "fecha", "actividad", "forma_documental"]


class ElementoPorDescribir(BaseModel):
    id: uuid.UUID
    nombre: str
    tamano_bytes: int
    formato: str | None
    expediente: str | None
    origen_texto: str | None
    cargado_en: datetime
    en_edicion_por: str | None


class IniciarIn(BaseModel):
    instanciacion_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    nivel: Literal["expediente", "subserie", "serie"] | None = None


class VerificarIn(BaseModel):
    fondo_id: uuid.UUID
    tipo: Literal["agente", "lugar", "forma_documental"]
    valor: str = Field(min_length=1, max_length=300)


class CoincidenciaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    subtipo: str | None
    similitud: float
    conexiones: int


class EntidadIn(BaseModel):
    tipo: TipoEntidad
    valor: str = Field(max_length=300)
    subtipo: str | None = Field(default=None, max_length=40)
    rol: str | None = Field(default=None, max_length=40)
    fecha_normalizada: str | None = None
    fragmento: str | None = Field(default=None, max_length=500)
    documento_id: str | None = None
    inicio: int | None = None
    clave: str | None = None
    reutilizar_id: uuid.UUID | None = None
    crear_nueva: bool = False


class PublicarIn(BaseModel):
    trabajo_id: uuid.UUID
    titulo: str = Field(max_length=300)
    alcance_contenido: str = Field(default="", max_length=5000)
    incluido_en_id: uuid.UUID | None = None
    entidades: list[EntidadIn] = Field(default_factory=list, max_length=300)


class ControlIn(BaseModel):
    """Datos de control del inventario (FUID). Vacío = sin dato."""
    codigo_referencia: str | None = Field(default=None, max_length=60)
    caja: str | None = Field(default=None, max_length=30)
    carpeta: str | None = Field(default=None, max_length=30)
    folios: int | None = Field(default=None, ge=0, le=100000)
    soporte: str | None = Field(default=None, max_length=40)


class EditarIn(BaseModel):
    trabajo_id: uuid.UUID
    titulo: str | None = Field(default=None, max_length=300)
    alcance_contenido: str | None = Field(default=None, max_length=5000)
    incluido_en_id: uuid.UUID | None = None
    anular_relaciones: list[uuid.UUID] = Field(default_factory=list)
    quitar_forma_documental: bool = False
    agregar_entidades: list[EntidadIn] = Field(default_factory=list, max_length=100)
    control: ControlIn | None = None


class NivelSuperiorOut(BaseModel):
    id: uuid.UUID
    titulo: str
    nivel: str


class PublicadaOut(BaseModel):
    id: uuid.UUID
    titulo: str
    nivel: str
    documentos: int
    publicado_en: datetime | None
    actualizado_en: datetime | None
    en_edicion_por: str | None
