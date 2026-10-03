"""
Conformidad de la exportación RDF con RiC-O 1.1.

Dos comprobaciones independientes sobre el mismo grafo exportado:

1. Contra la ontología oficial (OWL): toda clase y toda propiedad de RiC-O
   que aparece existe, y cada tripleta respeta el dominio y el rango que la
   ontología declara (con sus superclases). Ningún predicado fuera de RiC-O,
   RDF, RDFS, SKOS y OWL (así no se cuela un campo interno).
2. Contra el perfil de aplicación SHACL del sistema (pyshacl): las
   cardinalidades y formatos que el sistema promete (título, tipo de
   agrupación, EDTF, ISO 639-3…) y, generadas desde el mapeo único, las
   clases admitidas en el origen y el destino de cada relación.

La primera no depende del mapeo del sistema (lee el OWL); la segunda sí, y
por eso sirve para detectar errores del exportador, no del mapeo. El mapeo
se verifica aparte contra el OWL (ric_o.verificar_contra_owl).
"""

from functools import lru_cache
from pathlib import Path

from rdflib import OWL, RDF, RDFS, BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection

from app.servicios import ric_o

SH = Namespace("http://www.w3.org/ns/shacl#")
RICO = Namespace(ric_o.RICO)
PR = Namespace("https://ricora.local/perfil#")
PERFIL = Path(__file__).resolve().parent.parent / "recursos" / "ric-o" / "perfil-ricora.shacl.ttl"
ESPACIOS_PERMITIDOS = (ric_o.RICO, ric_o.RST, ric_o.SKOS, str(RDF), str(RDFS), str(OWL))


@lru_cache(maxsize=1)
def formas() -> Graph:
    """El perfil escrito a mano más una forma por relación del mapeo."""
    g = Graph()
    g.parse(PERFIL, format="turtle")
    # Fecha normalizada: el subconjunto EDTF de servicios/fechas.py, tal cual.
    from app.servicios import fechas

    edtf = PR["fecha-edtf"]
    g.add((edtf, RDF.type, SH.NodeShape))
    g.add((edtf, SH.targetClass, RICO.Date))
    propiedad = BNode()
    g.add((edtf, SH.property, propiedad))
    g.add((propiedad, SH.path, RICO.normalizedDateValue))
    g.add((propiedad, SH.pattern, Literal("|".join(f"(?:{x.pattern})" for x in (fechas._SIMPLE, fechas._RANGO,
                                                                                fechas._CONJUNTO)))))
    g.add((propiedad, SH.message, Literal("La fecha normalizada es EDTF del subconjunto del sistema "
                                          "(servicios/fechas.py).")))
    for codigo, p in sorted(ric_o.PROPIEDADES.items()):
        forma = PR[f"relacion-{codigo}"]
        g.add((forma, RDF.type, SH.NodeShape))
        g.add((forma, SH.targetSubjectsOf, RICO[p.rico]))
        g.add((forma, SH.message, Literal(f"rico:{p.rico} ({p.codigo_cm or 'sin código RiC-CM'}): "
                                          f"origen admitido {', '.join(p.origen)}; destino {', '.join(p.destino)}.")))
        if "Thing" not in p.origen:
            g.add((forma, SH["or"], _lista(g, [_clase(g, c) for c in p.origen])))
        if "Thing" not in p.destino:
            propiedad = BNode()
            g.add((forma, SH.property, propiedad))
            g.add((propiedad, SH.path, RICO[p.rico]))
            g.add((propiedad, SH["or"], _lista(g, [_clase(g, c) for c in p.destino])))
    return g


def _clase(g: Graph, clase: str) -> BNode:
    n = BNode()
    g.add((n, SH["class"], RICO[clase]))
    return n


def _lista(g: Graph, elementos: list) -> BNode:
    cabeza = BNode()
    Collection(g, cabeza, elementos)
    return cabeza


@lru_cache(maxsize=1)
def jerarquia() -> Graph:
    """Lo que sh:class necesita del OWL: la jerarquía de clases de RiC-O y
    el tipo de sus individuos (rst:Fonds…). Mezclar el OWL completo en cada
    validación multiplica el tiempo sin cambiar el resultado."""
    g, owl = Graph(), ric_o._owl()
    for c, sup in owl.subject_objects(RDFS.subClassOf):
        if isinstance(c, URIRef) and isinstance(sup, URIRef):
            g.add((c, RDFS.subClassOf, sup))
    for ind, tipo in owl.subject_objects(RDF.type):
        if str(ind).startswith(ric_o.RST):
            g.add((ind, RDF.type, tipo))
    return g


