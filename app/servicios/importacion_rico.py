"""
Importar un fondo descrito en RiC-O 1.1 desde otro sistema (Turtle, RDF/XML,
JSON-LD o N-Triples).

Es el espejo de `exportacion_rico`: lee las mismas clases y propiedades que el
sistema escribe y las lleva a sus tablas por los mismos caminos que usa una
persona, sin atajos:

1. La jerarquía de rico:RecordSet (fondo, secciones, subsecciones, series y
   subseries, por rico:hasRecordSetType o deducidas de su lugar en el árbol) se
   convierte en las filas del CCD y la TRD, y el fondo se registra con ellas como
   en el asistente: el cuadro sale de la parametrización (versión 1 de la TRD).
   La retención y los tipos documentales se leen si vienen en el texto de la regla
   y del alcance (así los escribe RICORA; RiC-O no tiene propiedades para años).
2. Agentes, lugares, formas documentales, actividades, tipos de actividad,
   mandatos y materias van al vocabulario del fondo (sin duplicar por nombre).
3. Expedientes (rst:File) y documentos (rico:Record) se crean dentro de su serie o
   subserie, con título, código, alcance, historia, condiciones y fechas.
4. Cada tripleta entre dos nodos importados cuya propiedad (o su inversa) está en
   el catálogo de relaciones del sistema se guarda como relación, si el dominio y
   el rango la admiten.

Lo que no se puede llevar se cuenta en «omitidas», con el motivo (los archivos de
las instanciaciones no viajan en el RDF, las partes documentales, la vigencia de
los nodos de relación…). Todo se hace en un punto de guardado: el resultado se
valida contra la ontología y el perfil SHACL y, si no es conforme, no queda nada.
"""

import hashlib
import io
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field

from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import cuadro, fechas, ric_o
from app.servicios.auditoria import registrar

RICO = Namespace(ric_o.RICO)
RST = Namespace(ric_o.RST)
SKOS = Namespace(ric_o.SKOS)
MAX_BYTES = 50 * 1024 * 1024
FORMATOS = {".ttl": "turtle", ".turtle": "turtle", ".rdf": "xml", ".xml": "xml", ".owl": "xml",
            ".jsonld": "json-ld", ".json": "json-ld", ".nt": "nt"}

# Tipo de agrupación (rico:hasRecordSetType) → nivel. Los propios del sistema
# (sección, subsección, subserie) se reconocen por su etiqueta.
NIVEL_TIPO = {"Fonds": "fondo", "Subfonds": "seccion", "Series": "serie", "Subseries": "subserie", "File": "expediente",
              "Collection": "coleccion"}
NIVEL_ETIQUETA = {"seccion": "seccion", "subseccion": "subseccion", "subserie": "subserie", "serie": "serie",
                  "fondo": "fondo", "expediente": "expediente", "coleccion": "coleccion"}

# Clase de RiC-O → (clase del vocabulario, subtipo).
CLASE_ENTIDAD = {**{v: ("agente", k) for k, v in ric_o.CLASE_AGENTE.items()}, "Agent": ("agente", None),
                 **{v: (k, None) for k, v in ric_o.CLASE_VOCABULARIO.items() if k not in ("tipo_parte", "regla")}}
CLASE_ENTIDAD["Concept"] = ("materia", None)

# Rol con que el sistema guarda cada relación (el que la pantalla de descripción espera).
ROL = {"has_creator": "productor", "has_sender": "remitente", "has_addressee": "destinatario", "has_author": "autor",
       "has_accumulator": "acumulador", "has_or_had_holder": "custodio"}
CATEGORIA = {"has_creator": "procedencia", "has_sender": "procedencia", "has_addressee": "procedencia",
             "has_author": "procedencia", "has_accumulator": "procedencia", "has_or_had_holder": "procedencia",
             "is_or_was_location_of": "espacial", "contains_or_contained": "espacial",
             "has_successor": "temporal", "precedes_or_preceded": "temporal"}
