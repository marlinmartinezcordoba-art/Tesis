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
- el motor de análisis y la procedencia de cada dato. Los agentes
  mecanismo que actuaron sobre un archivo exportado (el identificador de
  formato, el conversor a PDF/A) sí salen, como rico:Mechanism con su
  versión (rico:technicalCharacteristics) y la acción técnica que ejecutaron
  (rico:Activity que afecta al archivo): hallazgos CM-11 y O-19;
- los borradores sin publicar;
- lo que ric_o.SIN_PROPIEDAD declara sin propiedad en RiC-O (calendario,
  nivel de detalle, fuentes, estructura interna del agente);
- por defecto, lo que tenga acceso clasificado o reservado vigente (Ley
  1712 de 2014): las descripciones, propio o heredado de un nivel
  superior; los archivos (instanciaciones), por su declaración propia o
  heredada; y las entidades del vocabulario que solo citan documentos que
  no se exportan (su nombre también es reservado). Una reserva con plazo
  vencido ya no restringe (art. 22).

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
from app.models.preservacion import DeclaracionDerechos, Migracion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import derechos, fechas, ric_o, vocabulario

RICO = Namespace(ric_o.RICO)
RST = Namespace(ric_o.RST)
SKOS = Namespace(ric_o.SKOS)
LEXVO = Namespace("http://lexvo.org/id/iso639-3/")