def validar_shacl(datos: Graph) -> dict:
    from pyshacl import validate

    conforme, resultados, _ = validate(datos, shacl_graph=formas(), ont_graph=jerarquia(), inference="none",
                                       abort_on_first=False, allow_warnings=True, advanced=True)
    salida = []
    for r in resultados.subjects(RDF.type, SH.ValidationResult):
        def uno(p):
            v = resultados.value(r, p)
            return str(v) if v is not None else None
        forma = resultados.value(r, SH.sourceShape)
        if isinstance(forma, BNode):  # forma de propiedad anidada: se nombra la forma que la contiene
            forma = next(formas().subjects(SH.property, forma), forma)
        salida.append({"foco": uno(SH.focusNode), "ruta": _corto(uno(SH.resultPath)), "mensaje": uno(SH.resultMessage),
                       "severidad": _corto(uno(SH.resultSeverity)),
                       "forma": _corto(str(forma)) if not isinstance(forma, BNode) else None,
                       "valor": uno(SH.value)})
    salida.sort(key=lambda x: (x["forma"] or "", x["foco"] or ""))
    return {"conforme": bool(conforme), "resultados": salida}


def _corto(valor: str | None) -> str | None:
    if valor is None:
        return None
    for prefijo, ns in (("rico:", ric_o.RICO), ("sh:", str(SH)), ("perfil:", str(PR))):
        if valor.startswith(ns):
            return prefijo + valor[len(ns):]
    return valor if not valor.startswith("n") or len(valor) < 30 else None  # nodo en blanco


@lru_cache(maxsize=None)
def _ancestros(clase: str) -> frozenset:
    return frozenset(ric_o._ancestros(ric_o._owl(), clase))


@lru_cache(maxsize=None)
def _declaracion(nombre: str) -> tuple[str | None, frozenset, frozenset]:
    """(ObjectProperty | DatatypeProperty | None, dominio, rango) según el OWL."""
    g = ric_o._owl()
    u = URIRef(ric_o.RICO + nombre)
    tipo = "objeto" if (u, RDF.type, OWL.ObjectProperty) in g else "dato" if (u, RDF.type, OWL.DatatypeProperty) in g else None
    dominio = frozenset().union(*[ric_o._clases_de(g, d) for d in g.objects(u, RDFS.domain)] or [frozenset()])
    rango = frozenset().union(*[ric_o._clases_de(g, r) for r in g.objects(u, RDFS.range)] or [frozenset()])
    return tipo, dominio, rango


def _clases_rico(datos: Graph, nodo) -> set[str]:
    clases = {str(t)[len(ric_o.RICO):] for t in datos.objects(nodo, RDF.type) if str(t).startswith(ric_o.RICO)}
    if not clases and isinstance(nodo, URIRef):  # individuos de la propia ontología (rst:Fonds…)
        clases = {str(t)[len(ric_o.RICO):] for t in ric_o._owl().objects(nodo, RDF.type) if str(t).startswith(ric_o.RICO)}
    return clases


def verificar_owl(datos: Graph) -> list[str]:
    """Problemas de la exportación frente al OWL oficial; vacía si conforme."""
    g = ric_o._owl()
    problemas = set()
    for clase in {o for o in datos.objects(None, RDF.type) if str(o).startswith(ric_o.RICO)}:
        if (clase, RDF.type, OWL.Class) not in g:
            problemas.add(f"La clase rico:{str(clase)[len(ric_o.RICO):]} no existe en RiC-O 1.1.")
    for s, p, o in datos:
        if not str(p).startswith(ESPACIOS_PERMITIDOS):
            problemas.add(f"Predicado fuera de los vocabularios admitidos: {p}.")
            continue
        if not str(p).startswith(ric_o.RICO):
            continue
        nombre = str(p)[len(ric_o.RICO):]
        tipo, dominio, rango = _declaracion(nombre)
        if tipo is None:
            problemas.add(f"rico:{nombre} no existe como propiedad en RiC-O 1.1.")
            continue
        if tipo == "objeto" and isinstance(o, Literal):
            problemas.add(f"rico:{nombre} es de objeto y lleva un literal.")
        if tipo == "dato" and not isinstance(o, Literal):
            problemas.add(f"rico:{nombre} es de dato y apunta a un nodo.")
        clases_s = _clases_rico(datos, s)
        if dominio and not any(_ancestros(c) & dominio for c in clases_s):
            problemas.add(f"rico:{nombre}: el sujeto ({', '.join(sorted(clases_s)) or 'sin clase RiC-O'}) "
                          f"no está en el dominio ({', '.join(sorted(dominio))}).")
        if tipo == "objeto" and rango:
            clases_o = _clases_rico(datos, o)
            if not any(_ancestros(c) & rango for c in clases_o):
                problemas.add(f"rico:{nombre}: el objeto ({', '.join(sorted(clases_o)) or 'sin clase RiC-O'}) "
                              f"no está en el rango ({', '.join(sorted(rango))}).")
    return sorted(problemas)


def reporte(ex) -> dict:
    """Reporte completo de conformidad de una exportación."""
    owl = verificar_owl(ex.grafo)
    shacl = validar_shacl(ex.grafo)
    return {"conforme": not owl and shacl["conforme"], "ontologia": "RiC-O 1.1 (2025-05-22)",
            "owl": {"conforme": not owl, "problemas": owl},
            "shacl": shacl | {"perfil": "perfil-ricora.shacl.ttl", "formas": len(set(formas().subjects(RDF.type, SH.NodeShape)))},
            "mapeo": {"problemas": ric_o.verificar_contra_owl()},
            "sin_propiedad": ric_o.SIN_PROPIEDAD,
            **ex.resumen()}