# Propiedades que la importación lleva por otro camino (jerarquía, fechas, retención) o no lleva.
ESTRUCTURALES = {"includes_or_included", "has_or_had_constituent", "has_or_had_instantiation", "migrated_into",
                 "has_or_had_derived_instantiation", "is_creation_date_of", "is_date_associated_with",
                 "regulates_or_regulated"}
DISPOSICION_TEXTO = {"conservación total": "ct", "eliminación": "e", "selección": "s",
                     "reproducción por medio técnico": "m", "medio técnico": "m"}


class ErrorImportacion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def _local(u) -> str:
    return re.split(r"[#/]", str(u))[-1]


def leer(contenido: bytes, archivo: str) -> Graph:
    if len(contenido) > MAX_BYTES:
        raise ErrorImportacion("El archivo supera los 50 MB.", 413)
    extension = ("." + archivo.rsplit(".", 1)[-1].lower()) if "." in archivo else ""
    formato = FORMATOS.get(extension)
    if formato is None:
        raise ErrorImportacion("Use un archivo RiC-O en Turtle (.ttl), RDF/XML (.rdf), JSON-LD (.jsonld) o N-Triples (.nt).")
    g = Graph()
    try:
        g.parse(io.BytesIO(contenido), format=formato)
    except Exception as exc:  # rdflib lanza errores de varios tipos según el formato
        raise ErrorImportacion(f"El archivo no se pudo leer como {formato}: {str(exc)[:200]}") from exc
    if not any(str(o).startswith(str(RICO)) for o in g.objects(None, RDF.type)):
        raise ErrorImportacion("El archivo no tiene ninguna clase de RiC-O (https://www.ica.org/standards/RiC/ontology#).")
    return g


def _texto(g: Graph, s, *props) -> str | None:
    """El primer valor de las propiedades, en español si hay varios idiomas."""
    for p in props:
        valores = [o for o in g.objects(s, p) if isinstance(o, Literal)]
        if valores:
            es = [v for v in valores if (v.language or "").startswith("es")]
            return " ".join(str((es or valores)[0]).split()) or None
    return None


def _nombre(g: Graph, s) -> str | None:
    return _texto(g, s, RICO.title, RICO.name, SKOS.prefLabel, RDFS.label)


@dataclass
class Nodo:
    uri: URIRef
    clase: str
    nivel: str | None = None
    titulo: str = ""
    padre: URIRef | None = None
    hijos: list = field(default_factory=list)


@dataclass
class Analisis:
    grafo: Graph
    fondo: Nodo | None
    recursos: dict
    entidades: dict  # uri → (clase, subtipo, nombre)
    filas: list[dict]
    omitidas: Counter
    problemas: list[str]

    def productor(self) -> str | None:
        """El productor del fondo: la sugerencia para la sección de las series sin ella."""
        if self.fondo is None:
            return None
        g = self.grafo
        for a in list(g.objects(self.fondo.uri, RICO.hasCreator)) + list(g.subjects(RICO.isCreatorOf, self.fondo.uri)):
            if a in self.entidades:
                return self.entidades[a][2]
        return None

    def resumen(self) -> dict:
        niveles = Counter(n.nivel for n in self.recursos.values())
        clases = Counter(c for c, _, _ in self.entidades.values())
        return {"fondo": self.fondo.titulo if self.fondo else None, "niveles": dict(niveles),
                "entidades": dict(clases), "filas_cuadro": len(self.filas),
                "filas_con_problemas": sum(1 for f in self.filas if f["problemas"]),
                "series_sin_seccion": sum(1 for f in self.filas if not f["seccion"]),
                "productor_sugerido": self.productor(),
                "omitidas": dict(self.omitidas), "problemas": self.problemas}


def _nivel_declarado(g: Graph, s) -> str | None:
    for tipo in g.objects(s, RICO.hasRecordSetType):
        if str(tipo).startswith(str(RST)):
            return NIVEL_TIPO.get(_local(tipo))
        etiqueta = cuadro._n(_nombre(g, tipo) or "")
        if etiqueta in NIVEL_ETIQUETA:
            return NIVEL_ETIQUETA[etiqueta]
        for amplio in g.objects(tipo, SKOS.broadMatch):
            return {"Fonds": "seccion", "Series": "subserie"}.get(_local(amplio))
    return None


