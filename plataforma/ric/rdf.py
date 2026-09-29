"""Proyección RDF del grafo validado (T050): serializa entidades y
relaciones RiC usando exclusivamente las URIs de RiC-O 1.1 tal como se
verificaron contra la fuente primaria (`RiC-O_1-1.rdf`) en
`ric/fixtures/ric_matrix.json` — nunca una URI inventada.

Solo se serializan relaciones con estado ACEPTADA o MODIFICADA: "la IA
propone, la persona decide" también aplica a lo que sale como RDF.

Atributos de «tipo» (A02 tipo de actividad, A17 forma documental, A25
idioma, A36 tipo de agrupación, A44 tipo de mandato…): en RiC-O son
propiedades de objeto cuyo rango es una clase (rico:ActivityType,
rico:DocumentaryFormType, rico:Language…). Se emiten como individuos de esa
clase, con su nombre, y nunca como un texto suelto. Qué atributo es de
objeto y cuál de dato lo dice la ontología oficial (`ric/conformidad.py`),
no una lista hecha a mano.

No se reifican las relaciones (RiC-RA01 certeza, RA03 descripción, RA05
fuente quedan fuera): RiC-O sí define una clase `rico:Relation` para
reificar relaciones con esos atributos, pero su patrón exacto de modelado
no se verificó contra la fuente primaria, así que por ahora cada relación
se serializa como un triple directo (origen -[predicado RiC-O]-> destino),
que es exactamente cómo RiC-O define esas propiedades "atajo".
"""

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from rdflib import Graph, Literal, Namespace, URIRef
from django.utils.text import slugify
from rdflib.namespace import RDF

from . import conformidad, reglas, tipos
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


def mas_especifica(entidad):
    """La misma entidad en su clase más concreta: una relación puede guardar
    su origen como RecordResource o Agent (clase general, herencia
    multitabla) cuando en realidad es un Record o una Person. En RiC-O cada
    entidad tiene una sola URI y se declara con su clase precisa."""
    for campo in type(entidad)._meta.related_objects:
        if campo.one_to_one and campo.parent_link:
            try:
                return mas_especifica(getattr(entidad, campo.get_accessor_name()))
            except ObjectDoesNotExist:
                continue
    return entidad


def _uri_entidad(entidad, base):
    entidad = mas_especifica(entidad)
    return URIRef(f"{base}{type(entidad).__name__.lower()}/{entidad.pk}")


def _uri_tipo(base, clase, valor):
    """Un individuo de una clase de tipo de RiC-O (p. ej. rico:ActivityType),
    identificado por su valor: el mismo valor da el mismo individuo."""
    return URIRef(f"{base}tipo/{str(clase).split('#')[-1]}/{slugify(valor)[:80] or 'sin-nombre'}")


def _emitir_entidad(g, entidad, base):
    """Agrega el rdf:type y los atributos con valor de `entidad` a `g`."""
    entidad = mas_especifica(entidad)
    sujeto = _uri_entidad(entidad, base)
    g.add((sujeto, RDF.type, _tipo_rdf(type(entidad))))
    for campo, a_code in _campos_ric(type(entidad)).items():
        valor = getattr(entidad, campo, "")
        if valor in ("", None):
            continue
        if a_code == "A17" and getattr(entidad, "forma_documental", None) is not None:
            continue  # la forma documental controlada (M5) se emite abajo como individuo propio
        predicado = _uri_rico(reglas.cargar_matriz()["atributos"][a_code]["uri_rico"])
        propiedad = conformidad.ontologia().propiedades.get(predicado)
        if propiedad is not None and propiedad.de_objeto and propiedad.rango:
            clase = sorted(propiedad.rango)[0]
            uri_tipo = _uri_tipo(base, clase, str(valor))
            g.add((uri_tipo, RDF.type, clase))
            g.add((uri_tipo, RICO.name, Literal(str(valor))))
            g.add((sujeto, predicado, uri_tipo))
        else:
            g.add((sujeto, predicado, Literal(str(valor))))
    # M5: la forma documental controlada se emite como individuo de
    # rico:DocumentaryFormType (clase verificada en RiC-O_1-1.rdf, subclase
    # de rico:Type) enlazado con rico:hasDocumentaryFormType (RiC-A17).
    # Especificación v5: los nombres alternativos de un agente se emiten como
    # individuos rico:Name (clase verificada en RiC-O_1-1.rdf) enlazados con
    # rico:hasOrHadName y con su rico:textualValue, sin confundirlos con el
    # nombre autorizado (rico:name, RiC-A28).
    for i, variante in enumerate(l for l in (getattr(entidad, "nombres_alternativos", "") or "").splitlines() if l.strip()):
        uri_nombre = URIRef(f"{sujeto}/nombre/{i + 1}")
        g.add((uri_nombre, RDF.type, RICO.Name))
        g.add((uri_nombre, RICO.textualValue, Literal(variante.strip())))
        g.add((sujeto, RICO.hasOrHadName, uri_nombre))
    forma = getattr(entidad, "forma_documental", None)
    if forma is not None:
        uri_forma = URIRef(f"{base}formadocumental/{forma.pk}")
        g.add((uri_forma, RDF.type, RICO.DocumentaryFormType))
        g.add((uri_forma, _uri_rico(reglas.cargar_matriz()["atributos"]["A28"]["uri_rico"]), Literal(forma.nombre)))
        g.add((sujeto, _uri_rico(reglas.cargar_matriz()["atributos"]["A17"]["uri_rico"]), uri_forma))
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
    # F09 (motor de reglas: dominio/rango + inversas): la matriz verificada
    # también trae la propiedad inversa de RiC-O para cada relación (p. ej.
    # "has creator" / "is creator of") — antes se guardaba pero nunca se
    # usaba, así que quien consultara el RDF exportado sin razonador OWL
    # (SPARQL directo, por ejemplo) no encontraba nada preguntando por el
    # lado inverso. Se materializa explícitamente, con la misma evidencia
    # ya validada.
    for inversa in info.get("inversa_rico") or []:
        g.add((destino, _uri_rico(inversa), origen))


