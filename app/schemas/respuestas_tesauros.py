"""
Esquemas de respuesta (solo documentación OpenAPI) de los tesauros.

No filtran la salida: describen lo que devuelven las rutas. Cada modelo
admite campos adicionales.
"""

from pydantic import BaseModel, ConfigDict


class TesauroOut(BaseModel):
    """Un tesauro importado, con su fuente, su licencia y cuántos conceptos tiene."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    fuente: str | None
    licencia: str | None
    idioma: str
    formato: str
    archivo: str | None
    uri_esquema: str | None
    conceptos: int
    estado: str
    importado_en: str


class TesauroBreve(BaseModel):
    """El tesauro al que pertenece un concepto."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    licencia: str | None


class ConceptoOut(BaseModel):
    """Un concepto: término preferente, no preferentes, nota de alcance y ruta de términos generales."""
    model_config = ConfigDict(extra="allow")

    id: str
    preferente: str
    uri: str | None
    notacion: str | None
    nota_alcance: str | None
    no_preferentes: list[str]
    ruta: list[str]
    tesauro: TesauroBreve


class ConceptoCoincidente(ConceptoOut):
    """Un concepto encontrado al normalizar, con la etiqueta que coincidió."""
    etiqueta_coincidente: str | None = None
    similitud: float | None = None


class NormalizacionOut(BaseModel):
    """Resultado de normalizar un término: el concepto exacto (y si llegó por un término
    no preferente) y los parecidos."""
    model_config = ConfigDict(extra="allow")

    termino: str
    exacto: ConceptoCoincidente | None
    via: str | None
    parecidos: list[ConceptoCoincidente]


class MateriaOut(BaseModel):
    """La materia del fondo que corresponde a un concepto."""
    model_config = ConfigDict(extra="allow")

    id: str
    nombre: str
    concepto: ConceptoOut