def analizar(g: Graph, seccion: dict | None = None) -> Analisis:
    """`seccion` ({codigo, nombre}): la dependencia productora de las series que
    cuelgan directo del fondo (muchos sistemas no usan secciones; el CCD sí)."""
    omitidas: Counter = Counter()
    problemas: list[str] = []
    recursos: dict[URIRef, Nodo] = {}
    for s in set(g.subjects(RDF.type, RICO.RecordSet)):
        recursos[s] = Nodo(s, "RecordSet", _nivel_declarado(g, s), _nombre(g, s) or "")
    for s in set(g.subjects(RDF.type, RICO.Record)):
        recursos[s] = Nodo(s, "Record", "unidad_documental", _nombre(g, s) or "")
    omitidas["partes documentales (rico:RecordPart)"] += len(set(g.subjects(RDF.type, RICO.RecordPart)))
    for padre, hijo in list(g.subject_objects(RICO.includesOrIncluded)) + \
            [(o, s) for s, o in g.subject_objects(RICO.isOrWasIncludedIn)]:
        if padre in recursos and hijo in recursos and recursos[hijo].padre is None and padre != hijo:
            recursos[hijo].padre = padre
    for n in recursos.values():
        if n.padre:
            recursos[n.padre].hijos.append(n)
    raices = [n for n in recursos.values() if n.padre is None and n.clase == "RecordSet"]
    fondos = [n for n in raices if n.nivel == "fondo"] or [n for n in raices if n.hijos]
    fondo = fondos[0] if len(fondos) == 1 else None
    if not fondos:
        problemas.append("No hay un rico:RecordSet de nivel fondo (rst:Fonds) en la raíz del árbol.")
    elif len(fondos) > 1:
        problemas.append(f"El archivo trae {len(fondos)} fondos: impórtelos uno por uno.")
    if fondo is not None:
        fondo.nivel = "fondo"
        _deducir(fondo)
        sueltos = [n for n in recursos.values() if n is not fondo and not _desciende(n, fondo, recursos)]
        if sueltos:
            omitidas["descripciones fuera del árbol del fondo"] += len(sueltos)
    entidades = {}
    for s, clase in g.subject_objects(RDF.type):
        nombre_clase = _local(clase)
        if not str(clase).startswith(str(RICO)) or nombre_clase not in CLASE_ENTIDAD or s in entidades:
            continue
        if nombre_clase == "Concept" and (s, RDF.type, RICO.ActivityType) in g:
            continue  # el tipo de actividad también es skos:Concept: ya está
        if nombre_clase == "Mechanism":
            omitidas["mecanismos (software): el sistema registra los suyos"] += 1
            continue
        nombre = _nombre(g, s)
        if not nombre:
            omitidas[f"rico:{nombre_clase} sin nombre"] += 1
            continue
        entidades[s] = (*CLASE_ENTIDAD[nombre_clase], nombre)
    omitidas["instanciaciones: los archivos no viajan en el RDF (cárguelos en Carga de documentos)"] += \
        len(set(g.subjects(RDF.type, RICO.Instantiation)))
    filas = _filas_cuadro(g, fondo, recursos, seccion) if fondo else []
    if fondo is not None and not filas:
        problemas.append("El fondo no trae series: sin cuadro de clasificación no se registra.")
    return Analisis(g, fondo, recursos, entidades, filas, +omitidas, problemas)


def _desciende(n: Nodo, raiz: Nodo, recursos: dict) -> bool:
    vistos = set()
    while n.padre is not None and n.padre not in vistos:
        vistos.add(n.padre)
        if n.padre == raiz.uri:
            return True
        n = recursos[n.padre]
    return False


def _solo_documentos(n: Nodo) -> bool:
    return bool(n.hijos) and all(h.clase == "Record" for h in n.hijos)


