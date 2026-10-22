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

La procedencia de cada relación sí sale (auditoría de especialización,
brecha 1): cada relación tiene su nodo rico:Relation con su fuente
(rico:relationSource: persona o motor de análisis, y el fragmento citado si
el archivo del que sale no está restringido), su certeza
(rico:relationCertainty, solo si la propuso el motor y nadie la corrigió) y
su estado (rico:relationState, si su vigencia dice que terminó o sigue).

Qué no se exporta nunca:
- la procedencia de cada atributo de una entidad (la confianza del alcance,
  de los idiomas…): RiC-O no tiene dónde ponerla fuera de una relación;
- el motor de análisis como agente. Los agentes
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
from app.db.base import ahora
from app.models.descripcion import EntidadVocabulario, Fecha, Hito, IdentificadorEntidad, NombreEntidad, Relacion
from app.models.instanciacion import TECNICA_PRODUCCION, Instanciacion
from app.models.preservacion import DeclaracionDerechos, Migracion
from app.models.recurso_documental import ESTADO_DOCUMENTO, TIPO_CONTENIDO, RecursoDocumental
from app.servicios import derechos, fechas, ric_o, vocabulario

RICO = Namespace(ric_o.RICO)
RST = Namespace(ric_o.RST)
SKOS = Namespace(ric_o.SKOS)
LEXVO = Namespace("http://lexvo.org/id/iso639-3/")

