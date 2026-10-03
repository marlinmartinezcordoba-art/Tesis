import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class FondoOut(BaseModel):
    id: uuid.UUID
    titulo: str
    fechas_extremas: str | None
    documentos: int


class FondoIn(BaseModel):
    titulo: str = Field(max_length=300)
    fechas_extremas: str | None = Field(default=None, max_length=60)
    nota: str | None = Field(default=None, max_length=2000)

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("Escriba el nombre del fondo.")
        return v


class ExpedienteOut(BaseModel):
    id: uuid.UUID
    titulo: str
    fechas_extremas: str | None


class LimiteOut(BaseModel):
    limite_mb: int
    limite_bytes: int


class LimiteIn(BaseModel):
    limite_mb: int


class UmbralOcrOut(BaseModel):
    umbral: int


class UmbralOcrIn(BaseModel):
    umbral: int = Field(ge=0, le=100)


class ResultadoCarga(BaseModel):
    nombre: str
    aceptado: bool
    id: uuid.UUID | None = None
    motivo: str | None = None


class CargaOut(BaseModel):
    resultados: list[ResultadoCarga]


class Referencia(BaseModel):
    id: uuid.UUID
    nombre: str
    cargado_en: datetime
    estado: str


class ElementoCola(BaseModel):
    id: uuid.UUID
    nombre: str
    tamano_bytes: int
    estado: str
    paso: str
    progreso: int
    detalle_paso: str | None
    mensaje_error: str | None
    cargado_en: datetime
    cargado_por: str | None
    expediente: str | None
    duplicado_de: Referencia | None = None


class ColaOut(BaseModel):
    procesando: list[ElementoCola]
    duplicados: list[ElementoCola]
    errores: list[ElementoCola]
    listos_hoy: int


class AlertaOut(BaseModel):
    id: uuid.UUID
    tipo: str
    severidad: str
    modulo: str
    mensaje: str
    entidad_tipo: str
    entidad_id: str
    creada_en: datetime
    atendida_en: datetime | None
    atendida_por: str | None
    nota_atencion: str | None


class AtenderIn(BaseModel):
    nota: str | None = Field(default=None, max_length=500)


class LoteIn(BaseModel):
    """Lote de transferencia (ISAD-G 3.2.4; hallazgos ING-01 e ING-02)."""
    fondo_id: uuid.UUID
    forma_ingreso: str = Field(max_length=40)
    remitente_id: uuid.UUID | None = None
    dependencia_origen_id: uuid.UUID | None = None
    acta_numero: str | None = Field(default=None, max_length=60)
    acta_fecha_edtf: str | None = Field(default=None, max_length=200)
    observaciones: str | None = Field(default=None, max_length=5000)


class ActaIn(BaseModel):
    instanciacion_id: uuid.UUID


class AnulacionIn(BaseModel):
    motivo: str = Field(max_length=2000)
