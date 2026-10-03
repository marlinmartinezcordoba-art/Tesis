"""
Exportación del fondo en RDF conforme a RiC-O 1.1 (Turtle y JSON-LD).

Todo nombre de clase y de propiedad sale de servicios/ric_o.py, el mapeo
único ya verificado contra el OWL oficial. Este archivo solo recorre la
base y escribe tripletas; no decide ningún nombre de RiC-O por su cuenta.

Qué se exporta:
- el fondo y las descripciones publicadas (Record Set, Record, Record Part),
  con su jerarquía, sus relaciones vigentes y sus instanciaciones;
- el contexto que esas descripciones citan, hasta donde llegue: agentes,
  lugares, actividades, tipos de actividad (como esquema SKOS), mandatos,
  formas documentales, fechas y la línea de tiempo de los agentes.

Qué no se exporta nunca:
- la procedencia del dato (origen, confianza, motor, fragmento citado): la
  regla de procedencia del sistema;
- los agentes mecanismo (los programas que actúan en el sistema): son
  procedencia técnica, no contexto del fondo;
- los borradores sin publicar;
- lo que ric_o.SIN_PROPIEDAD declara sin propiedad en RiC-O (calendario,
  nivel de detalle, fuentes, estructura interna del agente);
- por defecto, las descripciones con acceso clasificado o reservado
  (Ley 1712 de 2014), propio o heredado de un nivel superior.

Cada omisión queda contada en `omitidas`, para el reporte de conformidad.
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.descripcion import EntidadVocabulario, Fecha, Hito, IdentificadorEntidad, NombreEntidad, Relacion
from app.models.instanciacion import Instanciacion
from app.models.preservacion import DeclaracionDerechos
from app.models.recurso_documental import RecursoDocumental
from app.servicios import fechas, ric_o

RICO = Namespace(ric_o.RICO)
RST = Namespace(ric_o.RST)
SKOS = Namespace(ric_o.SKOS)
LEXVO = Namespace("http://lexvo.org/id/iso639-3/")
ACCESO_RESTRINGIDO = ("clasificado", "reservado")

NOMBRE_NIVEL = {"fondo": "Fondo", "seccion": "Sección", "serie": "Serie", "subserie": "Subserie",
                "expediente": "Expediente"}


def base() -> str:
    return f"{settings.url_publica}/id/"


def uri(*partes) -> URIRef:
    return URIRef(base() + "/".join(str(p) for p in partes))


def _a(clave: str) -> URIRef:
    """Propiedad de dato del mapeo único (ric_o.ATRIBUTOS)."""
    return RICO[ric_o.ATRIBUTOS[clave][0]]


def _apoyo(clave: str) -> tuple[URIRef, URIRef]:
    nombre, _, rango = ric_o.APOYO[clave]
    return RICO[nombre], RICO[rango]


def _texto(valor) -> Literal | None:
    v = (valor or "").strip() if isinstance(valor, str) else valor
    return Literal(v) if v else None


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-") or "x"


@dataclass
class Exportacion:
    grafo: Graph
    fondo: RecursoDocumental
    omitidas: Counter = field(default_factory=Counter)
    nodos: dict = field(default_factory=dict)  # uuid → (tipo, clase RiC-O)

    def resumen(self) -> dict:
        clases = Counter(str(o).split("#")[-1] for o in self.grafo.objects(None, RDF.type) if str(o).startswith(ric_o.RICO))
        return {"tripletas": len(self.grafo), "por_clase": dict(sorted(clases.items())),
                "omitidas": dict(sorted(self.omitidas.items()))}


# --- Visibilidad ----------------------------------------------------------------------------------


def _restringidas(db: Session, recursos: dict[uuid.UUID, RecursoDocumental]) -> set[uuid.UUID]:
    """Descripciones con acceso clasificado o reservado, propio o heredado
    del nivel superior más cercano que tenga declaración (la misma regla de
    herencia de la declaración de derechos de preservación)."""
    declaradas = {d.entidad_id: d.acceso for d in db.scalars(select(DeclaracionDerechos).where(
        DeclaracionDerechos.entidad_id.in_(list(recursos)), DeclaracionDerechos.vigente.is_(True))).all()}
    salida = set()
    for r in recursos.values():
        actual = r
        while actual is not None:
            if actual.id in declaradas:
                if declaradas[actual.id] in ACCESO_RESTRINGIDO:
                    salida.add(r.id)
                break
            actual = recursos.get(actual.incluido_en_id) if actual.incluido_en_id and actual.id != actual.fondo_id else None
    return salida


def _recursos(db: Session, fondo: RecursoDocumental, incluir_restringidos: bool, omitidas: Counter):
    todos = {r.id: r for r in db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == fondo.id)).all()}
    todos[fondo.id] = fondo
    visibles = {i: r for i, r in todos.items() if i == fondo.id or r.publicado_en is not None}
    omitidas["borradores sin publicar"] += len(todos) - len(visibles)
    if not incluir_restringidos:
        fuera = _restringidas(db, visibles)
        for i in fuera:
            visibles.pop(i, None)
        omitidas["descripciones con acceso clasificado o reservado"] += len(fuera)
    # Una descripción cuya cadena superior quedó fuera tampoco se exporta.
    cambio = True
    while cambio:
        cambio = False
        for i, r in list(visibles.items()):
            if i != fondo.id and r.incluido_en_id and r.incluido_en_id not in visibles:
                visibles.pop(i)
                omitidas["descripciones bajo un nivel no exportado"] += 1
                cambio = True
    return visibles


# --- Construcción -----------------------------------------------------------------------------------


def exportar(db: Session, fondo: RecursoDocumental, incluir_restringidos: bool = False) -> Exportacion:
    g = Graph()
    for prefijo, ns in (("rico", RICO), ("rst", RST), ("skos", SKOS), ("owl", OWL), ("rdfs", RDFS),
                        ("ricora", Namespace(base())), ("lexvo", LEXVO)):
        g.bind(prefijo, ns)
    ex = Exportacion(grafo=g, fondo=fondo)
    recursos = _recursos(db, fondo, incluir_restringidos, ex.omitidas)
    for r in recursos.values():
        _recurso(ex, r, recursos)

    # Relaciones vigentes alrededor de las descripciones, y de ahí hacia el
    # contexto (agente → agente, actividad → tipo, mandato → mandato…).
    entidades: dict[uuid.UUID, EntidadVocabulario] = {}
    fechas_: dict[uuid.UUID, Fecha] = {}
    instancias: dict[uuid.UUID, Instanciacion] = {}
    vistas: set[uuid.UUID] = set()
    frontera = set(recursos)
    while frontera:
        filas = db.scalars(select(Relacion).where(
            Relacion.estado == "vigente",
            or_(Relacion.origen_id.in_(list(frontera)), Relacion.destino_id.in_(list(frontera))))).all()
        frontera = set()
        for rel in filas:
            if rel.id in vistas:
                continue
            vistas.add(rel.id)
            extremos = []
            for tipo, ident in ((rel.origen_tipo, rel.origen_id), (rel.destino_tipo, rel.destino_id)):
                nodo = _cargar(db, tipo, ident, recursos, entidades, fechas_, instancias)
                if nodo is None:
                    break
                extremos.append((tipo, ident, nodo))
            if len(extremos) < 2:
                ex.omitidas["relaciones con un extremo no exportado"] += 1
                continue
            for tipo, ident, _ in extremos:
                if tipo != "recurso_documental" and ident not in ex.nodos:
                    ex.nodos[ident] = (tipo, None)
                    frontera.add(ident)
            _relacion(ex, rel, extremos)

    # Formas documentales y tipos de parte citados por la propia descripción
    # (no por una fila de relación).
    for ident in {r.tipo_parte_id if r.nivel == "parte_documental" else r.forma_documental_id
                  for r in recursos.values()} - {None}:
        if _cargar(db, "entidad_vocabulario", ident, recursos, entidades, fechas_, instancias) is None:
            g.remove((None, _apoyo("forma_documental")[0], uri(ident)))
            ex.omitidas["formas documentales no exportables"] += 1
    # Tipos de actividad: también sus conceptos más amplios (SKOS broader).
    pendientes = [e for e in entidades.values() if e.concepto_superior_id]
    while pendientes:
        e = pendientes.pop()
        sup = db.get(EntidadVocabulario, e.concepto_superior_id)
        if sup is not None and sup.id not in entidades and sup.estado == "activa":
            entidades[sup.id] = sup
            if sup.concepto_superior_id:
                pendientes.append(sup)
    for e in entidades.values():
        _entidad(db, ex, e, entidades)
    for f in fechas_.values():
        _fecha(ex, f)
    for i in instancias.values():
        _instanciacion(ex, i)
    return ex


def _cargar(db, tipo, ident, recursos, entidades, fechas_, instancias):
    if tipo == "recurso_documental":
        return recursos.get(ident)
    if tipo == "entidad_vocabulario":
        if ident not in entidades:
            e = db.get(EntidadVocabulario, ident)
            if e is None or e.estado != "activa" or e.subtipo == "mecanismo":
                return None
            entidades[ident] = e
        return entidades[ident]
    if tipo == "fecha":
        if ident not in fechas_:
            f = db.get(Fecha, ident)
            if f is None:
                return None
            fechas_[ident] = f
        return fechas_[ident]
    if tipo == "instanciacion":
        if ident not in instancias:
            i = db.get(Instanciacion, ident)
            if i is None:
                return None
            instancias[ident] = i
        return instancias[ident]
    return None


def _clase_de(tipo: str, nodo) -> str:
    if tipo == "recurso_documental":
        return ric_o.clase_de(tipo, nivel=nodo.nivel)
    if tipo == "entidad_vocabulario":
        return ric_o.clase_de(tipo, clase=nodo.clase, subtipo=nodo.subtipo)
    return ric_o.clase_de(tipo)


def _relacion(ex: Exportacion, rel: Relacion, extremos) -> None:
    p = ric_o.propiedad(rel.codigo_ric)
    (t_o, i_o, n_o), (t_d, i_d, n_d) = extremos
    if p is None:
        ex.omitidas[f"relación «{rel.codigo_ric}» sin propiedad en RiC-O"] += 1
        return
    if not ric_o.uso_valido(rel.codigo_ric, _clase_de(t_o, n_o), _clase_de(t_d, n_d)):
        ex.omitidas[f"rico:{p.rico} entre clases que su dominio o rango no admiten"] += 1
        return
    ex.grafo.add((uri(i_o), RICO[p.rico], uri(i_d)))


# --- Nodos ------------------------------------------------------------------------------------------


def _fecha_libre(ex: Exportacion, sujeto: URIRef, predicado: URIRef, nodo: URIRef, expresada: str | None,
                 edtf: str | None) -> None:
    g = ex.grafo
    g.add((nodo, RDF.type, RICO.Date))
    if expresada:
        g.add((nodo, _a("fecha_expresada"), Literal(expresada)))
    if edtf:
        g.add((nodo, _a("fecha_normalizada"), Literal(edtf)))
        calificador = "aproximada" if "~" in edtf or "%" in edtf else "incierta" if "?" in edtf else None
        if calificador:
            g.add((nodo, _a("calificador_fecha"), Literal(calificador)))
    g.add((sujeto, predicado, nodo))


def _periodo(ex: Exportacion, sujeto: URIRef, edtf: str | None) -> None:
    """Existencia o periodo en EDTF: un intervalo da fecha de inicio y de
    fin (rico:hasBeginningDate / hasEndDate); una sola fecha, fecha asociada."""
    if not edtf:
        return
    if "/" in edtf:
        inicio, fin = edtf.split("/", 1)
        for parte, clave in ((inicio, "inicio"), (fin, "fin")):
            if parte and parte != "..":
                _fecha_libre(ex, sujeto, _apoyo(clave)[0], URIRef(f"{sujeto}/{clave}"),
                             fechas.legible(parte), parte)
    else:
        _fecha_libre(ex, sujeto, RICO.isAssociatedWithDate, URIRef(f"{sujeto}/fecha"), fechas.legible(edtf), edtf)


def _concepto(ex: Exportacion, grupo: str, clave: str, clase: URIRef, etiqueta: str) -> URIRef:
    nodo = uri(ex.fondo.id, "vocabulario", grupo, _slug(clave))
    g = ex.grafo
    g.add((nodo, RDF.type, clase))
    g.add((nodo, _a("nombre"), Literal(etiqueta)))
    g.add((nodo, RDFS.label, Literal(etiqueta)))
    return nodo


def _idioma(ex: Exportacion, codigo: str) -> URIRef:
    from app.servicios.motor import IDIOMAS

    nodo = uri(ex.fondo.id, "vocabulario", "idioma", codigo)
    g = ex.grafo
    g.add((nodo, RDF.type, RICO.Language))
    g.add((nodo, _a("identificador"), Literal(codigo)))
    nombre = IDIOMAS.get(codigo)
    if nombre:
        g.add((nodo, _a("nombre"), Literal(nombre)))
        g.add((nodo, RDFS.label, Literal(nombre)))
    g.add((nodo, SKOS.exactMatch, LEXVO[codigo]))  # ISO 639-3 en Lexvo
    return nodo


def _tipo_agrupacion(ex: Exportacion, nivel: str) -> URIRef:
    oficial = ric_o.TIPO_AGRUPACION_OFICIAL.get(nivel)
    if oficial:
        return RST[oficial]
    # Sección y subserie no tienen individuo oficial en recordSetTypes:
    # concepto propio del sistema, emparentado con el oficial más cercano.
    nodo = _concepto(ex, "tipo-de-agrupacion", nivel, RICO.RecordSetType, NOMBRE_NIVEL[nivel])
    ex.grafo.add((nodo, SKOS.broadMatch, RST[ric_o.TIPO_AGRUPACION_PROPIO[nivel]]))
    return nodo


_AÑOS = re.compile(r"^\s*(\d{4})\s*(?:[–—-]\s*(\d{4}))?\s*$")


def _recurso(ex: Exportacion, r: RecursoDocumental, recursos: dict) -> None:
    g = ex.grafo
    s = uri(r.id)
    clase = ric_o.CLASE_NIVEL[r.nivel]
    g.add((s, RDF.type, RICO[clase]))
    g.add((s, _a("titulo"), Literal(r.titulo)))
    g.add((s, RDFS.label, Literal(r.titulo)))
    for clave, valor in (("identificador", r.codigo_referencia), ("alcance_contenido", r.alcance_contenido),
                         ("condiciones_acceso", r.condiciones_acceso), ("condiciones_uso", r.condiciones_uso)):
        if _texto(valor) is not None:
            g.add((s, _a(clave), _texto(valor)))
    if clase == "RecordSet":
        g.add((s, _apoyo("tipo_agrupacion")[0], _tipo_agrupacion(ex, r.nivel)))
    forma = r.tipo_parte_id if r.nivel == "parte_documental" else r.forma_documental_id
    if forma and clase != "RecordSet":
        g.add((s, _apoyo("forma_documental")[0], uri(forma)))
        ex.nodos.setdefault(forma, ("entidad_vocabulario", None))
    idioma = _apoyo("idioma_agrupacion" if clase == "RecordSet" else "idioma_registro")[0]
    for codigo in r.idiomas or []:
        g.add((s, idioma, _idioma(ex, codigo)))
    if r.fechas_extremas:
        m = _AÑOS.match(r.fechas_extremas)
        edtf = (f"{m.group(1)}/{m.group(2)}" if m.group(2) else m.group(1)) if m else None
        _fecha_libre(ex, s, RICO.hasCreationDate, URIRef(f"{s}/fechas-extremas"), r.fechas_extremas, edtf)
    # Jerarquía: de incluido_en_id (siempre está), no solo de las filas de relación.
    if r.id != ex.fondo.id and r.incluido_en_id in recursos:
        padre = uri(r.incluido_en_id)
        if r.nivel == "parte_documental":
            g.add((padre, RICO[ric_o.PROPIEDADES["has_or_had_constituent"].rico], s))
        else:
            g.add((padre, RICO[ric_o.PROPIEDADES["includes_or_included"].rico], s))
    ex.nodos[r.id] = ("recurso_documental", clase)


def _entidad(db: Session, ex: Exportacion, e: EntidadVocabulario, entidades: dict) -> None:
    g = ex.grafo
    s = uri(e.id)
    clase = ric_o.clase_de("entidad_vocabulario", clase=e.clase, subtipo=e.subtipo)
    g.add((s, RDF.type, RICO[clase]))
    g.add((s, RDFS.label, Literal(e.nombre)))
    # Un mandato lleva rico:title (especialización de rico:name que admite
    # Rule); lo demás, rico:name.
    g.add((s, _a("titulo" if e.clase == "mandato" else "nombre"), Literal(e.nombre)))
    if e.clase in ("tipo_actividad", "forma_documental", "tipo_parte"):
        g.add((s, RDF.type, SKOS.Concept))
        g.add((s, SKOS.prefLabel, Literal(e.nombre)))
    if e.clase == "tipo_actividad":
        esquema = uri(ex.fondo.id, "tipos-de-actividad")
        g.add((esquema, RDF.type, SKOS.ConceptScheme))
        g.add((esquema, SKOS.prefLabel, Literal(f"Tipos de actividad (funciones) · {ex.fondo.titulo}")))
        g.add((s, SKOS.inScheme, esquema))
        if e.concepto_superior_id and e.concepto_superior_id in entidades:
            g.add((s, SKOS[ric_o.SKOS_BROADER], uri(e.concepto_superior_id)))
        elif not e.concepto_superior_id:
            g.add((esquema, SKOS.hasTopConcept, s))
    if e.historia and e.clase in ("agente", "lugar", "actividad", "mandato"):
        g.add((s, _a("historia"), Literal(e.historia)))
    if e.contexto_general:
        g.add((s, _a("descripcion_general"), Literal(e.contexto_general)))
    if e.estructura:
        ex.omitidas["estructura interna de un agente (sin propiedad en RiC-O)"] += 1
    if e.clase in ("agente", "actividad"):
        _periodo(ex, s, e.existencia_edtf)
    if e.clase == "agente" and e.estatuto_juridico:
        prop, clase_ap = _apoyo("estatuto_juridico")
        g.add((s, prop, _concepto(ex, "estatuto-juridico", e.estatuto_juridico, clase_ap,
                                  {"publica": "Pública", "privada": "Privada", "mixta": "Mixta"}[e.estatuto_juridico])))
    if e.clase == "lugar":
        if e.latitud is not None and e.longitud is not None:
            g.add((s, _a("coordenadas"), Literal(f"{e.latitud:.6f}, {e.longitud:.6f}")))  # WGS 84, lat, long
        if e.tipo_lugar:
            prop, clase_ap = _apoyo("tipo_lugar")
            g.add((s, prop, _concepto(ex, "tipo-de-lugar", e.tipo_lugar, clase_ap, e.tipo_lugar.capitalize())))
    if e.clase == "mandato" and e.subtipo:
        prop, clase_ap = _apoyo("tipo_mandato")
        g.add((s, prop, _concepto(ex, "tipo-de-mandato", e.subtipo, clase_ap, e.subtipo.capitalize())))
    # Otras formas del nombre (ISAAR 5.1.3–5.1.5): nodos de nombre de RiC-O.
    if e.clase in ("agente", "lugar"):
        prop, clase_nombre = _apoyo("nombre_agente" if e.clase == "agente" else "nombre_lugar")
        for n in db.scalars(select(NombreEntidad).where(NombreEntidad.entidad_id == e.id,
                                                        NombreEntidad.estado == "vigente")).all():
            nodo = URIRef(f"{s}/nombre/{n.id}")
            g.add((nodo, RDF.type, clase_nombre))
            g.add((nodo, _a("valor_textual"), Literal(n.nombre, lang=n.idioma or None)))
            g.add((s, prop, nodo))
            if n.vigencia_edtf:
                _periodo(ex, nodo, n.vigencia_edtf)
    # Identificadores con su esquema; los de una autoridad externa, además owl:sameAs.
    from app.servicios.autoridad import uri_externa

    for i in db.scalars(select(IdentificadorEntidad).where(IdentificadorEntidad.entidad_id == e.id,
                                                           IdentificadorEntidad.estado == "vigente")).all():
        nodo = URIRef(f"{s}/identificador/{i.id}")
        g.add((nodo, RDF.type, RICO.Identifier))
        g.add((nodo, _a("valor_textual"), Literal(i.valor)))
        prop_tipo, clase_tipo = _apoyo("tipo_identificador")
        g.add((nodo, prop_tipo, _concepto(ex, "tipo-de-identificador", i.esquema, clase_tipo, i.esquema.upper())))
        g.add((s, _apoyo("identificador_externo")[0], nodo))
        externa = uri_externa(i.esquema, i.valor)
        if externa:
            g.add((s, OWL.sameAs, URIRef(externa)))
    # Línea de tiempo institucional: cada hito es un rico:Event.
    if e.clase == "agente":
        for h in db.scalars(select(Hito).where(Hito.agente_id == e.id, Hito.estado == "vigente")).all():
            nodo = uri(h.id)
            g.add((nodo, RDF.type, RICO[ric_o.CLASE_NODO["hito"]]))
            g.add((nodo, _a("nombre"), Literal(h.descripcion)))
            g.add((nodo, RDFS.label, Literal(h.descripcion)))
            g.add((nodo, RICO[ric_o.PROPIEDADES["affects_or_affected"].rico], s))
            _periodo(ex, nodo, h.edtf)
    ex.nodos[e.id] = ("entidad_vocabulario", clase)


def _fecha(ex: Exportacion, f: Fecha) -> None:
    g = ex.grafo
    s = uri(f.id)
    g.add((s, RDF.type, RICO.Date))
    g.add((s, _a("fecha_expresada"), Literal(f.expresion)))
    if f.edtf:
        g.add((s, _a("fecha_normalizada"), Literal(f.edtf)))
        calificador = "aproximada" if "~" in f.edtf or "%" in f.edtf else "incierta" if "?" in f.edtf else None
        if calificador:
            g.add((s, _a("calificador_fecha"), Literal(calificador)))
    if f.calendario and f.calendario != "gregoriano":
        ex.omitidas["calendario distinto del gregoriano (sin propiedad en RiC-O)"] += 1
    ex.nodos[f.id] = ("fecha", "Date")


def _instanciacion(ex: Exportacion, i: Instanciacion) -> None:
    g = ex.grafo
    s = uri(i.id)
    g.add((s, RDF.type, RICO.Instantiation))
    g.add((s, _a("titulo"), Literal(i.nombre_original)))
    g.add((s, RDFS.label, Literal(i.nombre_original)))
    g.add((s, _a("identificador"), Literal(f"urn:uuid:{i.id}")))
    extension = f"{i.tamano_bytes} bytes" + (f"; {i.paginas} página(s)" if i.paginas else "")
    g.add((s, _a("extension_instanciacion"), Literal(extension)))
    if i.formato_puid:
        # El formato identificado, con su ficha en el registro PRONOM.
        g.add((s, RDFS.seeAlso, URIRef(f"https://www.nationalarchives.gov.uk/PRONOM/{i.formato_puid}")))
    ex.nodos[i.id] = ("instanciacion", "Instantiation")


# --- Serialización ------------------------------------------------------------------------------------

FORMATOS = {"turtle": ("turtle", "text/turtle", "ttl"), "jsonld": ("json-ld", "application/ld+json", "jsonld")}


def serializar(g: Graph, formato: str) -> bytes:
    nombre = FORMATOS[formato][0]
    if formato == "jsonld":
        contexto = {p: str(ns) for p, ns in g.namespaces() if p in ("rico", "rst", "skos", "owl", "rdfs", "lexvo")}
        return g.serialize(format=nombre, context=contexto, indent=2).encode("utf-8")
    return g.serialize(format=nombre).encode("utf-8")


def descripcion_de(ex: Exportacion, nodo: URIRef) -> Graph:
    """Lo que se entrega al resolver una URI: las tripletas del nodo, las
    de sus nodos de apoyo (nombre, identificador, fechas propias), las que
    apuntan a él y la clase y la etiqueta de cada nodo citado. Los nodos
    compartidos del fondo (vocabulario, esquema de funciones) se resuelven
    por su propia URI, no dentro de la del fondo."""
    salida = Graph()
    for p, ns in ex.grafo.namespaces():
        salida.bind(p, ns)
    propio = str(nodo) + "/"
    compartidos = (propio + "vocabulario/", propio + "tipos-de-actividad")
    for t in ex.grafo:
        sujeto = str(t[0])
        if t[0] == nodo or t[2] == nodo or (sujeto.startswith(propio) and not sujeto.startswith(compartidos)):
            salida.add(t)
    for o in set(salida.objects()) | set(salida.subjects()):
        if isinstance(o, URIRef) and o != nodo:
            for p in (RDFS.label, RDF.type):
                for v in ex.grafo.objects(o, p):
                    salida.add((o, p, v))
    return salida
