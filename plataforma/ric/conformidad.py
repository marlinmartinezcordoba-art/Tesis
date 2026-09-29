"""Conformidad con RiC-O 1.1: verifica un grafo RDF contra la ontología
oficial (`ric/ontologia/RiC-O_1-1.rdf`), no contra una lista hecha a mano.

Por cada tripleta en el espacio de nombres de RiC-O comprueba que:
- la clase de cada `rdf:type` exista en RiC-O;
- la propiedad exista, y sea de objeto (apunta a una entidad) o de dato
  (apunta a un texto) según la usa el grafo;
- el sujeto tenga un tipo compatible con el dominio de la propiedad y, en
  las de objeto, el destino uno compatible con su rango (con la jerarquía de
  clases de RiC-O: una Entidad corporativa es un Grupo, que es un Agente...).

Devuelve la lista de hallazgos en lenguaje claro; vacía = conforme."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS

RUTA_ONTOLOGIA = Path(__file__).parent / "ontologia" / "RiC-O_1-1.rdf"
RICO = "https://www.ica.org/standards/RiC/ontology#"


def _corto(uri):
    return "rico:" + str(uri)[len(RICO):] if str(uri).startswith(RICO) else str(uri)


@dataclass(frozen=True)
class Propiedad:
    uri: URIRef
    de_objeto: bool
    dominio: frozenset  # clases permitidas (vacío = cualquiera)
    rango: frozenset


class Ontologia:
    def __init__(self, ruta=RUTA_ONTOLOGIA):
        g = Graph()
        g.parse(str(ruta))
        self.clases = {c for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef) and str(c).startswith(RICO)}
        self._padres = {c: {p for p in g.objects(c, RDFS.subClassOf) if isinstance(p, URIRef)} for c in self.clases}
        self.propiedades = {}
        for tipo, de_objeto in ((OWL.ObjectProperty, True), (OWL.DatatypeProperty, False)):
            for p in g.subjects(RDF.type, tipo):
                if isinstance(p, URIRef) and str(p).startswith(RICO):
                    self.propiedades[p] = Propiedad(
                        p, de_objeto,
                        frozenset().union(*(self._expandir(g, d) for d in g.objects(p, RDFS.domain))),
                        frozenset().union(*(self._expandir(g, r) for r in g.objects(p, RDFS.range))) if de_objeto else frozenset(),
                    )

    @staticmethod
    def _expandir(g, expresion):
        """Una clase o una unión de clases (owl:unionOf) -> conjunto de clases."""
        if isinstance(expresion, BNode):
            union = g.value(expresion, OWL.unionOf)
            if union is not None:
                return frozenset(c for c in Collection(g, union) if isinstance(c, URIRef))
            return frozenset()
        return frozenset([expresion])

    @lru_cache(maxsize=None)
    def ancestros(self, clase):
        """La clase y todas sus superclases en RiC-O."""
        vistos, pendientes = {clase}, [clase]
        while pendientes:
            for padre in self._padres.get(pendientes.pop(), ()):
                if padre not in vistos:
                    vistos.add(padre)
                    pendientes.append(padre)
        return frozenset(vistos)

    def compatible(self, tipos_nodo, permitidas):
        if not permitidas:
            return True
        return any(self.ancestros(t) & permitidas for t in tipos_nodo)


@lru_cache(maxsize=1)
def ontologia():
    return Ontologia()


def validar(g, maximo=200):
    """Hallazgos de conformidad de `g` con RiC-O 1.1 (lista vacía = conforme)."""
    onto = ontologia()
    hallazgos = []
    tipos = {}
    for s, o in g.subject_objects(RDF.type):
        tipos.setdefault(s, set()).add(o)
        if str(o).startswith(RICO) and o not in onto.clases:
            hallazgos.append(f"{s}: la clase {_corto(o)} no existe en RiC-O 1.1.")
    for s, p, o in g:
        if p == RDF.type or not str(p).startswith(RICO):
            continue
        prop = onto.propiedades.get(p)
        if prop is None:
            hallazgos.append(f"{s}: la propiedad {_corto(p)} no existe en RiC-O 1.1.")
            continue
        if prop.de_objeto and isinstance(o, Literal):
            hallazgos.append(f"{s}: {_corto(p)} debe apuntar a una entidad, no al texto «{o}».")
            continue
        if not prop.de_objeto and not isinstance(o, Literal):
            hallazgos.append(f"{s}: {_corto(p)} debe tener un texto como valor, no la entidad {o}.")
            continue
        tipos_s = tipos.get(s, set())
        if not tipos_s:
            hallazgos.append(f"{s}: usa {_corto(p)} pero no declara su clase RiC-O.")
        elif not onto.compatible(tipos_s, prop.dominio):
            hallazgos.append(f"{s}: su clase ({', '.join(sorted(_corto(t) for t in tipos_s))}) no está en el dominio de {_corto(p)}.")
        if prop.de_objeto:
            tipos_o = tipos.get(o, set())
            if not tipos_o:
                hallazgos.append(f"{o}: es destino de {_corto(p)} pero no declara su clase RiC-O.")
            elif not onto.compatible(tipos_o, prop.rango):
                hallazgos.append(f"{o}: su clase ({', '.join(sorted(_corto(t) for t in tipos_o))}) no está en el rango de {_corto(p)}.")
        if len(hallazgos) >= maximo:
            break
    return hallazgos
