"""
Esquemas de respuesta (solo documentación OpenAPI) de la parametrización de
la TRD: versiones, dependencias, banco terminológico y matriz. Admiten campos
adicionales.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.respuestas_cuadro import InformeCuadro, ValidacionRico


class VersionTrdOut(BaseModel):
    """Una versión de la TRD: acto que la aprueba, convalidación, vigencia y estado."""
    model_config = ConfigDict(extra="allow")

    id: str
    numero: int
    nombre: str
    acto_aprobacion: str | None
    fecha_aprobacion: date | None
    convalidacion: str | None
    fecha_convalidacion: date | None
    vigente_desde: date | None
    vigente_hasta: date | None
    estado: str
    observaciones: str | None
    filas: int
    informe: dict[str, Any] | None
    creado_en: datetime
    aplicado_en: datetime | None
    editable: bool
    ente_vigilancia: str | None = None


class DependenciaTrdOut(BaseModel):
    """Una sección (dependencia productora) o subsección del fondo."""
    model_config = ConfigDict(extra="allow")

    id: str
    codigo: str
    nombre: str
    estado: str
    superior_id: str | None
    codigo_completo: str | None
    nivel: str


class TerminoBancoOut(BaseModel):
    """Una serie, subserie o tipo documental del banco terminológico."""
    model_config = ConfigDict(extra="allow")

    id: str
    clase: str
    codigo: str | None
    nombre: str
    definicion: str | None
    estado: str
    superior_id: str | None
    superior: str | None
    codigo_completo: str | None


class FilaTrdOut(BaseModel):
    """Una serie o subserie de una dependencia en la matriz de la TRD."""
    model_config = ConfigDict(extra="allow")

    id: str
    dependencia_id: str
    serie_id: str
    subserie_id: str | None
    tipos: list[str]
    dependencia: str
    codigo_dependencia: str | None
    serie: str
    subserie: str | None
    codigo: str | None
    nombres_tipos: list[str]
    gestion: int | None
    central: int | None
    disposicion: str | None
    otras_disposiciones: list[str]
    soporte: str | None
    procedimiento: str | None
    funcion: str | None


class AplicacionTrd(BaseModel):
    """Lo que haría (o hizo) aplicar la versión y su validación RiC-O."""
    aplicada: bool
    version: VersionTrdOut
    informe: InformeCuadro
    validacion: ValidacionRico


class ImportacionTrd(BaseModel):
    """Lo que se agregó al borrador desde el archivo."""
    model_config = ConfigDict(extra="allow")

    dependencias: int
    series: int
    subseries: int
    tipos_documentales: int
    filas: int
    repetidas: int
    sin_funcion: int = 0


class CargaTrd(BaseModel):
    """El borrador configurado desde el archivo y lo que se agregó a cada tabla."""
    version: VersionTrdOut
    parametrizacion: ImportacionTrd