def _relaciones_validadas():
    return RelacionRiC.objects.filter(
        estado__in=(RelacionRiC.Estado.ACEPTADA, RelacionRiC.Estado.MODIFICADA)
    ).select_related("origen_content_type", "destino_content_type")


def grafo_de_entidad(entidad, base, visibilidad=None):
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
        if visibilidad is None or visibilidad.relacion(relacion):
            _emitir_relacion(g, relacion, base)
    return g


def grafo_completo(base, visibilidad=None):
    """Todo el grafo RiC: cada entidad ya guardada con sus atributos, más
    cada RelacionRiC aceptada o modificada entre ellas. Es lo que carga el
    endpoint SPARQL.

    F12 (auditoría): antes solo recorría las relaciones ya validadas y
    emitía las dos entidades de cada una — una entidad recién ingerida
    (F01) o creada a mano, sin ninguna relación validada todavía, no
    aparecía en absoluto en el RDF completo ni en SPARQL, aunque ya
    existiera de verdad en el sistema. Ahora se recorren también todos los
    tipos concretos (mismo inventario que "Entidades RiC"), así que toda
    entidad guardada aparece con sus propios atributos desde que existe,
    tenga o no relaciones ya validadas."""
    g = Graph()
    g.bind("rico", RICO)
    for rid in tipos.TIPOS_CONCRETOS:
        modelo = apps.get_model("ric", tipos.RIC_ID_A_MODELO_NOMBRE[rid])
        for entidad in tipos.instancias_propias(modelo):
            if visibilidad is None or visibilidad.puede(entidad):
                _emitir_entidad(g, entidad, base)
    for relacion in _relaciones_validadas():
        if visibilidad is None or visibilidad.relacion(relacion):
            _emitir_relacion(g, relacion, base)
    return g


def grafo_de_tipo(clase_local, valor_slug, base, visibilidad=None):
    """El individuo de tipo `…/tipo/<Clase>/<valor>` (p. ej. un rico:ActivityType)
    con su nombre y las entidades que lo tienen. None si no existe."""
    g = Graph()
    g.bind("rico", RICO)
    for nombre_modelo, campos in [("Thing", _ATRIBUTOS_THING), *_ATRIBUTOS_POR_MODELO.items()]:
        for campo, a_code in campos.items():
            predicado = _uri_rico(reglas.cargar_matriz()["atributos"][a_code]["uri_rico"])
            propiedad = conformidad.ontologia().propiedades.get(predicado)
            if not (propiedad and propiedad.de_objeto and propiedad.rango):
                continue
            if str(sorted(propiedad.rango)[0]).split("#")[-1] != clase_local or nombre_modelo == "Thing":
                continue
            modelo = apps.get_model("ric", nombre_modelo)
            valores = {v for v in modelo.objects.exclude(**{campo: ""}).values_list(campo, flat=True).distinct()
                       if v and (slugify(v)[:80] or "sin-nombre") == valor_slug}
            for entidad in modelo.objects.filter(**{f"{campo}__in": valores}):
                if visibilidad is None or visibilidad.puede(entidad):
                    _emitir_entidad(g, entidad, base)
    return g if len(g) else None


def grafo_de_forma_documental(forma, base, visibilidad=None):
    """La forma documental controlada (rico:DocumentaryFormType) y los
    documentos que la tienen."""
    from .models import Record

    g = Graph()
    g.bind("rico", RICO)
    uri_forma = URIRef(f"{base}formadocumental/{forma.pk}")
    g.add((uri_forma, RDF.type, RICO.DocumentaryFormType))
    g.add((uri_forma, RICO.name, Literal(forma.nombre)))
    for record in Record.objects.filter(forma_documental=forma):
        if visibilidad is None or visibilidad.puede(record):
            _emitir_entidad(g, record, base)
    return g
