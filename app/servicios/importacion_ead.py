"""
EAD (EAD3 de 2015 o EAD 2002) convertido a RiC-O 1.1, para importarlo.

RiC-AG recomienda migrar desde la norma anterior y enriquecer después. Un
inventario en EAD (el que exportan AtoM, ArchivesSpace y otros sistemas) se
convierte aquí en un grafo RiC-O con las mismas clases y propiedades que
escribe RICORA, y ese grafo sigue el camino ya probado de `importacion_rico`:
vista previa, cuadro por la parametrización de la TRD, vocabulario,
expedientes, documentos y relaciones, validado contra la ontología y el perfil
SHACL, todo o nada. No hay un segundo camino para crear un fondo.

Correspondencia (EAD → RiC-O):
- <archdesc> y <c>/<c01>…<c12> → rico:RecordSet con su tipo (level: fonds,
  subfonds, series, subseries, file; otherlevel «sección», «subsección»…), o
  rico:Record (level="item"); la anidación → rico:includesOrIncluded.
- <unittitle> → rico:title; <unitid> → rico:identifier.
- <unitdate>/<unitdatestructured> → rico:Date con su expresión y su valor
  normalizado (EDTF), como fechas de creación de los miembros (conjuntos) o
  del documento.
- <scopecontent>, <accessrestrict>, <userestrict>, <custodhist>,
  <arrangement>, <accruals> → alcance y contenido, condiciones de acceso y de
  uso, historia, estructura, ingresos.
- <origination> (persname, corpname, famname) → agente como rico:hasCreator.
- <controlaccess>: personas, entidades y familias → agentes; <subject> →
  materia; <geogname> → lugar; todos como rico:hasOrHadSubject; <genreform> →
  forma documental; <function> → tipo de actividad.
- <dao>/<dao> digitales y <physdesc> no se convierten (los archivos se cargan
  en Carga de documentos): quedan contados.

El XML se lee sin resolver entidades ni descargar nada (sin DTD externas).
"""

import re
from collections import Counter

from lxml import etree
from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef

from app.servicios import fechas, ric_o

RICO = Namespace(ric_o.RICO)
RST = Namespace(ric_o.RST)
BASE = "urn:ricora:ead:"
NIVEL_RST = {"fonds": "Fonds", "subfonds": "Subfonds", "series": "Series", "subseries": "Subseries",
             "file": "File", "collection": "Collection", "recordgrp": "Fonds", "subgrp": "Subfonds"}
# otherlevel en español (como los usan los sistemas del país) → etiqueta que la importación reconoce.
OTRO_NIVEL = {"seccion": "Sección", "sección": "Sección", "subseccion": "Subsección", "subsección": "Subsección",
              "serie": "Serie", "subserie": "Subserie", "expediente": "Expediente", "fondo": "Fondo",
              "unidad documental": None, "documento": None}
AGENTE = {"persname": "Person", "corpname": "CorporateBody", "famname": "Family"}
NOTAS = {"scopecontent": "scopeAndContent", "accessrestrict": "conditionsOfAccess", "userestrict": "conditionsOfUse",
         "custodhist": "history", "arrangement": "structure", "accruals": "accruals"}


class ErrorEad(Exception):
    pass


def _local(e) -> str:
    return etree.QName(e).localname if isinstance(e.tag, str) else ""


def _hijos(e, *nombres):
    return [h for h in e if isinstance(h.tag, str) and _local(h) in nombres]


def _todo(e, nombre):
    return [h for h in e.iter() if isinstance(h.tag, str) and _local(h) == nombre]


def _texto(e) -> str:
    return " ".join("".join(e.itertext()).split()) if e is not None else ""


