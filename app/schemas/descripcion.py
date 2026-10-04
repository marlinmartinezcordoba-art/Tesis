import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

TipoEntidad = Literal["agente", "lugar", "fecha", "actividad", "tipo_actividad", "mandato", "forma_documental"]
ClaseVocabulario = Literal["agente", "lugar", "forma_documental", "actividad", "tipo_actividad", "mandato", "tipo_parte"]


class ElementoPorDescribir(BaseModel):
    id: uuid.UUID
    nombre: str
    tamano_bytes: int
    formato: str | None
    expediente: str | None
    origen_texto: str | None
    confianza_ocr: float | None = None
    ocr_baja_confianza: bool = False
    cargado_en: datetime
    en_edicion_por: str | None


class IniciarIn(BaseModel):
    instanciacion_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    nivel: Literal["expediente", "subserie", "serie"] | None = None


class VerificarIn(BaseModel):
    fondo_id: uuid.UUID
    tipo: ClaseVocabulario
    valor: str = Field(min_length=1, max_length=300)


class CoincidenciaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    subtipo: str | None
    similitud: float
    conexiones: int
    aviso: str | None = None
    forma: str | None = None  # otra forma del nombre que coincidió (DES-10)


class EntidadIn(BaseModel):
    tipo: TipoEntidad
    valor: str = Field(max_length=300)
    subtipo: str | None = Field(default=None, max_length=40)
    rol: str | None = Field(default=None, max_length=40)
    fecha_normalizada: str | None = None
    edtf: str | None = Field(default=None, max_length=200)
    nota: str | None = Field(default=None, max_length=500)  # p. ej. de un tramo de la custodia
    fecha_subtipo: Literal["simple", "rango", "conjunto"] | None = None
    tipo_clave: str | None = Field(default=None, max_length=40)
    agente_clave: str | None = Field(default=None, max_length=40)
    mandato_clave: str | None = Field(default=None, max_length=40)
    actividad_mayor_id: uuid.UUID | None = None
    actividad_mayor_clave: str | None = Field(default=None, max_length=40)
    fragmento: str | None = Field(default=None, max_length=500)
    documento_id: str | None = None
    inicio: int | None = None
    clave: str | None = Field(default=None, max_length=40)
    reutilizar_id: uuid.UUID | None = None
    crear_nueva: bool = False


class TipoParteIn(BaseModel):
    valor: str = Field(max_length=300)
    reutilizar_id: uuid.UUID | None = None
    crear_nueva: bool = False


class RecorteIn(BaseModel):
    instanciacion_id: uuid.UUID
    pagina: int = Field(default=1, ge=1, le=10000)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    ancho: float = Field(gt=0, le=1)
    alto: float = Field(gt=0, le=1)


class ParteIn(BaseModel):
    titulo: str = Field(max_length=300)
    tipo_parte: TipoParteIn | None = None
    alcance: str | None = Field(default=None, max_length=5000)
    recorte: RecorteIn | None = None


class CamposRegistro(BaseModel):
    """Idioma, condiciones de acceso y de uso, y secuencia (versión 3)."""
    idiomas: list[str] | None = Field(default=None, max_length=5)
    condiciones_acceso: str | None = Field(default=None, max_length=5000)
    condiciones_uso: str | None = Field(default=None, max_length=5000)
    historia_archivistica: str | None = Field(default=None, max_length=20000)
    # Resto de ISAD-G (DES-07): {campo: texto}; ver app/servicios/isadg.py.
    isadg: dict[str, str | None] | None = None
    escrituras: list[str] | None = Field(default=None, max_length=10)
    precede_a_id: uuid.UUID | None = None
    sigue_a_id: uuid.UUID | None = None


class ClasificacionIn(BaseModel):
    """Clasificación del acceso según la Ley 1712 de 2014, declarada al
    describir. Crea la declaración de derechos del Record Resource (la
    misma que se gestiona en Preservación → Derechos)."""
    acceso: Literal["publico", "clasificado", "reservado"]
    fundamento: str | None = Field(default=None, max_length=500)  # obligatorio si no es pública
    reproduccion: Literal["permitida", "condicionada", "no_permitida"] = "permitida"
    vigente_hasta: date | None = None  # obligatorio si es reservada (art. 22: máximo 15 años)


class ProteccionIn(BaseModel):
    """Esquema de Metadatos del AGN v1.4: protección de datos (Ley 1581 de
    2012, minimización) y accesibilidad (Ley 1680 de 2013). None: no cambia;
    texto vacío en la nota: se borra."""
    datos_personales: Literal["no_contiene", "personales", "sensibles", "menores"] | None = None
    nota_accesibilidad: str | None = Field(default=None, max_length=2000)


class PublicarIn(CamposRegistro):
    trabajo_id: uuid.UUID
    clasificacion: ClasificacionIn | None = None  # vacío: hereda la del nivel superior
    proteccion: ProteccionIn | None = None
    titulo: str = Field(max_length=300)
    alcance_contenido: str = Field(default="", max_length=5000)
    incluido_en_id: uuid.UUID | None = None
    entidades: list[EntidadIn] = Field(default_factory=list, max_length=300)
    partes: list[ParteIn] = Field(default_factory=list, max_length=50)


class ControlIn(BaseModel):
    """Datos de control del inventario (FUID). Vacío = sin dato."""
    codigo_referencia: str | None = Field(default=None, max_length=60)
    caja: str | None = Field(default=None, max_length=30)
    carpeta: str | None = Field(default=None, max_length=30)
    folios: int | None = Field(default=None, ge=0, le=100000)
    soporte: str | None = Field(default=None, max_length=40)
    tomo: str | None = Field(default=None, max_length=30)
    otra_unidad: str | None = Field(default=None, max_length=60)
    frecuencia_consulta: Literal["alta", "media", "baja", "ninguna"] | None = None


class EditarIn(CamposRegistro):
    trabajo_id: uuid.UUID
    titulo: str | None = Field(default=None, max_length=300)
    alcance_contenido: str | None = Field(default=None, max_length=5000)
    incluido_en_id: uuid.UUID | None = None
    anular_relaciones: list[uuid.UUID] = Field(default_factory=list)
    quitar_forma_documental: bool = False
    agregar_entidades: list[EntidadIn] = Field(default_factory=list, max_length=100)
    agregar_partes: list[ParteIn] = Field(default_factory=list, max_length=50)
    control: ControlIn | None = None
    # Clasificación del acceso (Ley 1712): una nueva, o volver a heredar la del nivel superior.
    clasificacion: ClasificacionIn | None = None
    clasificacion_hereda: bool = False
    proteccion: ProteccionIn | None = None


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