def _deducir(n: Nodo) -> None:
    """Nivel de lo que no lo declara, por su lugar en el árbol (de arriba abajo): un
    conjunto que solo tiene documentos es un expediente (o una serie, si cuelga del
    fondo o de una sección); el que tiene expedientes o documentos, una serie; el que
    solo tiene conjuntos de conjuntos, una sección."""
    for h in n.hijos:
        if h.nivel is None and h.clase == "RecordSet":
            en_serie = n.nivel in ("serie", "subserie")
            expedientes = [x for x in h.hijos if x.clase == "RecordSet" and (x.nivel == "expediente" or _solo_documentos(x))]
            if _solo_documentos(h) or not h.hijos:
                h.nivel = "expediente" if en_serie else "serie"
            elif expedientes or any(x.clase == "Record" for x in h.hijos):
                h.nivel = "subserie" if n.nivel == "serie" else "expediente" if n.nivel == "subserie" else "serie"
            else:
                h.nivel = "subseccion" if n.nivel == "seccion" else "seccion"
        elif h.nivel == "serie" and n.nivel == "serie":
            h.nivel = "subserie"
        elif h.nivel == "seccion" and n.nivel == "seccion":
            h.nivel = "subseccion"
        _deducir(h)


def _regla(g: Graph, s) -> tuple[int | None, int | None, str | None, list[str], str | None]:
    """Retención de la regla que regula la serie, si su texto la dice (así la escribe RICORA)."""
    reglas = set(g.subjects(RICO.regulatesOrRegulated, s)) | set(g.objects(s, RICO.isOrWasRegulatedBy))
    for r in reglas:
        if (r, RDF.type, RICO.Rule) not in g:
            continue
        texto = _texto(g, r, RICO.generalDescription, RDFS.label) or ""
        ag = re.search(r"(\d+)\s*año\(s\) en el archivo de gestión", texto)
        ac = re.search(r"(\d+)\s*año\(s\) en el archivo central", texto)
        disp = re.search(r"disposición final:\s*([a-záéíóúñ ]+)", texto.lower())
        clave = DISPOSICION_TEXTO.get(disp.group(1).strip().rstrip(".")) if disp else None
        procedimiento = _texto(g, r, RICO.history)
        if ag or ac or clave:
            return (int(ag.group(1)) if ag else None, int(ac.group(1)) if ac else None, clave, [], procedimiento)
    return None, None, None, [], None


def _filas_cuadro(g: Graph, fondo: Nodo, recursos: dict, seccion: dict | None = None) -> list[dict]:
    filas = []

    def nodo(n: Nodo | None):
        return {"codigo": _texto(g, n.uri, RICO.identifier), "nombre": n.titulo} if n else None

    def subir(n: Nodo, nivel: str) -> Nodo | None:
        while n.padre is not None:
            n = recursos[n.padre]
            if n.nivel == nivel:
                return n
        return None

    hojas = [n for n in recursos.values() if n.nivel == "subserie"] + \
            [n for n in recursos.values() if n.nivel == "serie" and not any(h.nivel == "subserie" for h in n.hijos)]
    for i, h in enumerate(sorted(hojas, key=lambda x: (_texto(g, x.uri, RICO.identifier) or "", x.titulo)), start=1):
        if not _desciende(h, fondo, recursos):
            continue
        serie = subir(h, "serie") if h.nivel == "subserie" else h
        ag, ac, disposicion, _, procedimiento = _regla(g, h.uri)
        alcance = _texto(g, h.uri, RICO.scopeAndContent) or ""
        tipos = [t.strip().rstrip(".") for t in alcance.split(":", 1)[1].split(";")] \
            if alcance.lower().startswith("tipos documentales:") else []
        funciones = [_nombre(g, a) for a in set(g.subjects(RICO.isRelatedTo, h.uri)) | set(g.objects(h.uri, RICO.isRelatedTo))
                     if (a, RDF.type, RICO.ActivityType) in g]
        fila = cuadro.FilaCuadro.de_dict({
            "fila": i, "seccion": nodo(subir(h, "seccion")) or seccion, "subseccion": nodo(subir(h, "subseccion")),
            "serie": nodo(serie), "subserie": nodo(h) if h.nivel == "subserie" else None,
            "tipos": [t for t in tipos if t], "gestion": ag, "central": ac, "disposicion": disposicion,
            "procedimiento": procedimiento, "funcion": next((f for f in funciones if f), None)})
        filas.append(fila.a_dict())
    return filas


