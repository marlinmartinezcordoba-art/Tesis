"""
Esquemas de respuesta del grafo de contexto del fondo.

Solo documentan en OpenAPI lo que devuelven las rutas (se declaran con
`responses=`, no con `response_model=`): no filtran ni validan la salida.
"""

from pydantic import BaseModel, ConfigDict


class OpcionClave(BaseModel):
    """Opción del panel de filtros: clave y nombre en pantalla."""

    model_config = ConfigDict(extra="allow")

    clave: str
    nombre: str


class OpcionRelacion(BaseModel):
    """Tipo de relación que el fondo usa, con su propiedad RiC-O."""

    model_config = ConfigDict(extra="allow")

    clave: str
    nombre: str
    uri_rico: str | None


class RaizPosible(BaseModel):
    """Entidad que puede ser el centro del grafo."""

    model_config = ConfigDict(extra="allow")

    clave: str
    etiqueta: str | None
    subtitulo: str | None
    familia: str


class OpcionesGrafo(BaseModel):
    """Opciones del panel de filtros y entidades que pueden ser raíz."""

    model_config = ConfigDict(extra="allow")

    familias: list[OpcionClave]
    relaciones: list[OpcionRelacion]
    estados: list[OpcionClave]
    raices: list[RaizPosible]
    saltos_maximos: int
    maximo_nodos: int


class FondoGrafo(BaseModel):
    """Fondo al que pertenece el grafo."""

    model_config = ConfigDict(extra="allow")

    id: str
    titulo: str | None


class NodoGrafo(BaseModel):
    """Entidad dibujada en el grafo (descripción, agente, fecha, archivo o hito)."""

    model_config = ConfigDict(extra="allow")

    id: str
    clave: str
    salto: int
    tipo: str
    clase: str | None
    familia: str
    etiqueta: str | None
    subtitulo: str | None
    estado: str | None
    fecha_inicio: str | None
    fecha_fin: str | None
    documentos: int | None = None


class AristaGrafo(BaseModel):
    """Relación dibujada entre dos entidades del grafo."""

    model_config = ConfigDict(extra="allow")

    desde: str
    hacia: str
    codigo_ric: str
    uri_rico: str | None
    etiqueta: str
    dirigida: bool


class Subgrafo(BaseModel):
    """Subgrafo acotado alrededor de una entidad raíz."""

    model_config = ConfigDict(extra="allow")

    fondo: FondoGrafo
    centro: str
    saltos: int
    nodos: list[NodoGrafo]
    aristas: list[AristaGrafo]
    truncado: bool
    maximo_nodos: int
    filtros_activos: int


class CampoFicha(BaseModel):
    """Dato de la ficha con su ícono."""

    model_config = ConfigDict(extra="allow")

    campo: str
    valor: str
    icono: str


class OtroExtremo(BaseModel):
    """La otra entidad de una relación."""

    model_config = ConfigDict(extra="allow")

    clave: str
    etiqueta: str | None
    familia: str


class RelacionFicha(BaseModel):
    """Relación de la entidad seleccionada, en el sentido en que se lee."""

    model_config = ConfigDict(extra="allow")

    codigo_ric: str
    etiqueta: str
    uri_rico: str | None
    sentido: str
    otro: OtroExtremo
    registrada: str | None


class FichaGrafo(BaseModel):
    """Resumen, atributos y relaciones de la entidad seleccionada en el grafo."""

    model_config = ConfigDict(extra="allow")

    clave: str
    id: str
    tipo: str
    clase: str | None
    familia: str
    familia_nombre: str
    etiqueta: str | None
    resumen: list[CampoFicha]
    atributos: list[CampoFicha]
    relaciones_total: int
    relaciones: list[RelacionFicha]
