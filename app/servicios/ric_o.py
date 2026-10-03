"""
Mapeo único entre el modelo de datos de RICORA y la ontología RiC-O 1.1.

Este archivo es la única fuente de los nombres de clase y de propiedad de
RiC-O que usa el sistema: la exportación RDF, la validación de conformidad,
la columna «propiedad RiC-O» de auditoría y las pruebas leen de aquí. Nadie
escribe un nombre de RiC-O suelto en otro módulo.

Cada nombre se verificó contra el archivo OWL oficial de RiC-O 1.1
(app/recursos/ric-o/RiC-O_1-1.rdf, versión 1.1 del 22 de mayo de 2025,
licencia CC BY 4.0 del Consejo Internacional de Archivos) y contra el PDF
de RiC-CM 1.0 (noviembre de 2023). La verificación no es una afirmación de
este comentario: `verificar_contra_owl()` la repite y la prueba
tests/test_ric_o.py falla si un nombre no existe o si su dominio o su rango
no admiten las clases con que el sistema lo usa.

Detalle y justificación de cada decisión: documentacion/anexos/
verificacion-ric-o-1-1.md.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

RICO = "https://www.ica.org/standards/RiC/ontology#"
RST = "https://www.ica.org/standards/RiC/vocabularies/recordSetTypes#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
OWL_ARCHIVO = Path(__file__).resolve().parent.parent / "recursos" / "ric-o" / "RiC-O_1-1.rdf"

# Estado de un mapeo:
# - «verificada»: la propiedad existe y su nombre, dominio y rango cubren
#   exactamente el uso del sistema;
# - «general»: RiC-O no tiene una propiedad dedicada para ese caso y el
#   sistema usa la más específica que sí existe, como pide la propia nota de
#   uso de RiC-O («use only if it is not possible to specify a narrower…»).
#   Se exporta, y el anexo explica por qué esa y no otra.
ESTADOS = ("verificada", "general")


@dataclass(frozen=True)
class Propiedad:
    rico: str  # nombre local en RiC-O
    codigo_cm: str | None  # código RiC-CM 1.0 (RiC-Rxxx o RiC-Rxxxi), si lo tiene
    origen: tuple[str, ...]  # clases RiC-O del nodo origen de la fila
    destino: tuple[str, ...]  # clases RiC-O del nodo destino
    inversa: str | None
    estado: str = "verificada"
    nota: str = ""


# --- Clases ------------------------------------------------------------

# Nivel de descripción → clase y tipo de agrupación. Fondo, serie y
# expediente tienen individuo oficial en el vocabulario recordSetTypes de
# RiC-O; sección y subserie no, y se declaran como conceptos propios del
# fondo con skos:broadMatch hacia el oficial más cercano.
CLASE_NIVEL = {
    "fondo": "RecordSet",
    "seccion": "RecordSet",
    "serie": "RecordSet",
    "subserie": "RecordSet",
    "expediente": "RecordSet",
    "unidad_documental": "Record",
    "parte_documental": "RecordPart",
}
TIPO_AGRUPACION_OFICIAL = {"fondo": "Fonds", "serie": "Series", "expediente": "File"}
TIPO_AGRUPACION_PROPIO = {"seccion": "Fonds", "subserie": "Series"}  # → skos:broadMatch

CLASE_AGENTE = {
    "persona": "Person",
    "familia": "Family",
    "entidad_corporativa": "CorporateBody",
    "grupo": "Group",  # instanciable directamente: nota de alcance de rico:Group
    "cargo": "Position",
    "mecanismo": "Mechanism",
}

CLASE_VOCABULARIO = {
    "lugar": "Place",
    "forma_documental": "DocumentaryFormType",
    "actividad": "Activity",
    "tipo_actividad": "ActivityType",  # además skos:Concept del esquema del fondo
    "mandato": "Mandate",
    "tipo_parte": "DocumentaryFormType",  # tipo de una parte documental (anexo, sello…)
}

CLASE_NODO = {
    "instanciacion": "Instantiation",
    "fecha": "Date",
    "hito": "Event",  # evento institucional usado directamente, no como Activity
}


def clase_de(tipo_nodo: str, clase: str | None = None, subtipo: str | None = None,
             nivel: str | None = None) -> str:
    if tipo_nodo == "recurso_documental":
        return CLASE_NIVEL[nivel]
    if tipo_nodo == "entidad_vocabulario":
        if clase == "agente":
            return CLASE_AGENTE.get(subtipo or "", "Agent")
        return CLASE_VOCABULARIO[clase]
    return CLASE_NODO[tipo_nodo]


# Superclases que el sistema necesita conocer para comprobar dominio y
# rango sin cargar la ontología (la prueba las coteja con el OWL).
SUPERCLASES = {
    "Record": ("RecordResource", "Thing"),
    "RecordSet": ("RecordResource", "Thing"),
    "RecordPart": ("RecordResource", "Thing"),
    "RecordResource": ("Thing",),
    "Instantiation": ("Thing",),
    "Person": ("Agent", "Thing"),
    "Group": ("Agent", "Thing"),
    "CorporateBody": ("Group", "Agent", "Thing"),
    "Family": ("Group", "Agent", "Thing"),
    "Position": ("Agent", "Thing"),
    "Mechanism": ("Agent", "Thing"),
    "Agent": ("Thing",),
    "Activity": ("Event", "Thing"),
    "Event": ("Thing",),
    "Mandate": ("Rule", "Thing"),
    "Rule": ("Thing",),
    "Place": ("Thing",),
    "Date": ("Thing",),
    "ActivityType": ("Type", "Concept", "Thing"),
    "DocumentaryFormType": ("Type", "Concept", "Thing"),
}

AGENTES = ("Person", "Family", "CorporateBody", "Group", "Position", "Mechanism")
REGISTROS = ("Record", "RecordPart")
RECURSOS = ("RecordSet", "Record", "RecordPart")

# --- Relaciones: código interno → propiedad de RiC-O --------------------
# El origen y el destino son los de la fila guardada en «relaciones».

PROPIEDADES: dict[str, Propiedad] = {
    # Procedencia
    "has_creator": Propiedad("hasCreator", "RiC-R027", RECURSOS + ("Instantiation",), AGENTES, "isCreatorOf"),
    "has_sender": Propiedad("hasSender", "RiC-R031", REGISTROS, AGENTES, "isSenderOf"),
    "has_addressee": Propiedad("hasAddressee", "RiC-R032", REGISTROS, AGENTES, "isAddresseeOf"),
    # Custodia: el agente que tiene o tuvo el documento sin haberlo producido.
    "has_or_had_holder": Propiedad("hasOrHadHolder", "RiC-R039i", RECURSOS + ("Instantiation",), AGENTES,
                                   "isOrWasHolderOf"),
    # Jerarquía documental
    "includes_or_included": Propiedad("includesOrIncluded", "RiC-R024", ("RecordSet",), ("RecordSet", "Record"),
                                      "isOrWasIncludedIn"),
    "has_or_had_constituent": Propiedad("hasOrHadConstituent", "RiC-R003", REGISTROS, REGISTROS,
                                        "isOrWasConstituentOf"),
    # Secuencia entre documentos del mismo nivel (el origen precede al destino).
    "precedes_or_preceded": Propiedad("precedesOrPreceded", "RiC-R008", RECURSOS, RECURSOS, "followsOrFollowed"),
    "has_or_had_instantiation": Propiedad("hasOrHadInstantiation", "RiC-R025", RECURSOS, ("Instantiation",),
                                          "isOrWasInstantiationOf"),
    "migrated_into": Propiedad("migratedInto", "RiC-R015", ("Instantiation",), ("Instantiation",), "migratedFrom"),
    # Contexto funcional
    "documents": Propiedad("documents", "RiC-R033", RECURSOS + ("Instantiation",), ("Activity",), "documentedBy"),
    "has_activity_type": Propiedad("hasActivityType", None, ("Activity",), ("ActivityType",), "isActivityTypeOf",
                                   nota="Propiedad de tipo de RiC-O; RiC-CM la trata como atributo."),
    "performs_or_performed": Propiedad("performsOrPerformed", "RiC-R060i", AGENTES, ("Activity",),
                                       "isOrWasPerformedBy"),
    "has_direct_subevent": Propiedad("hasDirectSubevent", None, ("Activity",), ("Activity",), "isDirectSubeventOf",
                                     nota="Atajo directo de RiC-R006 has or had subevent."),
    "regulates_or_regulated": Propiedad(
        "regulatesOrRegulated", "RiC-R063", ("Mandate",), ("Activity", "ActivityType", "Mandate") + RECURSOS,
        "isOrWasRegulatedBy",
        nota="Mandato que regula una actividad; con rol «creacion», el mandato que crea un tipo de actividad; "
             "con rol «jerarquia_normativa», la norma superior que regula a la que la desarrolla.",
    ),
    "issued_by": Propiedad("issuedBy", "RiC-R065", ("Mandate",), AGENTES, None,
                           nota="RiC-O no declara inversa."),
    "authorizes": Propiedad("authorizes", "RiC-R067", ("Mandate",), AGENTES, "authorizedBy",
                            nota="Con rol «creacion», el mandato que crea o establece al agente."),
    # Agente a agente
    "has_or_had_subordinate": Propiedad("hasOrHadSubordinate", "RiC-R045", AGENTES, AGENTES, "isOrWasSubordinateTo"),
    "has_successor": Propiedad("hasSuccessor", "RiC-R016", AGENTES, AGENTES, "isSuccessorOf"),
    "is_agent_associated_with_agent": Propiedad("isAgentAssociatedWithAgent", "RiC-R044", AGENTES, AGENTES,
                                                "isAgentAssociatedWithAgent", nota="Simétrica."),
    "occupies_or_occupied": Propiedad("occupiesOrOccupied", "RiC-R054", ("Person",), ("Position",),
                                      "isOrWasOccupiedBy"),
    # Eventos institucionales (línea de tiempo del agente)
    "affects_or_affected": Propiedad("affectsOrAffected", "RiC-R059", ("Event",), AGENTES + RECURSOS,
                                     "isOrWasAffectedBy", estado="general",
                                     nota="RiC-O no tiene una propiedad dedicada a «hito de la historia de»; "
                                          "R059 (el evento tuvo un impacto significativo en la cosa) es la más "
                                          "específica que cubre creación, reforma y traslado."),
    # Lugar
    "contains_or_contained": Propiedad("containsOrContained", "RiC-R007", ("Place",), ("Place",),
                                       "isOrWasContainedBy"),
    "is_or_was_location_of": Propiedad("isOrWasLocationOf", "RiC-R075", ("Place",), AGENTES + RECURSOS,
                                       "hasOrHadLocation"),
    # Tema y fecha
    "has_or_had_subject": Propiedad("hasOrHadSubject", "RiC-R019", RECURSOS, ("Thing",), "isOrWasSubjectOf"),
    "is_creation_date_of": Propiedad("isCreationDateOf", "RiC-R080", ("Date",), RECURSOS + ("Instantiation",),
                                     "hasCreationDate"),
    "is_date_associated_with": Propiedad("isDateAssociatedWith", "RiC-R068", ("Date",), ("Thing",),
                                         "isAssociatedWithDate"),
    # Función ↔ serie (TRD): sin propiedad dedicada.
    "is_related_to": Propiedad("isRelatedTo", "RiC-R001", ("ActivityType",), RECURSOS, "isRelatedTo",
                               estado="general",
                               nota="RiC-O no tiene propiedad entre un tipo de actividad y la serie que produce; "
                                    "la relación se reconstruye por documents + hasActivityType y se exporta "
                                    "con la relación más general, R001, simétrica."),
}

# Atributos (propiedades de dato) que el sistema exporta.
ATRIBUTOS = {
    "titulo": ("title", "RiC-A40"),
    "alcance_contenido": ("scopeAndContent", "RiC-A38"),
    "condiciones_acceso": ("conditionsOfAccess", "RiC-A08"),
    "condiciones_uso": ("conditionsOfUse", "RiC-A09"),
    "historia": ("history", "RiC-A21"),
    "descripcion_general": ("generalDescription", "RiC-A43"),
    "identificador": ("identifier", "RiC-A22"),
    "version_mecanismo": ("technicalCharacteristics", "RiC-A41"),
    "coordenadas": ("geographicalCoordinates", "RiC-A11"),
    "fecha_expresada": ("expressedDate", "RiC-A19"),
    "fecha_normalizada": ("normalizedDateValue", "RiC-A29"),
    "calificador_fecha": ("dateQualifier", "RiC-A13"),
    "reglas": ("ruleFollowed", None),
    "extension": ("recordResourceExtent", "RiC-A35"),
}

# Propiedades de objeto hacia nodos de apoyo (no son relaciones del grafo
# descriptivo, sino atributos que RiC-O modela como clases).
APOYO = {
    "idioma_registro": ("hasOrHadLanguage", ("Record", "RecordPart", *AGENTES), "Language"),
    "idioma_agrupacion": ("hasOrHadAllMembersWithLanguage", ("RecordSet",), "Language"),
    "tipo_lugar": ("hasOrHadPlaceType", ("Place",), "PlaceType"),
    "nombre_lugar": ("hasOrHadPlaceName", ("Place",), "PlaceName"),
    "nombre_agente": ("hasOrHadAgentName", AGENTES, "AgentName"),
    "identificador_externo": ("hasOrHadIdentifier", ("Thing",), "Identifier"),
    "tipo_identificador": ("hasIdentifierType", ("Identifier",), "IdentifierType"),
    "estatuto_juridico": ("hasOrHadLegalStatus", AGENTES, "LegalStatus"),
    "tipo_agrupacion": ("hasRecordSetType", ("RecordSet",), "RecordSetType"),
    "forma_documental": ("hasDocumentaryFormType", ("Record", "RecordPart"), "DocumentaryFormType"),
    "tipo_mandato": ("hasOrHadRuleType", ("Mandate",), "RuleType"),
    "inicio": ("hasBeginningDate", ("Thing",), "Date"),
    "fin": ("hasEndDate", ("Thing",), "Date"),
}

# Datos que el sistema guarda pero que RiC-O no tiene dónde poner, y por
# eso no se exportan. Se declaran para que la omisión sea explícita.
SIN_PROPIEDAD = {
    "calendario": "RiC-O no declara calendario; normalizedDateValue usa ISO 8601 (gregoriano). Delimitación de la tesis.",
    "nivel_detalle": "Dato de control interno del registro de autoridad.",
    "fuentes": "RiC-O solo ofrece fuente para relaciones reificadas (isEvidencedBy); se conserva interno.",
    "origen_confianza": "Procedencia del dato (motor o persona): nunca sale del sistema.",
}

SKOS_BROADER = "broader"  # jerarquía función/subfunción: SKOS, no RiC-O
SKOS_NARROWER = "narrower"


def propiedad(codigo: str) -> Propiedad | None:
    return PROPIEDADES.get(codigo)


def etiqueta(codigo: str | None) -> str | None:
    """«rico:hasCreator» para mostrar en auditoría; None si no hay mapeo."""
    p = PROPIEDADES.get(codigo or "")
    return f"rico:{p.rico}" if p else None


def _es(clase: str, admitidas: tuple[str, ...]) -> bool:
    return clase in admitidas or any(s in admitidas for s in SUPERCLASES.get(clase, ()))


def uso_valido(codigo: str, clase_origen: str, clase_destino: str) -> bool:
    """¿La fila respeta el origen y el destino declarados para el código?"""
    p = PROPIEDADES.get(codigo)
    return bool(p and _es(clase_origen, p.origen) and _es(clase_destino, p.destino))


# --- Verificación contra el archivo OWL oficial ---------------------------


@lru_cache(maxsize=1)
def _owl():
    from rdflib import Graph

    g = Graph()
    g.parse(OWL_ARCHIVO)
    return g


def _clases_de(g, nodo) -> set[str]:
    """Clases nombradas que admite un dominio o rango (con owl:unionOf)."""
    from rdflib import OWL, URIRef
    from rdflib.collection import Collection

    if isinstance(nodo, URIRef):
        return {str(nodo).split("#")[-1]}
    salida = set()
    for lista in g.objects(nodo, OWL.unionOf):
        salida |= {str(x).split("#")[-1] for x in Collection(g, lista)}
    return salida


def _ancestros(g, clase: str) -> set[str]:
    from rdflib import RDFS, URIRef

    vistos, pendientes = {clase}, [URIRef(RICO + clase)]
    while pendientes:
        actual = pendientes.pop()
        for sup in g.objects(actual, RDFS.subClassOf):
            if isinstance(sup, URIRef) and str(sup).startswith(RICO):
                nombre = str(sup).split("#")[-1]
                if nombre not in vistos:
                    vistos.add(nombre)
                    pendientes.append(sup)
    return vistos | {"Thing"}


def verificar_contra_owl() -> list[str]:
    """Lista de problemas; vacía si todo el mapeo es conforme al OWL."""
    from rdflib import OWL, RDF, RDFS, URIRef

    g = _owl()
    problemas = []

    def existe(nombre, tipo):
        return (URIRef(RICO + nombre), RDF.type, tipo) in g

    clases = set(CLASE_NIVEL.values()) | set(CLASE_AGENTE.values()) | set(CLASE_VOCABULARIO.values()) \
        | set(CLASE_NODO.values()) | {"Language", "PlaceType", "PlaceName", "AgentName", "Identifier",
                                      "IdentifierType", "LegalStatus", "RecordSetType", "RuleType"}
    for c in sorted(clases):
        if not existe(c, OWL.Class):
            problemas.append(f"La clase rico:{c} no existe en RiC-O 1.1.")
    for c, sups in SUPERCLASES.items():
        reales = _ancestros(g, c)
        for s in sups:
            if s not in reales and s != "Concept":
                problemas.append(f"rico:{c} no es subclase de rico:{s}.")

    def cubre(admitidas_owl: set[str], usadas: tuple[str, ...]) -> list[str]:
        return [u for u in usadas if not (_ancestros(g, u) & admitidas_owl)]

    for codigo, p in PROPIEDADES.items():
        u = URIRef(RICO + p.rico)
        if not existe(p.rico, OWL.ObjectProperty):
            problemas.append(f"{codigo}: rico:{p.rico} no existe como propiedad de objeto.")
            continue
        dominio = set().union(*[_clases_de(g, d) for d in g.objects(u, RDFS.domain)] or [set()])
        rango = set().union(*[_clases_de(g, r) for r in g.objects(u, RDFS.range)] or [set()])
        for fuera in cubre(dominio, p.origen):
            problemas.append(f"{codigo}: el dominio de rico:{p.rico} ({', '.join(sorted(dominio))}) no admite {fuera}.")
        for fuera in cubre(rango, p.destino):
            problemas.append(f"{codigo}: el rango de rico:{p.rico} ({', '.join(sorted(rango))}) no admite {fuera}.")
        if p.inversa and p.inversa != p.rico:
            inversas = {str(x).split("#")[-1] for x in g.objects(u, OWL.inverseOf)} \
                | {str(x).split("#")[-1] for x in g.subjects(OWL.inverseOf, u)}
            if p.inversa not in inversas:
                problemas.append(f"{codigo}: rico:{p.inversa} no es la inversa de rico:{p.rico}.")
        if p.codigo_cm:
            cm = " ".join(str(x) for x in g.objects(u, URIRef(RICO + "RiCCMCorrespondingComponent")))
            codigos = {c.upper() for c in re.findall(r"R\d{3}i?", cm, flags=re.IGNORECASE)}
            if p.codigo_cm.split("-")[1].upper() not in codigos:
                problemas.append(f"{codigo}: rico:{p.rico} no corresponde a {p.codigo_cm} en RiC-O.")
    for clave, (nombre, _) in ATRIBUTOS.items():
        if not existe(nombre, OWL.DatatypeProperty):
            problemas.append(f"{clave}: rico:{nombre} no existe como propiedad de dato.")
    for clave, (nombre, usadas, rango) in APOYO.items():
        u = URIRef(RICO + nombre)
        if not existe(nombre, OWL.ObjectProperty):
            problemas.append(f"{clave}: rico:{nombre} no existe como propiedad de objeto.")
            continue
        dominio = set().union(*[_clases_de(g, d) for d in g.objects(u, RDFS.domain)] or [set()])
        for fuera in cubre(dominio, usadas):
            problemas.append(f"{clave}: el dominio de rico:{nombre} no admite {fuera}.")
        rangos = set().union(*[_clases_de(g, r) for r in g.objects(u, RDFS.range)] or [set()])
        if rango not in rangos:
            problemas.append(f"{clave}: el rango de rico:{nombre} no es rico:{rango}.")
    return problemas


def etiqueta_es(nombre: str) -> str | None:
    """Etiqueta oficial en español (rdfs:label @es) de una clase o propiedad."""
    from rdflib import RDFS, URIRef

    for lbl in _owl().objects(URIRef(RICO + nombre), RDFS.label):
        if getattr(lbl, "language", None) == "es":
            return str(lbl)
    return None