NOMBRE_NIVEL = {"fondo": "Fondo", "coleccion": "Colección", "seccion": "Sección", "subseccion": "Subsección", "serie": "Serie", "subserie": "Subserie",
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
    completa: bool = False  # con lo restringido (el grafo «completo»), no el público

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


def grafo_vacio() -> Graph:
    g = Graph()
    for prefijo, ns in (("rico", RICO), ("rst", RST), ("skos", SKOS), ("owl", OWL), ("rdfs", RDFS),
                        ("ricora", Namespace(base())), ("lexvo", LEXVO)):
        g.bind(prefijo, ns)
    return g


def exportar(db: Session, fondo: RecursoDocumental, incluir_restringidos: bool = False) -> Exportacion:
    """Arma el grafo RiC-O del fondo desde la base. Solo lo usa `grafo_rdf.sincronizar`
    (y la evaluación de conformidad de lo que se está describiendo): lo que se consulta
    y se descarga sale del grafo guardado (`grafo_rdf.leer`)."""
    g = grafo_vacio()
    ex = Exportacion(grafo=g, fondo=fondo, completa=incluir_restringidos)
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
            _relacion(db, ex, rel, extremos, incluir_restringidos)

    # Formas documentales y tipos de parte citados por la propia descripción
    # (no por una fila de relación).
    citadas = {r.tipo_parte_id if r.nivel == "parte_documental" else r.forma_documental_id for r in recursos.values()}
    citadas |= {f for r in recursos.values() for f in (r.formas_miembros or [])}  # tipos de la TRD en cada serie
    for ident in citadas - {None}:
        if _cargar(db, "entidad_vocabulario", ident, recursos, entidades, fechas_, instancias) is None:
            for clave in ("forma_documental", "formas_miembros"):
                g.remove((None, _apoyo(clave)[0], uri(ident)))
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
        _instanciacion(db, ex, i)
    _acciones_tecnicas(db, ex, instancias, entidades)
    _trd(db, ex, entidades)
    _instrumentos_aprobados(db, ex, recursos)
    for i in instancias.values():  # el recorte y el archivo del que salió (RiC-R034)
        if i.recorte_de_id in instancias:
            g.add((uri(i.id), _apoyo("instanciacion_asociada")[0], uri(i.recorte_de_id)))
    _fechas_entre_niveles(ex, recursos)
    return ex


def _intervalo(edtf: str | None):
    try:
        f = fechas.interpretar(edtf) if edtf else None
    except fechas.FechaInvalida:
        return None
    return (f.inicio, f.fin) if f and f.inicio and f.fin else None


def _fechas_entre_niveles(ex: Exportacion, recursos: dict) -> None:
    """Las fechas de cada descripción frente a las de su conjunto: la del documento
    es fecha de creación de algunos miembros del conjunto (RiC-R082), y está dentro de
    sus fechas extremas (RiC-R085) o se cruza con ellas (RiC-R086). Lo segundo también
    sirve de control: una fecha que solo se cruza merece revisión."""
    g = ex.grafo
    for r in recursos.values():
        padre = recursos.get(r.incluido_en_id) if r.id != ex.fondo.id else None
        if padre is None or not r.fechas_extremas_edtf and not r.fechas_extremas:
            continue
        nodo_hijo = URIRef(f"{uri(r.id)}/fechas-extremas")
        if ric_o.CLASE_NIVEL[r.nivel] == "Record" and ric_o.CLASE_NIVEL[padre.nivel] == "RecordSet":
            g.add((uri(padre.id), _apoyo("fechas_algunos")[0], nodo_hijo))
        if not (padre.fechas_extremas_edtf or padre.fechas_extremas):
            continue
        hijo, conjunto = _intervalo(r.fechas_extremas_edtf), _intervalo(padre.fechas_extremas_edtf)
        if hijo is None or conjunto is None:
            continue
        nodo_padre = URIRef(f"{uri(padre.id)}/fechas-extremas")
        if conjunto[0] <= hijo[0] and hijo[1] <= conjunto[1]:
            g.add((nodo_hijo, _apoyo("fecha_dentro_de")[0], nodo_padre))
        elif hijo[0] <= conjunto[1] and conjunto[0] <= hijo[1]:
            g.add((nodo_hijo, _apoyo("fecha_se_cruza")[0], nodo_padre))


def _trd(db: Session, ex: Exportacion, entidades: dict) -> None:
    """La TRD como instrumento (no solo sus reglas): cada versión aplicada es una
    rico:Rule de tipo «Tabla de retención documental» con su vigencia, que regula el
    fondo y tiene por partes las reglas de retención que rigieron durante ella; el
    acto administrativo que la aprueba es un rico:Mandate que la regula."""
    from app.models.trd import VersionTrd
    from app.servicios import retencion

    g = ex.grafo
    versiones = db.scalars(select(VersionTrd).where(VersionTrd.fondo_id == ex.fondo.id,
                                                    VersionTrd.estado.in_(("vigente", "historica")))
                           .order_by(VersionTrd.numero)).all()
    if not versiones:
        return
    reglas = db.execute(select(Relacion.origen_id, Relacion.fecha_edtf).where(
        Relacion.codigo_ric == "regulates_or_regulated", Relacion.rol == "retencion", Relacion.estado == "vigente",
        Relacion.origen_id.in_([i for i, e in entidades.items() if e.clase == "regla"]))).all()
    prop_tipo, clase_tipo = _apoyo("tipo_regla")
    tipo_trd = _concepto(ex, "tipo-de-regla", "tabla-de-retencion", clase_tipo, "Tabla de retención documental")
    # Los instrumentos archivísticos también son documentos (fase 1 de RiC
    # completo, RiC-R021 y R064): el cuadro de clasificación y el documento de
    # cada versión de la TRD describen el fondo, y la regla se expresa en su documento.
    prop_forma, clase_forma = _apoyo("forma_documental")
    describe = _apoyo("describe")[0]

    def instrumento(nodo, titulo, clave_forma, nombre_forma, fecha):
        g.add((nodo, RDF.type, RICO[ric_o.CLASE_NIVEL["unidad_documental"]]))
        g.add((nodo, _a("titulo"), Literal(titulo)))
        g.add((nodo, RDFS.label, Literal(titulo)))
        g.add((nodo, prop_forma, _concepto(ex, "forma-documental-instrumento", clave_forma, clase_forma, nombre_forma)))
        g.add((nodo, describe, uri(ex.fondo.id)))
        if fecha:
            _fecha_libre(ex, nodo, _apoyo("fecha_creacion")[0], URIRef(f"{nodo}/fecha"), None, fecha.isoformat())

    primera = next((v.vigente_desde for v in versiones if v.vigente_desde), None)
    instrumento(uri(ex.fondo.id, "cuadro-de-clasificacion"), f"Cuadro de clasificación documental · {ex.fondo.titulo}",
                "cuadro-de-clasificacion", "Cuadro de clasificación documental", primera)
    for v in versiones:
        documento = uri(v.id, "documento")
        instrumento(documento, f"{v.nombre} · {ex.fondo.titulo}", "tabla-de-retencion-documental",
                    "Tabla de retención documental", v.fecha_aprobacion or v.vigente_desde)
        g.add((uri(v.id), _apoyo("expresada_en")[0], documento))
        if v.ente_vigilancia_id:  # quien vigila su aplicación (RiC-R066): el AGN o el consejo territorial
            ente = entidades.get(v.ente_vigilancia_id) or db.get(EntidadVocabulario, v.ente_vigilancia_id)
            if ente is not None and ente.estado == "activa" and ente.clase == "agente":
                if ente.id not in entidades:
                    entidades[ente.id] = ente
                    _entidad(db, ex, ente, entidades)
                g.add((uri(v.id), _apoyo("vigilada_por")[0], uri(ente.id)))
        nodo = uri(v.id)
        g.add((nodo, RDF.type, RICO[ric_o.CLASE_VOCABULARIO["regla"]]))
        g.add((nodo, _a("nombre"), Literal(v.nombre)))
        g.add((nodo, RDFS.label, Literal(v.nombre)))
        g.add((nodo, prop_tipo, tipo_trd))
        descripcion = " ".join(x for x in (
            f"Aprobada por {v.acto_aprobacion}" + (f" del {v.fecha_aprobacion.isoformat()}" if v.fecha_aprobacion else "")
            + "." if v.acto_aprobacion else None,
            f"Convalidación: {v.convalidacion}" + (f" del {v.fecha_convalidacion.isoformat()}" if v.fecha_convalidacion
                                                   else "") + "." if v.convalidacion else None,
            "Vigente." if v.estado == "vigente" else "Histórica: la reemplazó una versión posterior.") if x)
        g.add((nodo, _a("descripcion_general"), Literal(descripcion, lang="es")))
        if v.vigente_desde:
            _periodo(ex, nodo, f"{v.vigente_desde.isoformat()}/{v.vigente_hasta.isoformat() if v.vigente_hasta else ''}")
        g.add((nodo, RICO[ric_o.PROPIEDADES["regulates_or_regulated"].rico], uri(ex.fondo.id)))
        # Sus partes: las reglas de serie cuya vigencia cubre el primer día de la versión.
        for regla_id, vigencia in reglas:
            if v.vigente_desde and retencion._elegir_por_fecha(vigencia, v.vigente_desde):
                g.add((nodo, _apoyo("parte_regla")[0], uri(regla_id)))
        if v.acto_aprobacion:
            acto = uri(v.id, "acto")
            g.add((acto, RDF.type, RICO[ric_o.CLASE_VOCABULARIO["mandato"]]))
            g.add((acto, _a("titulo"), Literal(v.acto_aprobacion)))
            g.add((acto, RDFS.label, Literal(v.acto_aprobacion)))
            prop_m, clase_m = _apoyo("tipo_mandato")
            g.add((acto, prop_m, _concepto(ex, "tipo-de-mandato", "aprobacion-trd", clase_m,
                                           "Acto de aprobación de la TRD")))
            if v.fecha_aprobacion:
                _periodo(ex, acto, v.fecha_aprobacion.isoformat())
            g.add((acto, RICO[ric_o.PROPIEDADES["regulates_or_regulated"].rico], nodo))


def _instrumentos_aprobados(db: Session, ex: Exportacion, recursos: dict) -> None:
    """El FUID, la guía y el índice aprobados (no los anulados) como documentos que
    describen su nivel (RiC-R021), con su fecha de aprobación, su archivo con la
    huella (autenticidad) y, si reemplazó a otro, la secuencia entre versiones (RiC-R008)."""
    from app.models.instrumento_aprobado import TIPO_INSTRUMENTO, InstrumentoAprobado

    g = ex.grafo
    filas = db.scalars(select(InstrumentoAprobado).where(
        InstrumentoAprobado.fondo_id == ex.fondo.id, InstrumentoAprobado.estado != "anulado")).all()
    prop_forma, clase_forma = _apoyo("forma_documental")
    exportados = {i.id for i in filas if i.recurso_id in recursos}
    for i in filas:
        if i.id not in exportados:
            continue  # describe un nivel que esta exportación no incluye (restringido)
        doc = uri(i.id, "documento")
        g.add((doc, RDF.type, RICO[ric_o.CLASE_NIVEL["unidad_documental"]]))
        g.add((doc, _a("titulo"), Literal(i.titulo)))
        g.add((doc, RDFS.label, Literal(i.titulo)))
        g.add((doc, prop_forma, _concepto(ex, "forma-documental-instrumento", i.tipo, clase_forma,
                                          TIPO_INSTRUMENTO[i.tipo])))
        g.add((doc, _apoyo("describe")[0], uri(i.recurso_id)))
        estado = "Vigente." if i.estado == "vigente" else "Reemplazado por una versión posterior."
        acta = f" Aprobado en {i.acta}" + (f" del {i.fecha_acta.isoformat()}" if i.fecha_acta else "") + "." if i.acta else ""
        g.add((doc, _a("descripcion_general"), Literal(f"Versión {i.version}. {estado}{acta}", lang="es")))
        _fecha_libre(ex, doc, _apoyo("fecha_creacion")[0], URIRef(f"{doc}/fecha"), None,
                     i.aprobado_en.date().isoformat())
        archivo = uri(i.id)
        g.add((archivo, RDF.type, RICO[ric_o.CLASE_NODO["instanciacion"]]))
        g.add((archivo, _a("titulo"), Literal(i.titulo)))
        g.add((archivo, _a("identificador"), Literal(f"urn:uuid:{i.id}")))
        g.add((archivo, _a("autenticidad"), Literal(f"Huella SHA-256 del archivo aprobado: {i.huella}.", lang="es")))
        g.add((doc, RICO[ric_o.PROPIEDADES["has_or_had_instantiation"].rico], archivo))
        if i.reemplaza_id in exportados:
            g.add((uri(i.reemplaza_id, "documento"), RICO[ric_o.PROPIEDADES["precedes_or_preceded"].rico], doc))


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

    def accion(nodo, nombre, quien, archivo, cuando, clave_tipo, nombre_tipo):
        g.add((nodo, RDF.type, RICO[ric_o.CLASE_VOCABULARIO["actividad"]]))
        g.add((nodo, tipo, _tipo_tecnico(ex, clave_tipo, nombre_tipo)))
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
            g.add((nodo, _apoyo("resultado")[0], uri(m.instanciacion_resultado_id)))  # RiC-R061
            # La copia migrada cumple la misma función que el original (RiC-R035).
            g.add((uri(origen.id), _apoyo("equivalente")[0], uri(m.instanciacion_resultado_id)))


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


def _relacion(db: Session, ex: Exportacion, rel: Relacion, extremos, incluir_restringidos: bool = False) -> None:
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
    # La misma fila como nodo de relación (VOC-06 y brecha 1): vigencia, nota,
    # rol, fuente, certeza y estado no se pierden. Orientado como lo define RiC-O.
    clase = ric_o.clase_relacion(rel.codigo_ric, rel.rol) or ric_o.RELACION_GENERAL
    fuente, destino = (i_d, i_o) if rel.codigo_ric in ric_o.RELACION_INVERTIDA else (i_o, i_d)
    g, nodo = ex.grafo, uri(rel.id)
    g.add((nodo, RDF.type, RICO[clase]))
    g.add((nodo, RICO[ric_o.RELACION_ORIGEN], uri(fuente)))
    g.add((nodo, RICO[ric_o.RELACION_DESTINO], uri(destino)))
    g.add((nodo, RDFS.label, Literal(f"Relación {ric_o.etiqueta(rel.codigo_ric)}")))
    if rel.fecha_edtf:
        _periodo(ex, nodo, rel.fecha_edtf)
    descripcion = "; ".join(x for x in (f"Rol: {rel.rol.replace('_', ' ')}" if rel.rol else None, rel.nota) if x)
    if descripcion:
        g.add((nodo, _a("descripcion_general"), Literal(descripcion)))
    _procedencia_relacion(db, ex, nodo, rel, incluir_restringidos)
    _derivadas_de_relacion(ex, rel, n_o, n_d)
    if rel.codigo_ric == "has_or_had_holder" and rel.fecha_edtf:
        # RiC-O no reifica la custodia en una clase de relación con fechas: el
        # tramo queda en el sistema y la exportación lo cuenta (DES-05).
        ex.omitidas["periodo de un tramo de custodia (RiC-O no reifica la custodia)"] += 1


def _fisica(i: Instanciacion) -> bool:
    """Un original físico registrado (papel, plano…): no tiene archivo."""
    return i.estado == "registro_fisico" or not i.ruta


def _derivadas_de_relacion(ex: Exportacion, rel: Relacion, n_o, n_d) -> None:
    """Lo que una fila dice además en RiC-O 1.1 con propiedades más precisas
    (fase 1 de RiC completo), sin otra fuente que la fila y sus extremos."""
    g = ex.grafo
    if rel.codigo_ric == "has_or_had_instantiation" and isinstance(n_d, Instanciacion):
        # El original en papel y la copia digital (refinan hasOrHadInstantiation, RiC-AG).
        clave = "instanciacion_analogica" if _fisica(n_d) else "instanciacion_digital"
        g.add((uri(rel.origen_id), _apoyo(clave)[0], uri(rel.destino_id)))
        if _fisica(n_d) and getattr(n_o, "folios", None):
            # Extensión del soporte (RiC-A04): los folios del original, no del archivo digital.
            s = uri(rel.destino_id)
            g.add((s, _a("extension_soporte"), Literal(f"{n_o.folios} folios", lang="es")))
            _extension(ex, s, "extension_soporte", "folios", n_o.folios, "folios")
    elif rel.codigo_ric == "has_or_had_derived_instantiation" and isinstance(n_o, Instanciacion) \
            and isinstance(n_d, Instanciacion) and _fisica(n_o) and not _fisica(n_d):
        # Digitalización del original físico, como la modela RiC-AG: una actividad
        # que afecta al original y resulta en la copia digital.
        nodo = uri(rel.id, "digitalizacion")
        nombre = f"Digitalización de «{n_o.nombre_original}»"
        g.add((nodo, RDF.type, RICO[ric_o.CLASE_VOCABULARIO["actividad"]]))
        g.add((nodo, RDFS.label, Literal(nombre)))
        g.add((nodo, _a("nombre"), Literal(nombre)))
        g.add((nodo, RICO[ric_o.PROPIEDADES["has_activity_type"].rico], _tipo_tecnico(ex, "digitalizacion",
                                                                                         "Digitalización")))
        g.add((nodo, RICO[ric_o.ACCION_TECNICA["afecta"].rico], uri(n_o.id)))
        g.add((nodo, _apoyo("resultado")[0], uri(n_d.id)))
        if n_d.cargado_en is not None:
            _fecha_libre(ex, nodo, _apoyo("inicio")[0], URIRef(f"{nodo}/fecha"), None, n_d.cargado_en.date().isoformat())
    elif rel.codigo_ric == "has_copy" and isinstance(n_o, RecursoDocumental) and isinstance(n_d, RecursoDocumental) \
            and ric_o.CLASE_NIVEL[n_o.nivel] != "RecordSet" and ric_o.CLASE_NIVEL[n_d.nivel] != "RecordSet":
        g.add((uri(rel.origen_id), _apoyo("original_de")[0], uri(rel.destino_id)))  # RiC-R010, entre documentos
    elif rel.codigo_ric == "has_direct_subevent":
        # RiC-R006 (has or had subevent) junto al atajo directo de RiC-O.
        g.add((uri(rel.origen_id), _apoyo("subevento")[0], uri(rel.destino_id)))
    elif rel.codigo_ric == "affects_or_affected" and rel.rol == "disposicion" and rel.destino_tipo == "recurso_documental" \
            and getattr(n_o, "subtipo", None) == "eliminacion" and n_o.existencia_edtf:
        # Expediente eliminado: su fecha de destrucción, la del acta (RiC-AG).
        s = uri(rel.destino_id)
        _fecha_libre(ex, s, _apoyo("fecha_destruccion")[0], URIRef(f"{s}/destruccion"),
                     fechas.legible(n_o.existencia_edtf), n_o.existencia_edtf)


def _tipo_tecnico(ex: Exportacion, clave: str, nombre: str) -> URIRef:
    """Tipo de una acción técnica, en el esquema SKOS de los tipos de actividad del fondo."""
    g = ex.grafo
    concepto = _concepto(ex, "tipo-de-accion-tecnica", clave, RICO[ric_o.CLASE_VOCABULARIO["tipo_actividad"]], nombre)
    esquema = uri(ex.fondo.id, "tipos-de-actividad")
    g.add((esquema, RDF.type, SKOS.ConceptScheme))
    g.add((esquema, SKOS.prefLabel, Literal(f"Tipos de actividad (funciones) · {ex.fondo.titulo}")))
    g.add((concepto, RDF.type, SKOS.Concept))
    g.add((concepto, SKOS.prefLabel, Literal(nombre)))
    g.add((concepto, SKOS.inScheme, esquema))
    return concepto


def _procedencia_relacion(db: Session, ex: Exportacion, nodo: URIRef, rel: Relacion, incluir_restringidos: bool) -> None:
    """Fuente, certeza y estado de una relación (brecha 1 de la auditoría de
    especialización): lo que distingue una descripción asistida por IA."""
    g = ex.grafo
    if rel.origen == "persona":
        fuente = "Registrada por una persona."
    else:
        # El motor no se nombra: no se exporta como agente (decisión anterior, que se mantiene).
        fuente = ("Propuesta por el motor de análisis" + (", corregida" if rel.origen == "motor_editado" else "")
                  + " y confirmada por una persona.")
    if rel.fragmento and rel.fragmento_instanciacion_id:
        # El fragmento sale solo si el archivo del que se tomó no está restringido:
        # citarlo sería publicar parte de su contenido.
        archivo = db.get(Instanciacion, rel.fragmento_instanciacion_id)
        if archivo is not None and (incluir_restringidos or not derechos.instanciacion_restringida(db, archivo)):
            fuente += f" Fragmento del documento: «{rel.fragmento.strip()[:300]}»."
        else:
            ex.omitidas["fragmento citado de un archivo restringido (la fuente de la relación sale sin él)"] += 1
    g.add((nodo, _a("fuente_relacion"), Literal(fuente, lang="es")))
    # La certeza es la del motor: si una persona la corrigió, ya no es su propuesta.
    if rel.origen == "motor" and rel.confianza is not None:
        g.add((nodo, _a("certeza_relacion"),
               Literal(f"{ric_o.certeza(rel.confianza)} (confianza del motor: {rel.confianza:.2f})", lang="es")))
    estado = _estado_relacion(rel.fecha_edtf)
    if estado:
        g.add((nodo, _a("estado_relacion"), Literal(estado, lang="es")))


def _estado_relacion(edtf: str | None) -> str | None:
    """«terminada» si su vigencia acabó; «vigente» si empezó y no tiene fin."""
    if not edtf:
        return None
    try:
        f = fechas.interpretar(edtf)
    except fechas.FechaInvalida:
        return None
    if f.fin is not None and f.fin < ahora().date():
        return "terminada"
    if f.subtipo == "rango" and f.inicio is not None and f.fin is None:
        return "vigente"
    return None


# --- Nodos ------------------------------------------------------------------------------------------


def _tipo_fecha(ex: Exportacion, nodo: URIRef, subtipo: str | None) -> None:
    """rico:hasDateType (RiC-A42): fecha simple, rango o conjunto (brecha 3)."""
    if subtipo in ric_o.TIPO_FECHA:
        prop, clase = _apoyo("tipo_fecha")
        ex.grafo.add((nodo, prop, _concepto(ex, "tipo-de-fecha", subtipo, clase, ric_o.TIPO_FECHA[subtipo])))


def _subtipo_edtf(edtf: str | None) -> str | None:
    try:
        return fechas.subtipo_de(edtf) if edtf else None
    except fechas.FechaInvalida:
        return None


def _fecha_libre(ex: Exportacion, sujeto: URIRef, predicado: URIRef, nodo: URIRef, expresada: str | None,
                 edtf: str | None) -> None:
    g = ex.grafo
    g.add((nodo, RDF.type, RICO[ric_o.CLASE_NODO["fecha"]]))
    _tipo_fecha(ex, nodo, _subtipo_edtf(edtf))
    if expresada:
        g.add((nodo, _a("fecha_expresada"), Literal(expresada)))
    if edtf:
        g.add((nodo, _a("fecha_normalizada"), Literal(edtf)))
        calificador = "aproximada" if "~" in edtf or "%" in edtf else "incierta" if "?" in edtf else None
        if calificador:
            g.add((nodo, _a("calificador_fecha"), Literal(calificador)))
    g.add((sujeto, predicado, nodo))


def _periodo(ex: Exportacion, sujeto: URIRef, edtf: str | None, inicio_clave: str = "inicio", fin_clave: str = "fin",
             una: str = "fecha_asociada") -> None:
    """Existencia o periodo en EDTF: un intervalo da fecha de inicio y de
    fin (rico:hasBeginningDate / hasEndDate, o el nacimiento y la muerte de una
    persona); una sola fecha, fecha asociada (o la de ocurrencia de un hito).
    Las URI de los nodos no cambian con la propiedad."""
    if not edtf:
        return
    if "/" in edtf:
        inicio, fin = edtf.split("/", 1)
        for parte, clave, sufijo in ((inicio, inicio_clave, "inicio"), (fin, fin_clave, "fin")):
            if parte and parte != "..":
                _fecha_libre(ex, sujeto, _apoyo(clave)[0], URIRef(f"{sujeto}/{sufijo}"),
                             fechas.legible(parte), parte)
    else:
        _fecha_libre(ex, sujeto, _apoyo(una)[0], URIRef(f"{sujeto}/fecha"), fechas.legible(edtf), edtf)


TIPO_HITO_NOMBRE = {"creacion": "Creación", "reforma": "Reforma o reestructuración", "traslado": "Traslado",
                    "supresion": "Supresión o liquidación", "otro": "Otro hito"}


def _tipos_de_agente(ex: Exportacion, s: URIRef, e: EntidadVocabulario) -> None:
    """Tipo de entidad (RiC-A12), de familia (A20), ocupación (A30) y grupo demográfico
    (A15). El grupo demográfico es un dato sensible (Ley 1581, art. 5): solo sale en el
    grafo completo, nunca en el público ni en la consulta."""
    from app.models.descripcion import TIPO_ENTIDAD, TIPO_FAMILIA

    if e.clase != "agente":
        return
    g = ex.grafo

    def tipo(apoyo: str, grupo: str, clave: str, etiqueta: str, esquema: str) -> None:
        # Cada tipo en su esquema SKOS del fondo (RiC-AG); la ocupación, además, es
        # subclase de ActivityType en RiC-O y el perfil le exige etiqueta y esquema.
        prop, clase = _apoyo(apoyo)
        g.add((s, prop, _concepto_en_esquema(ex, grupo, clave, clase, etiqueta, esquema)))

    if e.subtipo == "entidad_corporativa" and e.tipo_entidad in TIPO_ENTIDAD:
        tipo("tipo_entidad", "tipo-de-entidad", e.tipo_entidad, TIPO_ENTIDAD[e.tipo_entidad], "Tipos de entidad")
    if e.subtipo == "familia" and e.tipo_familia in TIPO_FAMILIA:
        tipo("tipo_familia", "tipo-de-familia", e.tipo_familia, TIPO_FAMILIA[e.tipo_familia], "Tipos de familia")
    if e.subtipo == "persona" and e.ocupacion:
        tipo("ocupacion", "ocupacion", e.ocupacion, e.ocupacion, "Ocupaciones")
    if e.grupo_demografico and e.subtipo in ("persona", "grupo", "entidad_corporativa", "familia"):
        if ex.completa:
            tipo("grupo_demografico", "grupo-demografico", e.grupo_demografico, e.grupo_demografico,
                 "Grupos demográficos")
        else:
            ex.omitidas["grupo demográfico (dato sensible, Ley 1581: solo en el grafo completo)"] += 1


def _concepto_en_esquema(ex: Exportacion, grupo: str, clave: str, clase: URIRef, etiqueta: str,
                         esquema_nombre: str) -> URIRef:
    """Concepto con su esquema SKOS del fondo (uno por grupo)."""
    g = ex.grafo
    concepto = _concepto(ex, grupo, clave, clase, etiqueta)
    esquema = uri(ex.fondo.id, "esquema", grupo)
    g.add((esquema, RDF.type, SKOS.ConceptScheme))
    g.add((esquema, SKOS.prefLabel, Literal(f"{esquema_nombre} · {ex.fondo.titulo}")))
    g.add((concepto, RDF.type, SKOS.Concept))
    g.add((concepto, SKOS.prefLabel, Literal(etiqueta)))
    g.add((concepto, SKOS.inScheme, esquema))
    return concepto


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




NIVELES_CCD = ("seccion", "subseccion", "serie", "subserie")


def _codigo_ccd(r: RecursoDocumental, recursos: dict) -> str | None:
    """El código del cuadro de clasificación que califica la descripción: el
    propio en una sección, subsección, serie o subserie; el de la serie o
    subserie más cercana en un expediente, un documento o una parte."""
    actual, vistos = r, set()
    while actual is not None and actual.id not in vistos:
        vistos.add(actual.id)
        if actual.nivel in NIVELES_CCD:
            return actual.codigo_referencia
        if actual.nivel in ("fondo", "coleccion"):
            return None
        actual = recursos.get(actual.incluido_en_id)
    return None


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
    # Fase 1 de RiC completo. Clasificación (RiC-A07): el código del cuadro de
    # clasificación; un expediente o documento lleva el de su serie o subserie.
    codigo = _codigo_ccd(r, recursos)
    if codigo:
        g.add((s, _a("clasificacion"), Literal(codigo)))
    if r.nota_integridad:  # RiC-A24: completitud intelectual
        g.add((s, _a("integridad"), Literal(r.nota_integridad, lang="es")))
    if clase == "RecordSet":
        for forma_id in r.formas_miembros or []:  # tipos documentales de la TRD
            g.add((s, _apoyo("formas_miembros")[0], uri(forma_id)))
            ex.nodos.setdefault(forma_id, ("entidad_vocabulario", None))
        if r.fechas_predominantes_edtf:  # RiC-R083: las de la mayoría de sus documentos
            _fecha_libre(ex, s, _apoyo("fechas_mayoria")[0], URIRef(f"{s}/fechas-predominantes"),
                         fechas.legible(r.fechas_predominantes_edtf), r.fechas_predominantes_edtf)
    else:
        if r.estado_documento in ESTADO_DOCUMENTO:  # RiC-A39
            prop, clase_ap = _apoyo("estado_documento")
            g.add((s, prop, _concepto(ex, "estado-del-documento", r.estado_documento, clase_ap,
                                      ESTADO_DOCUMENTO[r.estado_documento])))
        if r.tipo_contenido in TIPO_CONTENIDO:  # RiC-A10
            prop, clase_ap = _apoyo("tipo_contenido")
            g.add((s, prop, _concepto(ex, "tipo-de-contenido", r.tipo_contenido, clase_ap,
                                      TIPO_CONTENIDO[r.tipo_contenido])))
    if r.folios:  # ISAD-G 3.1.5, RiC-A35: el texto y el nodo con cantidad y unidad (brecha 2)
        g.add((s, _a("extension"), Literal(f"{r.folios} folios", lang="es")))
        _extension(ex, s, "extension_recurso", "folios", r.folios, "folios")
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


# Esquemas SKOS por fondo (hallazgo VOC-04): funciones, formas documentales y tipos de parte.
ESQUEMAS_SKOS = {"tipo_actividad": ("tipos-de-actividad", "Tipos de actividad (funciones)"),
                 "forma_documental": ("formas-documentales", "Formas documentales"),
                 "tipo_parte": ("tipos-de-parte", "Tipos de parte documental"),
                 "materia": ("materias", "Materias")}


def _entidad(db: Session, ex: Exportacion, e: EntidadVocabulario, entidades: dict) -> None:
    g = ex.grafo
    s = uri(e.id)
    clase = ric_o.clase_de("entidad_vocabulario", clase=e.clase, subtipo=e.subtipo)
    g.add((s, RDF.type, RICO[clase]))
    g.add((s, RDFS.label, Literal(e.nombre)))
    # Un mandato lleva rico:title (especialización de rico:name que admite
    # Rule); lo demás, rico:name.
    g.add((s, _a("titulo" if e.clase == "mandato" else "nombre"), Literal(e.nombre)))
    if e.clase in ESQUEMAS_SKOS:
        # Cada concepto en su esquema, con sus otras formas, su código y su
        # nota de alcance (hallazgos VOC-03 y VOC-04).
        clave, titulo = ESQUEMAS_SKOS[e.clase]
        esquema = uri(ex.fondo.id, clave)
        g.add((s, RDF.type, SKOS.Concept))
        g.add((s, SKOS.prefLabel, Literal(e.nombre)))
        g.add((esquema, RDF.type, SKOS.ConceptScheme))
        g.add((esquema, SKOS.prefLabel, Literal(f"{titulo} · {ex.fondo.titulo}")))
        g.add((s, SKOS.inScheme, esquema))
        for n in db.scalars(select(NombreEntidad).where(NombreEntidad.entidad_id == e.id,
                                                        NombreEntidad.estado == "vigente")).all():
            g.add((s, SKOS.altLabel, Literal(n.nombre, lang=bcp47(n.idioma))))
        if e.historia:
            g.add((s, SKOS.scopeNote, Literal(e.historia)))
        if e.codigo_clasificacion:
            g.add((s, SKOS.notation, Literal(e.codigo_clasificacion)))
        if e.concepto_superior_id and e.concepto_superior_id in entidades:
            g.add((s, SKOS[ric_o.SKOS_BROADER], uri(e.concepto_superior_id)))
            g.add((uri(e.concepto_superior_id), SKOS.narrower, s))  # explícita: sin razonador también se ve
        elif not e.concepto_superior_id:
            g.add((esquema, SKOS.hasTopConcept, s))
    if e.clase == "materia" and e.concepto_tesauro_id:
        # La materia normalizada apunta al concepto del tesauro de origen (UNESCO, Minambiente…).
        from app.models.tesauro import ConceptoTesauro

        c = db.get(ConceptoTesauro, e.concepto_tesauro_id)
        if c is not None and (c.uri or "").startswith(("http://", "https://")):
            g.add((s, SKOS.exactMatch, URIRef(c.uri)))
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
        # De una persona, el inicio y el fin de su existencia son su nacimiento y su
        # muerte (RiC-R070 y R072): las propiedades más específicas, como pide RiC-O.
        _periodo(ex, s, e.existencia_edtf, *(("nacimiento", "muerte") if e.subtipo == "persona" else ()))
    _tipos_de_agente(ex, s, e)
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
        hitos = db.scalars(select(Hito).where(Hito.agente_id == e.id, Hito.estado == "vigente")
                           .order_by(Hito.inicio, Hito.edtf)).all()
        anterior = None
        for h in hitos:
            nodo = uri(h.id)
            g.add((nodo, RDF.type, RICO[ric_o.CLASE_NODO["hito"]]))
            g.add((nodo, _a("nombre"), Literal(h.descripcion)))
            g.add((nodo, RDFS.label, Literal(h.descripcion)))
            g.add((nodo, RICO[ric_o.PROPIEDADES["affects_or_affected"].rico], s))
            # Una fecha: la de su ocurrencia (RiC-R084); un periodo: inicio y fin.
            _periodo(ex, nodo, h.edtf, una="ocurrio")
            prop, clase_ap = _apoyo("tipo_evento")  # RiC-A18
            g.add((nodo, prop, _concepto(ex, "tipo-de-evento", h.tipo, clase_ap, TIPO_HITO_NOMBRE.get(h.tipo, h.tipo))))
            # La línea de tiempo del agente, en orden (RiC-R009): cada hito fechado precede al siguiente.
            if h.inicio is not None:
                if anterior is not None:
                    g.add((uri(anterior.id), _apoyo("precede_en_el_tiempo")[0], nodo))
                anterior = h
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
    _tipo_fecha(ex, s, _subtipo_edtf(f.edtf) or f.subtipo)
    if f.edtf:
        g.add((s, _a("fecha_normalizada"), Literal(f.edtf)))
        calificador = "aproximada" if "~" in f.edtf or "%" in f.edtf else "incierta" if "?" in f.edtf else None
        if calificador:
            g.add((s, _a("calificador_fecha"), Literal(calificador)))
    if f.calendario and f.calendario != "gregoriano":
        ex.omitidas["calendario distinto del gregoriano (sin propiedad en RiC-O)"] += 1
    ex.nodos[f.id] = ("fecha", "Date")


def _extension(ex: Exportacion, sujeto: URIRef, clave: str, sufijo: str, cantidad: int, unidad: str) -> None:
    """Extensión como nodo rico:Extent con cantidad legible por máquina y su
    unidad (brecha 2), además del texto que ya se exportaba."""
    prop, clase = _apoyo(clave)
    nodo = URIRef(f"{sujeto}/extension/{sufijo}")
    g = ex.grafo
    g.add((nodo, RDF.type, clase))
    # Forma canónica del decimal («12.0»): Turtle y JSON-LD la leen igual.
    g.add((nodo, _a("cantidad"), Literal(f"{cantidad}.0", datatype=XSD.decimal)))
    g.add((nodo, _a("unidad"), Literal(unidad, lang="es")))
    g.add((nodo, RDFS.label, Literal(f"{cantidad} {unidad}", lang="es")))
    g.add((sujeto, prop, nodo))


def _notas_de_preservacion(db: Session, ex: Exportacion, i: Instanciacion, s: URIRef) -> None:
    """Lo que el sistema sabe de la calidad, la autenticidad y la derivación
    del archivo, en las propiedades de RiC-O que lo dicen (brecha 2)."""
    from app.models.preservacion import ComprobacionTecnica, VerificacionIntegridad

    g = ex.grafo
    if i.origen_texto == "ocr" and i.confianza_ocr is not None:  # RiC-A34
        g.add((s, _a("calidad_representacion"), Literal(
            f"Texto obtenido por reconocimiento óptico de caracteres (OCR) con confianza media de "
            f"{i.confianza_ocr:.0f} sobre 100" + (": baja, la transcripción puede tener errores." if i.ocr_baja_confianza
                                                  else "."), lang="es")))
    partes = []
    if i.huella:
        partes.append(f"Huella {i.algoritmo_huella} al ingresar: {i.huella}.")
    v = db.scalar(select(VerificacionIntegridad).where(VerificacionIntegridad.instanciacion_id == i.id)
                  .order_by(VerificacionIntegridad.fecha.desc()).limit(1))
    if v is not None:
        partes.append(f"Última verificación de integridad ({v.fecha:%Y-%m-%d}): copia primaria {v.resultado}; "
                      f"segunda copia {v.segunda_copia_resultado or 'no verificada'}.")
    c = db.scalar(select(ComprobacionTecnica).where(ComprobacionTecnica.instanciacion_id == i.id,
                                                    ComprobacionTecnica.tipo == "validacion")
                  .order_by(ComprobacionTecnica.realizada_en.desc()).limit(1))
    if c is not None and c.resultado in ("conforme", "no_conforme"):
        partes.append(f"Validación del formato con {c.herramienta} ({c.realizada_en:%Y-%m-%d}): {c.resumen}")
    if partes:  # RiC-A03
        g.add((s, _a("autenticidad"), Literal(" ".join(partes), lang="es")))
    migrada = db.scalar(select(Migracion).where(Migracion.instanciacion_origen_id == i.id,
                                                Migracion.estado == "completada", Migracion.terminada_en.is_not(None))
                        .order_by(Migracion.terminada_en).limit(1))
    if migrada is not None:
        g.add((s, _a("fecha_migracion"), Literal(migrada.terminada_en.date().isoformat(), datatype=XSD.date)))
    origen = db.scalar(select(Migracion).where(Migracion.instanciacion_resultado_id == i.id)) if i.derivada_de_id else None
    derivada_en = (origen.terminada_en if origen is not None and origen.terminada_en else
                   i.cargado_en if i.recorte_de_id or i.derivada_de_id else None)
    if derivada_en is not None:
        g.add((s, _a("fecha_derivacion"), Literal(derivada_en.date().isoformat(), datatype=XSD.date)))


def _representacion(i: Instanciacion) -> tuple[str, str]:
    """Tipo de representación (RiC-A37): cómo se registra el contenido. Un
    original en papel no necesita un aparato para leerse; un archivo digital sí,
    y se distingue la imagen (también un escaneo con OCR) del texto codificado."""
    if _fisica(i):
        return "analogica", "Analógica (se lee sin un aparato)"
    mime = (i.formato_mime or "").lower()
    if mime == "image/svg+xml":
        return "digital-vectorial", "Digital: imagen vectorial"
    if mime.startswith("image/") or i.origen_texto == "ocr":
        return "digital-mapa-de-bits", "Digital: imagen de mapa de bits"
    if mime.startswith("audio/"):
        return "digital-audio", "Digital: audio"
    if mime.startswith("video/"):
        return "digital-video", "Digital: video"
    if i.origen_texto == "capa_de_texto" or mime.startswith("text/"):
        return "digital-texto", "Digital: texto codificado"
    return "digital", "Digital"


def _ubicacion(ex: Exportacion, i: Instanciacion, s: URIRef) -> None:
    """La signatura topográfica del original (depósito, estante, entrepaño y la
    ubicación escrita) como un lugar con su localización textual (RiC-A27): la
    instanciación tiene o tuvo esa ubicación (rico:hasOrHadLocation)."""
    from app.servicios.descripcion import signatura_topografica

    texto = "; ".join(x for x in (signatura_topografica(i), i.ubicacion_fisica) if x)
    if not texto:
        return
    g, nodo = ex.grafo, URIRef(f"{s}/ubicacion")
    prop, clase = _apoyo("ubicacion")
    g.add((nodo, RDF.type, clase))
    g.add((nodo, _a("nombre"), Literal(f"Ubicación de «{i.nombre_original}»")))
    g.add((nodo, RDFS.label, Literal(f"Ubicación de «{i.nombre_original}»")))
    g.add((nodo, _a("localizacion"), Literal(texto, lang="es")))
    prop_tipo, clase_tipo = _apoyo("tipo_lugar")
    g.add((nodo, prop_tipo, _concepto(ex, "tipo-de-lugar", "ubicacion-topografica", clase_tipo,
                                      "Ubicación topográfica en el depósito de archivo")))
    g.add((s, prop, nodo))


def _instanciacion(db: Session, ex: Exportacion, i: Instanciacion) -> None:
    g = ex.grafo
    s = uri(i.id)
    g.add((s, RDF.type, RICO[ric_o.CLASE_NODO["instanciacion"]]))
    g.add((s, _a("titulo"), Literal(i.nombre_original)))
    g.add((s, RDFS.label, Literal(i.nombre_original)))
    g.add((s, _a("identificador"), Literal(f"urn:uuid:{i.id}")))
    if i.tamano_bytes is not None:
        extension = f"{i.tamano_bytes} bytes" + (f"; {i.paginas} página(s)" if i.paginas else "")
        g.add((s, _a("extension_instanciacion"), Literal(extension)))
        _extension(ex, s, "extension_archivo", "bytes", i.tamano_bytes, "bytes")
        if i.paginas:
            _extension(ex, s, "extension_archivo", "paginas", i.paginas, "páginas")
    if i.soporte:  # original físico: su tipo de soporte (RiC-A05, rico:CarrierType)
        prop, clase_ap = _apoyo("tipo_soporte")
        g.add((s, prop, _concepto(ex, "tipo-de-soporte", i.soporte, clase_ap, i.soporte.replace("_", " ").capitalize())))
    # ISAD-G 3.4.4 (hallazgo DES-07), RiC-A31. El estado de conservación del
    # AGN (tabla 4) va en la misma nota: RiC-CM define Physical
    # Characteristics como «apariencia y estado físico», y no tiene otro atributo.
    nota_fisica = "; ".join(x for x in (
        f"Estado de conservación: {i.estado_conservacion}" if i.estado_conservacion else None,
        i.caracteristicas_fisicas) if x)
    if nota_fisica:
        g.add((s, _a("caracteristicas_fisicas"), Literal(nota_fisica)))
    _ubicacion(ex, i, s)
    if i.tecnica_produccion in TECNICA_PRODUCCION:  # RiC-A33: el texto y el tipo controlado
        nombre = TECNICA_PRODUCCION[i.tecnica_produccion]
        g.add((s, _a("tecnica_produccion"), Literal(nombre, lang="es")))
        prop, clase_ap = _apoyo("tipo_tecnica")
        g.add((s, prop, _concepto(ex, "tecnica-de-produccion", i.tecnica_produccion, clase_ap, nombre)))
    clave, nombre = _representacion(i)  # RiC-A37
    prop, clase_ap = _apoyo("tipo_representacion")
    g.add((s, prop, _concepto(ex, "tipo-de-representacion", clave, clase_ap, nombre)))
    if i.formato_puid:
        # El formato identificado, con su ficha en el registro PRONOM.
        g.add((s, RDFS.seeAlso, URIRef(f"https://www.nationalarchives.gov.uk/PRONOM/{i.formato_puid}")))
    _notas_de_preservacion(db, ex, i, s)
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