NOMBRE_NIVEL = {"fondo": "Fondo", "seccion": "Sección", "subseccion": "Subsección", "serie": "Serie", "subserie": "Subserie",
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
    declaradas = {d.entidad_id: derechos.restringe(d) for d in db.scalars(select(DeclaracionDerechos).where(
        DeclaracionDerechos.entidad_id.in_(list(recursos)), DeclaracionDerechos.vigente.is_(True))).all()}
    salida = set()
    for r in recursos.values():
        actual = r
        while actual is not None:
            if actual.id in declaradas:
                if declaradas[actual.id]:
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
    vedadas = set() if incluir_restringidos else _entidades_vedadas(db, fondo, recursos)

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
                nodo = _cargar(db, tipo, ident, recursos, entidades, fechas_, instancias, incluir_restringidos, vedadas)
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
    # El lugar de los hitos de los agentes exportados (hallazgo CM-13).
    for lugar_id in db.scalars(select(Hito.lugar_id).where(
            Hito.agente_id.in_([i for i, e in entidades.items() if e.clase == "agente"]), Hito.estado == "vigente",
            Hito.lugar_id.is_not(None))).all():
        if lugar_id not in entidades and lugar_id not in vedadas:
            lugar = db.get(EntidadVocabulario, lugar_id)
            if lugar is not None and lugar.estado == "activa":
                entidades[lugar_id] = lugar
    for e in list(entidades.values()):
        _entidad(db, ex, e, entidades)
    for f in fechas_.values():
        _fecha(ex, f)
    for i in instancias.values():
        _instanciacion(ex, i)
    _acciones_tecnicas(db, ex, instancias, entidades)
    return ex


def _acciones_tecnicas(db: Session, ex: Exportacion, instancias: dict, entidades: dict) -> None:
    """Identificación de formato y migraciones de cada archivo exportado,
    como Activity ejercida por su Mechanism (con versión)."""
    g = ex.grafo
    afecta = RICO[ric_o.ACCION_TECNICA["afecta"].rico]
    ejerce = RICO[ric_o.PROPIEDADES["performs_or_performed"].rico]
    inicio = _apoyo("inicio")[0]

    def mecanismo(ident):
        if ident is None:
            return None
        m = entidades.get(ident) or db.get(EntidadVocabulario, ident)
        if m is None or m.estado != "activa" or m.subtipo != "mecanismo":
            return None
        if ident not in entidades:
            entidades[ident] = m
            _entidad(db, ex, m, entidades)
        return uri(m.id)

    tipo = RICO[ric_o.PROPIEDADES["has_activity_type"].rico]
    documenta = RICO[ric_o.PROPIEDADES["documents"].rico]

    def tipo_tecnico(clave, nombre):
        """Tipo de la acción técnica, en el mismo esquema SKOS de los tipos de actividad del fondo."""
        concepto = _concepto(ex, "tipo-de-accion-tecnica", clave, RICO[ric_o.CLASE_VOCABULARIO["tipo_actividad"]], nombre)
        esquema = uri(ex.fondo.id, "tipos-de-actividad")
        g.add((esquema, RDF.type, SKOS.ConceptScheme))
        g.add((esquema, SKOS.prefLabel, Literal(f"Tipos de actividad (funciones) · {ex.fondo.titulo}")))
        g.add((concepto, RDF.type, SKOS.Concept))
        g.add((concepto, SKOS.prefLabel, Literal(nombre)))
        g.add((concepto, SKOS.inScheme, esquema))
        return concepto

    def accion(nodo, nombre, quien, archivo, cuando, clave_tipo, nombre_tipo):
        g.add((nodo, RDF.type, RICO[ric_o.CLASE_VOCABULARIO["actividad"]]))
        g.add((nodo, tipo, tipo_tecnico(clave_tipo, nombre_tipo)))
        g.add((nodo, RDFS.label, Literal(nombre)))
        g.add((nodo, _a("nombre"), Literal(nombre)))
        g.add((nodo, afecta, uri(archivo)))
        if quien is not None:
            g.add((quien, ejerce, nodo))
        if cuando is not None:
            _fecha_libre(ex, nodo, inicio, URIRef(f"{nodo}/fecha"), None, cuando.date().isoformat())

    for i in instancias.values():
        if i.formato_puid or i.mecanismo_identificacion_id:
            accion(uri(i.id, "identificacion-de-formato"),
                   f"Identificación de formato de «{i.nombre_original}»" + (f" ({i.formato_puid})" if i.formato_puid else ""),
                   mecanismo(i.mecanismo_identificacion_id), i.id, i.procesado_en or i.cargado_en,
                   "identificacion", "Identificación de formato")
    for m in db.scalars(select(Migracion).where(Migracion.instanciacion_origen_id.in_(list(instancias)),
                                                Migracion.estado == "completada")).all():
        origen = instancias[m.instanciacion_origen_id]
        nodo = uri(origen.id, "migracion", m.id)
        accion(nodo, f"Migración de «{origen.nombre_original}» a {m.destino_nombre}", mecanismo(m.mecanismo_id),
               origen.id, m.terminada_en or m.aprobada_en, "migracion", "Migración de formato")
        # La instanciación que resultó documenta la migración (hallazgo CM-22).
        if m.instanciacion_resultado_id in instancias:
            g.add((uri(m.instanciacion_resultado_id), documenta, nodo))


def _entidades_vedadas(db: Session, fondo: RecursoDocumental, recursos: dict) -> set[uuid.UUID]:
    """Entidades del vocabulario que citan documentos, pero ninguno que se
    exporte: solo las conocen documentos reservados, clasificados o sin
    publicar, así que su nombre tampoco sale (la misma regla del grafo).
    Una entidad que no cita ningún documento (una institución antecesora,
    un mandato) es contexto puro y sí se exporta."""
    ids = list(db.scalars(select(EntidadVocabulario.id).where(EntidadVocabulario.fondo_id == fondo.id)))
    visibles = set(recursos) - {fondo.id}
    return {e for e, docs in vocabulario._documentos_por_entidad(db, ids).items() if docs and not docs & visibles}


def _cargar(db, tipo, ident, recursos, entidades, fechas_, instancias, incluir_restringidos=True, vedadas=frozenset()):
    if tipo == "recurso_documental":
        return recursos.get(ident)
    if tipo == "entidad_vocabulario":
        if ident not in entidades:
            if ident in vedadas:
                return None
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
            if i is None or (not incluir_restringidos and derechos.instanciacion_restringida(db, i)):
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
        # Código reservado del catálogo: no es que RiC-O no lo tenga (hallazgo O-33).
        ex.omitidas[f"relación «{rel.codigo_ric}» sin mapeo en el sistema (código reservado)"] += 1
        return
    if not ric_o.uso_valido(rel.codigo_ric, _clase_de(t_o, n_o), _clase_de(t_d, n_d)):
        ex.omitidas[f"rico:{p.rico} entre clases que su dominio o rango no admiten"] += 1
        return
    ex.grafo.add((uri(i_o), RICO[p.rico], uri(i_d)))
    if rel.codigo_ric == "has_or_had_holder" and rel.fecha_edtf:
        # RiC-O no reifica la custodia en una clase de relación con fechas: el
        # tramo queda en el sistema y la exportación lo cuenta (DES-05).
        ex.omitidas["periodo de un tramo de custodia (RiC-O no reifica la custodia)"] += 1


# --- Nodos ------------------------------------------------------------------------------------------


def _fecha_libre(ex: Exportacion, sujeto: URIRef, predicado: URIRef, nodo: URIRef, expresada: str | None,
                 edtf: str | None) -> None:
    g = ex.grafo
    g.add((nodo, RDF.type, RICO[ric_o.CLASE_NODO["fecha"]]))
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
        _fecha_libre(ex, sujeto, _apoyo("fecha_asociada")[0], URIRef(f"{sujeto}/fecha"), fechas.legible(edtf), edtf)


def _concepto(ex: Exportacion, grupo: str, clave: str, clase: URIRef, etiqueta: str) -> URIRef:
    nodo = uri(ex.fondo.id, "vocabulario", grupo, _slug(clave))
    g = ex.grafo
    g.add((nodo, RDF.type, clase))
    g.add((nodo, _a("nombre"), Literal(etiqueta)))
    g.add((nodo, RDFS.label, Literal(etiqueta)))
    return nodo


# ISO 639-3 → BCP 47: la etiqueta de idioma de un literal usa el código de
# dos letras cuando existe (BCP 47 prefiere «es» a «spa»); si no, el de tres.
_ISO_639_1 = {"spa": "es", "lat": "la", "eng": "en", "fra": "fr", "por": "pt", "ita": "it", "deu": "de",
              "que": "qu", "cat": "ca", "glg": "gl", "eus": "eu", "nld": "nl", "grc": "grc"}


def bcp47(codigo: str | None) -> str | None:
    if not codigo:
        return None
    codigo = codigo.strip().lower()
    return _ISO_639_1.get(codigo, codigo) if re.fullmatch(r"[a-z]{2,3}", codigo) else None


def _idioma(ex: Exportacion, codigo: str) -> URIRef:
    from app.servicios.motor import IDIOMAS

    nodo = uri(ex.fondo.id, "vocabulario", "idioma", codigo)
    g = ex.grafo
    g.add((nodo, RDF.type, RICO[ric_o.APOYO["idioma_registro"][2]]))
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
    nodo = _concepto(ex, "tipo-de-agrupacion", nivel, RICO[ric_o.APOYO["tipo_agrupacion"][2]], NOMBRE_NIVEL[nivel])
    ex.grafo.add((nodo, SKOS.broadMatch, RST[ric_o.TIPO_AGRUPACION_PROPIO[nivel]]))
    return nodo




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
    if r.historia_archivistica:  # ISAD-G 3.2.3 (hallazgo DES-06)
        g.add((s, _a("historia"), Literal(r.historia_archivistica)))
    # ISAD-G 3.3.3, 3.3.4 y 3.6.1 (hallazgo DES-07). Nuevos ingresos: solo una agrupación.
    if r.nuevos_ingresos and clase == "RecordSet":
        g.add((s, _a("nuevos_ingresos"), Literal(r.nuevos_ingresos)))
    if r.organizacion:
        g.add((s, _a("organizacion"), Literal(r.organizacion)))
    if r.nota:
        g.add((s, _a("descripcion_general"), Literal(r.nota)))
    if clase == "RecordSet":
        # Un solo idioma declarado: todos sus miembros; varios: algunos en cada uno (O-26).
        idioma = _apoyo("idioma_agrupacion" if len(r.idiomas or []) <= 1 else "idioma_agrupacion_parcial")[0]
    else:
        idioma = _apoyo("idioma_registro")[0]
    for codigo in r.idiomas or []:
        g.add((s, idioma, _idioma(ex, codigo)))
    if r.fechas_extremas or r.fechas_extremas_edtf:
        # Fechas extremas de una agrupación: las de creación de todos sus
        # miembros (no la «creación» del conjunto); de un documento, la suya.
        clave = "fechas_extremas" if clase == "RecordSet" else "fecha_creacion"
        _fecha_libre(ex, s, _apoyo(clave)[0], URIRef(f"{s}/fechas-extremas"), r.fechas_extremas,
                     r.fechas_extremas_edtf)
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
    if e.subtipo == "mecanismo" and e.version:
        g.add((s, _a("version_mecanismo"), Literal(e.version)))
    if e.historia and e.clase in ("agente", "lugar", "actividad", "mandato"):
        g.add((s, _a("historia"), Literal(e.historia)))
    if e.contexto_general:
        g.add((s, _a("descripcion_general"), Literal(e.contexto_general)))
    if e.estructura:
        ex.omitidas["estructura interna de un agente (sin propiedad en RiC-O)"] += 1
    if e.clase == "agente":
        # El periodo de una actividad tiene una sola fuente: su nodo Fecha
        # (is_date_associated_with), exportado con las relaciones (CM-14).
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
    if e.clase == "regla":  # regla de retención de la TRD (rico:Rule)
        from app.servicios import retencion

        prop, clase_ap = _apoyo("tipo_regla")
        g.add((s, prop, _concepto(ex, "tipo-de-regla", "retencion", clase_ap, "Regla de retención documental (TRD)")))
        if retencion.resumen(e):
            g.add((s, _a("descripcion_general"), Literal(retencion.resumen(e))))
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
            g.add((nodo, _a("valor_textual"), Literal(n.nombre, lang=bcp47(n.idioma))))
            g.add((s, prop, nodo))
            if n.vigencia_edtf:
                _periodo(ex, nodo, n.vigencia_edtf)
    # Identificadores con su esquema; los de una autoridad externa, además owl:sameAs.
    from app.servicios.autoridad import uri_externa

    for i in db.scalars(select(IdentificadorEntidad).where(IdentificadorEntidad.entidad_id == e.id,
                                                           IdentificadorEntidad.estado == "vigente")).all():
        nodo = URIRef(f"{s}/identificador/{i.id}")
        g.add((nodo, RDF.type, RICO[ric_o.APOYO["identificador_externo"][2]]))
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
            # Otros afectados (hallazgo CM-13), solo si también se exportan.
            for r in db.scalars(select(Relacion).where(Relacion.origen_id == h.id, Relacion.estado == "vigente",
                                                       Relacion.codigo_ric == "affects_or_affected")).all():
                if r.destino_id in entidades or r.destino_id in ex.nodos:
                    g.add((nodo, RICO[ric_o.PROPIEDADES["affects_or_affected"].rico], uri(r.destino_id)))
                else:
                    ex.omitidas["afectados de un hito que no se exportan"] += 1
            if h.lugar_id and h.lugar_id in entidades:
                g.add((uri(h.lugar_id), RICO[ric_o.PROPIEDADES["is_or_was_location_of"].rico], nodo))
    ex.nodos[e.id] = ("entidad_vocabulario", clase)


def _fecha(ex: Exportacion, f: Fecha) -> None:
    g = ex.grafo
    s = uri(f.id)
    g.add((s, RDF.type, RICO[ric_o.CLASE_NODO["fecha"]]))
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
    g.add((s, RDF.type, RICO[ric_o.CLASE_NODO["instanciacion"]]))
    g.add((s, _a("titulo"), Literal(i.nombre_original)))
    g.add((s, RDFS.label, Literal(i.nombre_original)))
    g.add((s, _a("identificador"), Literal(f"urn:uuid:{i.id}")))
    if i.tamano_bytes is not None:
        extension = f"{i.tamano_bytes} bytes" + (f"; {i.paginas} página(s)" if i.paginas else "")
        g.add((s, _a("extension_instanciacion"), Literal(extension)))
    if i.soporte:  # original físico: su tipo de soporte (RiC-A05, rico:CarrierType)
        prop, clase_ap = _apoyo("tipo_soporte")
        g.add((s, prop, _concepto(ex, "tipo-de-soporte", i.soporte, clase_ap, i.soporte.replace("_", " ").capitalize())))
    if i.caracteristicas_fisicas:  # ISAD-G 3.4.4 (hallazgo DES-07), RiC-A31
        g.add((s, _a("caracteristicas_fisicas"), Literal(i.caracteristicas_fisicas)))
    if i.ubicacion_fisica:
        ex.omitidas["ubicación física de un original (sin propiedad de dato en RiC-O para una Instantiation)"] += 1
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
