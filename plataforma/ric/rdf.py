"""Proyección RDF del grafo validado (T050): serializa entidades y
relaciones RiC usando exclusivamente las URIs de RiC-O 1.1 tal como se
verificaron contra la fuente primaria (`RiC-O_1-1.rdf`) en
`ric/fixtures/ric_matrix.json` — nunca una URI inventada.

Solo se serializan relaciones con estado ACEPTADA o MODIFICADA: "la IA
propone, la persona decide" también aplica a lo que sale como RDF.

No se reifican las relaciones (RiC-RA01 certeza, RA03 descripción, RA05
fuente quedan fuera): RiC-O sí define una clase `rico:Relation` para
reificar relaciones con esos atributos, pero su patrón exacto de modelado
no se verificó contra la fuente primaria, así que por ahora cada relación
se serializa como un triple directo (origen -[predicado RiC-O]-> destino),
que es exactamente cómo RiC-O define esas propiedades "atajo".
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF

from . import reglas, tipos
from .models import RelacionRiC

RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")

# Campo del modelo Django -> ID de atributo RiC-CM (A##), tal como se
# documentó en el help_text de cada campo en ric/models.py y se verificó
# contra ric_matrix.json (mismo nombre, mismo dominio).
_ATRIBUTOS_THING = {"identificador": "A22", "nombre": "A28", "descripcion_general": "A43"}
_ATRIBUTOS_POR_MODELO = {
    "RecordResource": {
        "autenticidad": "A03", "clasificacion": "A07", "condiciones_acceso": "A08",
        "condiciones_uso": "A09", "tipo_contenido": "A10", "historia": "A21",
        "nota_integridad": "A24", "idioma": "A25", "estatus_legal": "A26",
        "extension": "A35", "alcance_y_contenido": "A38", "estado_produccion": "A39",
        "estructura": "A40",
    },
    "RecordSet": {"accruals": "A01", "tipo_conjunto": "A36"},
    "Record": {"tipo_forma_documental": "A17"},
    "RecordPart": {"tipo_forma_documental": "A17"},
    "Instantiation": {
        "tipo_soporte": "A05", "extension_soporte": "A04",
        "tipo_representacion": "A37", "caracteristicas_fisicas": "A31",
    },
    "Agent": {"historia": "A21", "idioma": "A25", "estatus_legal": "A26"},
    "Person": {"tipo_ocupacion": "A30"},
    "Group": {"grupo_demografico": "A15"},
    "Family": {"tipo_familia": "A20"},
    "CorporateBody": {"tipo_entidad_corporativa": "A12"},
    "Mechanism": {"caracteristicas_tecnicas": "A41"},
    "Event": {"tipo_evento": "A18", "historia": "A21"},
    "Activity": {"tipo_actividad": "A02"},
    "Rule": {"tipo_regla": "A45", "historia": "A21"},
    "Mandate": {"tipo_mandato": "A44"},
    "Date": {"expresion": "A19", "valor_normalizado": "A29", "calificador": "A13", "tipo_fecha": "A42"},
    "Place": {"coordenadas": "A11", "ubicacion": "A27", "tipo_lugar": "A32", "historia": "A21"},
}

_MODELO_A_RIC_ID = {v: k for k, v in tipos.RIC_ID_A_MODELO_NOMBRE.items()}


def _uri_rico(prefijo_uri):
    """'rico:hasCreator' -> RICO.hasCreator, usando el namespace verificado."""
    return RICO[prefijo_uri.split(":", 1)[1]]


def _campos_ric(modelo):
    """(campo, A-code) para `modelo`, incluidos los heredados de Thing y de
    sus clases padre concretas (herencia multitabla)."""
    campos = dict(_ATRIBUTOS_THING)
    for clase in reversed(modelo.__mro__):
        campos.update(_ATRIBUTOS_POR_MODELO.get(clase.__name__, {}))
    return campos


def _tipo_rdf(modelo):
    """El URI RiC-O verificado para el tipo RiC-CM concreto de `modelo`."""
    e_id = _MODELO_A_RIC_ID[modelo.__name__]
    return _uri_rico(reglas.cargar_matriz()["entidades"][e_id]["uri_rico"])


def _uri_entidad(entidad, base):
    return URIRef(f"{base}{type(entidad).__name__.lower()}/{entidad.pk}")


def _emitir_entidad(g, entidad, base):
    """Agrega el rdf:type y los atributos con valor de `entidad` a `g`."""
    sujeto = _uri_entidad(entidad, base)
    g.add((sujeto, RDF.type, _tipo_rdf(type(entidad))))
    for campo, a_code in _campos_ric(type(entidad)).items():
        valor = getattr(entidad, campo, "")
        if valor in ("", None):
            continue
        predicado = _uri_rico(reglas.cargar_matriz()["atributos"][a_code]["uri_rico"])
        g.add((sujeto, predicado, Literal(str(valor))))
    return sujeto


def _emitir_relacion(g, relacion, base):
    info = reglas.cargar_matriz()["relaciones"].get(relacion.relacion_id)
    if info is None or not info.get("uri_rico"):
        return
    if relacion.origen is None or relacion.destino is None:
        return
    origen = _emitir_entidad(g, relacion.origen, base)
    destino = _emitir_entidad(g, relacion.destino, base)
    g.add((origen, _uri_rico(info["uri_rico"]), destino))


def _relaciones_validadas():
    return RelacionRiC.objects.filter(
        estado__in=(RelacionRiC.Estado.ACEPTADA, RelacionRiC.Estado.MODIFICADA)
    ).select_related("origen_content_type", "destino_content_type")


def grafo_de_entidad(entidad, base):
    """El vecindario a un salto de `entidad`: sus atributos y toda relación
    RiC ya validada donde participa, como origen o como destino."""
    g = Graph()
    g.bind("rico", RICO)
    _emitir_entidad(g, entidad, base)

    content_type = ContentType.objects.get_for_model(entidad)
    relaciones = _relaciones_validadas().filter(
        Q(origen_content_type=content_type, origen_object_id=entidad.pk)
        | Q(destino_content_type=content_type, destino_object_id=entidad.pk)
    )
    for relacion in relaciones:
        _emitir_relacion(g, relacion, base)
    return g


def grafo_completo(base):
    """Todo el grafo RiC validado: cada RelacionRiC aceptada o modificada,
    con las dos entidades que conecta. Es lo que carga el endpoint SPARQL."""
    g = Graph()
    g.bind("rico", RICO)
    for relacion in _relaciones_validadas():
        _emitir_relacion(g, relacion, base)
    return g