def vista_previa(contenido: bytes, archivo: str, seccion: dict | None = None) -> dict:
    a = analizar(leer(contenido, archivo), seccion)
    return a.resumen() | {"filas": a.filas, "huella": hashlib.sha256(contenido).hexdigest()}


# --- Aplicar -------------------------------------------------------------------------------------------


def importar(db: Session, contenido: bytes, archivo: str, usuario_id: uuid.UUID, *, titulo: str | None = None,
             version: dict | None = None, seccion: dict | None = None, crear: bool = False) -> dict:
    """Registra el fondo con su cuadro (por la parametrización) y lleva el resto del grafo
    a las tablas. Con `crear=False` solo valida. Nada queda a medias: si algo falla o el
    resultado no es conforme con RiC-O 1.1, se deshace."""
    from app.servicios import fondos, parametrizacion_trd

    a = analizar(leer(contenido, archivo), seccion)
    if a.problemas:
        raise ErrorImportacion(" ".join(a.problemas))
    malas = [f for f in a.filas if f["problemas"]]
    if malas:
        raise ErrorImportacion(f"{len(malas)} serie(s) del cuadro con problemas (la primera: "
                               f"{malas[0]['serie']['nombre'] if malas[0]['serie'] else '?'}: {malas[0]['problemas'][0]})")
    g, raiz = a.grafo, a.fondo
    punto = db.begin_nested()
    try:
        fondo = fondos.crear(db, titulo=titulo or raiz.titulo, nota=_texto(g, raiz.uri, RICO.generalDescription),
                             fechas_extremas=_fechas(g, raiz.uri)[0], usuario_id=usuario_id, origen=f"RiC-O: {archivo}")
        _campos(g, raiz.uri, fondo)
        informe, validacion, parametrizado, completa = parametrizacion_trd.configurar_cuadro_nuevo(
            db, fondo, a.filas, usuario_id, version)
        if not completa:
            parametrizado = parametrizacion_trd.primera_version(db, fondo, a.filas, usuario_id, informe)
        hecho = _contenido(db, a, fondo, usuario_id, archivo)
        validacion = cuadro.validar_rico(db, fondo)
        registrar(db, modulo="instrumentos", accion="rico_importado", usuario_id=usuario_id,
                  entidad_tipo="recurso_documental", entidad_id=fondo.id,
                  detalle=f"Fondo «{fondo.titulo}» importado de {archivo}",
                  nuevo={"huella": hashlib.sha256(contenido).hexdigest(), **{k: v for k, v in hecho.items()
                                                                             if k != "omitidas"}})
    except (fondos.ErrorFondo, parametrizacion_trd.ErrorTrd, cuadro.ErrorCuadro) as exc:
        punto.rollback()
        raise ErrorImportacion(str(exc), getattr(exc, "codigo", 422)) from exc
    except Exception:
        punto.rollback()
        raise
    creado = crear and validacion["conforme"]
    salida = {"creado": creado, "fondo": {"id": str(fondo.id), "titulo": fondo.titulo} if creado else None,
              "cuadro": {k: v for k, v in informe.items() if k != "_nuevos"}, "parametrizacion": parametrizado,
              "contenido": hecho, "omitidas": dict(a.omitidas + Counter(hecho["omitidas"])), "validacion": validacion,
              "version": parametrizacion_trd.estado_version_1(db, fondo) if creado else None}
    if creado:
        punto.commit()
    else:
        punto.rollback()
    return salida


def _fechas(g: Graph, s) -> tuple[str | None, str | None]:
    """(expresión, EDTF) de la fecha de creación o las extremas del nodo."""
    for p in (RICO.hasOrHadAllMembersWithCreationDate, RICO.hasCreationDate, RICO.isAssociatedWithDate):
        for d in g.objects(s, p):
            if isinstance(d, Literal):
                return str(d), None
            edtf = _texto(g, d, RICO.normalizedDateValue)
            expresion = _texto(g, d, RICO.expressedDate) or edtf
            if edtf:
                try:
                    edtf = fechas.interpretar(edtf).edtf
                except fechas.FechaInvalida:
                    edtf = None
            return expresion, edtf
    return None, None