def raiz_xml(contenido: bytes):
    """La raíz del XML, leído de forma segura; None si no es XML."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False,
                             remove_comments=True)
    try:
        return etree.fromstring(contenido, parser)
    except etree.XMLSyntaxError:
        return None


def es_ead(raiz) -> bool:
    return raiz is not None and _local(raiz) == "ead"


def es_eac(raiz) -> bool:
    """EAC-CPF 2010 (raíz <eac-cpf>) o 2.0 (raíz <eac>)."""
    return raiz is not None and _local(raiz) in ("eac-cpf", "eac")


class _Conversor:
    def __init__(self):
        self.g = Graph()
        self.g.bind("rico", RICO)
        self.n = 0
        self.entidades: dict[tuple, URIRef] = {}
        self.omitidas: Counter = Counter()

    def nuevo(self, clase: str) -> URIRef:
        self.n += 1
        u = URIRef(f"{BASE}{self.n}")
        self.g.add((u, RDF.type, RICO[clase]))
        return u

    def entidad(self, clase: str, nombre: str) -> URIRef | None:
        nombre = " ".join((nombre or "").split()).strip(" .,;")
        if not nombre:
            return None
        clave = (clase, nombre.lower())
        if clave not in self.entidades:
            u = self.nuevo(clase)
            propiedad = RICO.name if clase in ric_o.CLASE_AGENTE.values() else RDFS.label
            self.g.add((u, propiedad, Literal(nombre, lang="es")))
            self.g.add((u, RDFS.label, Literal(nombre, lang="es")))
            if clase == "Concept":
                self.g.add((u, RDF.type, URIRef("http://www.w3.org/2004/02/skos/core#Concept")))
                self.g.add((u, URIRef("http://www.w3.org/2004/02/skos/core#prefLabel"), Literal(nombre, lang="es")))
            self.entidades[clave] = u
        return self.entidades[clave]

    def fecha(self, s: URIRef, did, conjunto: bool) -> None:
        for d in _hijos(did, "unitdate", "unitdatestructured"):
            expresion, normal = _texto(d), d.get("normal")
            if _local(d) == "unitdatestructured":
                partes = [p.get("standarddate") for p in _todo(d, "fromdate") + _todo(d, "todate") + _todo(d, "datesingle")]
                partes = [p for p in partes if p]
                normal = normal or ("/".join(partes[:2]) if partes else None)
                expresion = expresion or normal
            edtf = None
            for candidato in (normal, expresion):
                if not candidato:
                    continue
                try:
                    edtf = fechas.interpretar(candidato).edtf
                    break
                except fechas.FechaInvalida:
                    continue
            if not (expresion or edtf):
                continue
            nodo = self.nuevo("Date")
            self.g.add((nodo, RICO.expressedDate, Literal(expresion or edtf)))
            if edtf:
                self.g.add((nodo, RICO.normalizedDateValue, Literal(edtf)))
            self.g.add((s, RICO.hasOrHadAllMembersWithCreationDate if conjunto else RICO.hasCreationDate, nodo))
            return

    def descripcion(self, e, padre: URIRef | None) -> URIRef:
        """Un <archdesc> o un <c>: su nodo, sus notas, sus agentes y sus hijos."""
        nivel = (e.get("level") or "").lower()
        otro = (e.get("otherlevel") or "").strip().lower()
        did = next(iter(_hijos(e, "did")), None)
        es_documento = nivel == "item" or (nivel == "otherlevel" and OTRO_NIVEL.get(otro, "x") is None)
        s = self.nuevo("Record" if es_documento else "RecordSet")
        if not es_documento:
            if nivel in NIVEL_RST:
                self.g.add((s, RICO.hasRecordSetType, RST[NIVEL_RST[nivel]]))
            elif otro in OTRO_NIVEL and OTRO_NIVEL[otro]:
                tipo = self.nuevo("RecordSetType")
                self.g.add((tipo, RDFS.label, Literal(OTRO_NIVEL[otro], lang="es")))
                self.g.add((s, RICO.hasRecordSetType, tipo))
        if did is not None:
            titulo = _texto(next(iter(_hijos(did, "unittitle")), None))
            codigo = _texto(next(iter(_hijos(did, "unitid")), None))
            if titulo:
                self.g.add((s, RICO.title, Literal(titulo, lang="es")))
            if codigo:
                self.g.add((s, RICO.identifier, Literal(codigo)))
            self.fecha(s, did, not es_documento)
            for origen in _hijos(did, "origination"):
                for a in origen:
                    if isinstance(a.tag, str) and _local(a) in AGENTE:
                        agente = self.entidad(AGENTE[_local(a)], _texto(a))
                        if agente is not None:
                            self.g.add((s, RICO.hasCreator, agente))
            if _hijos(did, "dao", "daogrp", "daoset"):
                self.omitidas["objetos digitales (<dao>): cargue los archivos en Carga de documentos"] += 1
            if _hijos(did, "physdesc", "physdescstructured", "physdescset"):
                self.omitidas["descripción física (<physdesc>): se registra en la instanciación al cargar"] += 1
        for nota, atributo in NOTAS.items():
            textos = [_texto(x) for x in _hijos(e, nota)]
            texto = " ".join(t for t in textos if t)
            if texto:
                self.g.add((s, RICO[atributo], Literal(texto, lang="es")))
        if _hijos(e, "bioghist"):
            self.omitidas["historia del productor (<bioghist>): impórtela con su EAC-CPF en Autoridades"] += 1
        for acceso in _hijos(e, "controlaccess"):
            for x in acceso.iter():
                if not isinstance(x.tag, str) or x is acceso:
                    continue
                nombre, etiqueta = _local(x), _texto(x)
                if nombre in AGENTE:
                    destino = self.entidad(AGENTE[nombre], etiqueta)
                elif nombre == "subject":
                    destino = self.entidad("Concept", etiqueta)
                elif nombre == "geogname":
                    destino = self.entidad("Place", etiqueta)
                elif nombre == "genreform":
                    self.entidad("DocumentaryFormType", etiqueta)
                    continue
                elif nombre == "function":
                    self.entidad("ActivityType", etiqueta)
                    continue
                else:
                    continue
                if destino is not None:
                    self.g.add((s, RICO.hasOrHadSubject, destino))
        if padre is not None:
            self.g.add((padre, RICO.includesOrIncluded, s))
        contenedores = _hijos(e, "dsc") or [e]
        for c in contenedores:
            for hijo in c:
                if isinstance(hijo.tag, str) and re.fullmatch(r"c(0[1-9]|1[0-2])?", _local(hijo)):
                    self.descripcion(hijo, s)
        return s


def a_rico(raiz) -> tuple[Graph, Counter]:
    """El EAD como grafo RiC-O, y lo que no se convirtió (con su motivo)."""
    archdesc = next((x for x in raiz.iter() if isinstance(x.tag, str) and _local(x) == "archdesc"), None)
    if archdesc is None:
        raise ErrorEad("El EAD no tiene <archdesc>: no describe un fondo.")
    conversor = _Conversor()
    fondo = conversor.descripcion(archdesc, None)
    if (fondo, RICO.hasRecordSetType, None) not in conversor.g:
        conversor.g.add((fondo, RICO.hasRecordSetType, RST.Fonds))
    if (fondo, RICO.title, None) not in conversor.g:
        titulo = _texto(next(iter(_todo(raiz, "titleproper")), None))
        if titulo:
            conversor.g.add((fondo, RICO.title, Literal(titulo, lang="es")))
    return conversor.g, conversor.omitidas