def _campos(g: Graph, s, r: RecursoDocumental) -> None:
    for atributo, columna in (("scopeAndContent", "alcance_contenido"), ("conditionsOfAccess", "condiciones_acceso"),
                              ("conditionsOfUse", "condiciones_uso"), ("history", "historia_archivistica"),
                              ("structure", "organizacion"), ("accruals", "nuevos_ingresos")):
        valor = _texto(g, s, RICO[atributo])
        if valor and not getattr(r, columna, None):
            setattr(r, columna, valor)
    expresion, edtf = _fechas(g, s)
    if expresion and not r.fechas_extremas:
        r.fechas_extremas, r.fechas_extremas_edtf = expresion[:60], edtf


def _contenido(db: Session, a: Analisis, fondo: RecursoDocumental, usuario_id: uuid.UUID, archivo: str) -> dict:
    """Vocabulario, expedientes, documentos y relaciones, una vez creado el cuadro."""
    from sqlalchemy import select

    from app.servicios import descripcion

    g = a.grafo
    omitidas: Counter = Counter()
    mapa: dict[URIRef, tuple[str, uuid.UUID, str]] = {a.fondo.uri: ("recurso_documental", fondo.id, "RecordSet")}
    # El cuadro ya creado: cada agrupación por su código o, si no lo tiene, por título bajo su superior.
    existentes = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo.id)).all()
    por_codigo = {r.codigo_referencia: r for r in existentes if r.codigo_referencia}
    for n in _orden(a.fondo, a.recursos):
        if n.nivel not in descripcion.NIVELES_CUADRO:
            continue
        codigo = _texto(g, n.uri, RICO.identifier)
        padre = mapa.get(n.padre)
        r = por_codigo.get(codigo) if codigo else None
        if r is None:
            # Sin código, o con el código compuesto distinto (serie que quedó bajo la sección indicada):
            # por nivel y título; si hay varias con el mismo, la que cuelga del mismo superior.
            iguales = [x for x in existentes if x.nivel == n.nivel and cuadro._n(x.titulo) == cuadro._n(n.titulo)]
            r = iguales[0] if len(iguales) == 1 else next(
                (x for x in iguales if padre and x.incluido_en_id == padre[1]), None)
        if r is not None:
            _campos(g, n.uri, r)
            mapa[n.uri] = ("recurso_documental", r.id, "RecordSet")
    hecho = {"entidades": 0, "expedientes": 0, "documentos": 0, "colecciones": 0, "relaciones": 0}
    for uri_e, (clase, subtipo, nombre) in a.entidades.items():
        e, creada = cuadro._de_vocabulario(db, fondo.id, clase, nombre, usuario_id, subtipo)
        hecho["entidades"] += int(creada)
        historia = _texto(g, uri_e, RICO.history, SKOS.scopeNote)
        if historia and not e.historia:
            e.historia = historia
        mapa[uri_e] = ("entidad_vocabulario", e.id, ric_o.clase_de("entidad_vocabulario", clase=e.clase, subtipo=e.subtipo))
    # Expedientes, colecciones y documentos, de arriba abajo, dentro de lo ya creado.
    for n in _orden(a.fondo, a.recursos):
        if n.uri in mapa or n.nivel in descripcion.NIVELES_CUADRO or n.nivel == "fondo":
            continue
        padre = mapa.get(n.padre)
        if padre is None:
            omitidas["descripciones cuyo nivel superior no se importó"] += 1
            continue
        try:
            if n.clase == "RecordSet":
                r = descripcion.crear_agrupacion(db, fondo_id=fondo.id, nivel=n.nivel, titulo=n.titulo or "Sin título",
                                                 incluido_en_id=padre[1], usuario_id=usuario_id,
                                                 codigo_referencia=_texto(g, n.uri, RICO.identifier),
                                                 fechas_extremas=_fechas(g, n.uri)[0])
                hecho["colecciones" if n.nivel == "coleccion" else "expedientes"] += 1
            else:
                r = _documento(db, fondo, n, padre[1], usuario_id, g)
                hecho["documentos"] += 1
        except descripcion.ErrorDescripcion as exc:
            omitidas[f"{n.nivel.replace('_', ' ')} no importado: {exc}"] += 1
            continue
        _campos(g, n.uri, r)
        forma = next(iter(g.objects(n.uri, RICO.hasDocumentaryFormType)), None)
        if forma in mapa and n.clase == "Record":
            r.forma_documental_id = mapa[forma][1]
        mapa[n.uri] = ("recurso_documental", r.id, ric_o.CLASE_NIVEL[n.nivel])
    db.flush()
    # Relaciones del catálogo entre nodos importados.
    por_nombre = {p.rico: (c, False) for c, p in ric_o.PROPIEDADES.items()}
    por_nombre.update({p.inversa: (c, True) for c, p in ric_o.PROPIEDADES.items() if p.inversa and p.inversa not in por_nombre})
    vistas = set()
    for s, p, o in g:
        if not str(p).startswith(str(RICO)) or _local(p) not in por_nombre:
            continue
        codigo, invertida = por_nombre[_local(p)]
        if codigo in ESTRUCTURALES:
            continue
        origen, destino = (o, s) if invertida else (s, o)
        if origen not in mapa or destino not in mapa:
            omitidas[f"rico:{_local(p)} con un extremo no importado"] += 1
            continue
        (t_o, i_o, c_o), (t_d, i_d, c_d) = mapa[origen], mapa[destino]
        if (codigo, i_o, i_d) in vistas or (codigo, i_d, i_o) in vistas and codigo in ("is_agent_associated_with_agent",
                                                                                         "has_family_association_with"):
            continue
        vistas.add((codigo, i_o, i_d))
        if not ric_o.uso_valido(codigo, c_o, c_d):
            omitidas[f"rico:{_local(p)} entre clases que su dominio o rango no admiten"] += 1
            continue
        rol = ROL.get(codigo)
        if codigo == "has_or_had_subject":
            rol = {"Concept": "materia", "Place": "lugar", "Mandate": "mandato"}.get(c_d) or (
                "mencionado" if c_d in ric_o.AGENTES else None)
        db.add(Relacion(origen_tipo=t_o, origen_id=i_o, destino_tipo=t_d, destino_id=i_d,
                        tipo_relacion=CATEGORIA.get(codigo, "asociacion"), codigo_ric=codigo, rol=rol,
                        origen="persona", confirmada_por_id=usuario_id, nota=f"Importada de {archivo}"[:500]))
        hecho["relaciones"] += 1
    nodos_relacion = sum(1 for c in set(g.objects(None, RDF.type)) if _local(c).endswith("Relation")
                         for _ in g.subjects(RDF.type, c))
    if nodos_relacion:
        omitidas["nodos rico:Relation (se toma la tripleta directa; su vigencia no se importa)"] += nodos_relacion
    db.flush()
    hecho["omitidas"] = dict(omitidas)
    return hecho


def _orden(raiz: Nodo, recursos: dict) -> list[Nodo]:
    salida, pendientes = [], list(raiz.hijos)
    while pendientes:
        n = pendientes.pop(0)
        salida.append(n)
        pendientes.extend(n.hijos)
    return salida


def _documento(db: Session, fondo: RecursoDocumental, n: Nodo, padre_id: uuid.UUID, usuario_id: uuid.UUID,
               g: Graph) -> RecursoDocumental:
    """Un rico:Record sin archivo: la descripción publicada, dentro de su serie o expediente."""
    from app.servicios import descripcion

    superior = descripcion._superior(db, fondo.id, "unidad_documental", padre_id)
    r = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo=(n.titulo or "Sin título")[:300],
                          fondo_id=fondo.id, incluido_en_id=superior.id,
                          codigo_referencia=_texto(g, n.uri, RICO.identifier), origen_titulo="persona",
                          creado_por_id=usuario_id, publicado_en=ahora(), publicado_por_id=usuario_id)
    db.add(r)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=superior.id, destino_tipo="recurso_documental",
                    destino_id=r.id, tipo_relacion="inclusion", codigo_ric="includes_or_included", origen="persona",
                    confirmada_por_id=usuario_id))
    return r

