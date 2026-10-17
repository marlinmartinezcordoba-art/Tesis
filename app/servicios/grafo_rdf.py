"""
Grafo RiC-O persistente.

La descripción publicada vive como grafo RDF en un almacén de tripletas
(Oxigraph, SPARQL 1.1), un grafo con nombre por fondo y alcance:

- «publico»: sin lo clasificado ni lo reservado (lo que ven el SPARQL, las
  URI /id/ y la descarga sin sesión);
- «completo»: todo (la exportación con permiso).

PostgreSQL sigue siendo donde se trabaja (formularios, bloqueos, versiones,
auditoría). Cada cambio que entra en el grafo de un fondo sube su
`version_datos` en la misma transacción (`marcar_cambios`); el trabajador
reconstruye el grafo, lo valida contra RiC-O 1.1 (OWL y SHACL) y lo
reemplaza en el almacén de una sola vez. Quien lee un grafo que todavía no
está al día lo sincroniza antes de leer: nunca se sirve un grafo viejo.

El almacén se abre en este proceso (pruebas, desarrollo) o se usa por HTTP
en el servicio `grafo` (producción), que es el único que escribe.
"""

import hashlib
import hmac
import json
import logging
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone

from rdflib import Graph
from sqlalchemy import event, select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.grafo_rdf import GrafoRdf
from app.models.recurso_documental import RecursoDocumental

log = logging.getLogger("ricora.grafo")

ALCANCES = ("publico", "completo")
CABECERA = "X-RICORA-Grafo"


class ErrorGrafo(RuntimeError):
    pass


def nombre(fondo_id, alcance: str) -> str:
    return f"urn:ricora:grafo:{fondo_id}:{alcance}"


def validar_nombre(grafo: str) -> str:
    """Solo grafos de RICORA y sin caracteres que rompan la actualización SPARQL."""
    if not grafo.startswith("urn:ricora:grafo:") or any(c in grafo for c in "<> \n{}\"\\"):
        raise ErrorGrafo("Nombre de grafo no válido.")
    return grafo


def ficha_servicio() -> str:
    """Credencial entre la web, el trabajador y el servicio del grafo (derivada de la clave del sistema)."""
    return hmac.new(settings.secret_key.encode(), b"ricora-grafo", hashlib.sha256).hexdigest()


# --- El almacén ----------------------------------------------------------------------------------


class Embebido:
    """Oxigraph abierto en este proceso: en un directorio o en memoria."""

    def __init__(self, directorio: str = ""):
        import pyoxigraph

        self._ox = pyoxigraph
        self.store = pyoxigraph.Store(directorio) if directorio else pyoxigraph.Store()
        self._escritura = threading.Lock()

    def reemplazar(self, grafo: str, ntriples: bytes) -> None:
        # DROP + INSERT DATA en una sola actualización: quien consulta ve el
        # grafo anterior o el nuevo, nunca uno a medias.
        validar_nombre(grafo)
        cuerpo = ntriples.decode("utf-8")
        with self._escritura:
            self.store.update(f"DROP SILENT GRAPH <{grafo}> ; INSERT DATA {{ GRAPH <{grafo}> {{\n{cuerpo}\n}} }}")

    def leer(self, grafo: str) -> bytes:
        g = self._ox.NamedNode(grafo)
        if not self.store.contains_named_graph(g):
            return b""
        return self.store.dump(format=self._ox.RdfFormat.N_TRIPLES, from_graph=g)

    def consultar(self, grafo: str, consulta: str, maximo: int) -> tuple[bytes, str]:
        ox = self._ox
        resultado = self.store.query(consulta, default_graph=[ox.NamedNode(grafo)])
        if isinstance(resultado, ox.QueryBoolean):
            return json.dumps({"head": {}, "boolean": bool(resultado)}).encode(), "application/sparql-results+json"
        if isinstance(resultado, ox.QueryTriples):
            tripletas = list(resultado)
            if len(tripletas) > maximo:
                raise ErrorGrafo(f"El resultado supera {maximo} tripletas: acote la consulta.")
            return ox.serialize(tripletas, format=ox.RdfFormat.TURTLE), "text/turtle; charset=utf-8"
        variables = [v.value for v in resultado.variables]
        filas = []
        for i, fila in enumerate(resultado):
            if i >= maximo:
                raise ErrorGrafo(f"El resultado supera {maximo} filas: use LIMIT.")
            filas.append({v: _termino(fila[v]) for v in variables if fila[v] is not None})
        cuerpo = {"head": {"vars": variables}, "results": {"bindings": filas}}
        return json.dumps(cuerpo, ensure_ascii=False).encode(), "application/sparql-results+json"

    def estado(self) -> dict:
        return {"grafos": len(list(self.store.named_graphs())), "tripletas": len(self.store),
                "motor": "Oxigraph (pyoxigraph)", "persistente": bool(settings.grafo_directorio)}


def _termino(t) -> dict:
    import pyoxigraph as ox

    if isinstance(t, ox.Literal):
        d = {"type": "literal", "value": t.value}
        if t.language:
            d["xml:lang"] = t.language
        elif t.datatype and t.datatype.value != "http://www.w3.org/2001/XMLSchema#string":
            d["datatype"] = t.datatype.value
        return d
    if isinstance(t, ox.BlankNode):
        return {"type": "bnode", "value": t.value}
    return {"type": "uri", "value": t.value}


class Remoto:
    """El servicio `grafo` por HTTP (producción)."""

    def __init__(self, url: str):
        import httpx

        self._http = httpx.Client(base_url=url, timeout=60, headers={CABECERA: ficha_servicio()})

    def _pedir(self, metodo: str, ruta: str, **kw):
        try:
            r = self._http.request(metodo, ruta, **kw)
        except Exception as exc:  # noqa: BLE001
            raise ErrorGrafo(f"El servicio del grafo no responde: {exc}") from exc
        if r.status_code >= 400:
            raise ErrorGrafo(r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith(
                "application/json") else r.text)
        return r

    def reemplazar(self, grafo: str, ntriples: bytes) -> None:
        self._pedir("PUT", "/grafos", params={"grafo": grafo}, content=ntriples,
                    headers={"Content-Type": "application/n-triples"})

    def leer(self, grafo: str) -> bytes:
        return self._pedir("GET", "/grafos", params={"grafo": grafo}).content

    def consultar(self, grafo: str, consulta: str, maximo: int) -> tuple[bytes, str]:
        r = self._pedir("POST", "/consulta", json={"grafo": grafo, "consulta": consulta, "maximo": maximo})
        return r.content, r.headers.get("content-type", "application/octet-stream")

    def estado(self) -> dict:
        return self._pedir("GET", "/estado").json()


_almacen = None
_crear = threading.Lock()


def almacen():
    global _almacen
    with _crear:
        if _almacen is None:
            _almacen = Remoto(settings.grafo_url) if settings.grafo_url else Embebido(settings.grafo_directorio)
        return _almacen


# --- Qué cambió ------------------------------------------------------------------------------------

# Tablas cuyo contenido entra en el grafo RiC-O de un fondo. Las que tienen
# fondo_id marcan solo ese fondo; las demás, todos (son pocas y raras).
_CON_FONDO = {"recursos_documentales", "entidades_vocabulario", "actividades", "hitos", "instanciaciones",
              "declaraciones_derechos"}
_SIN_FONDO = {"fechas", "nombres_entidad", "identificadores_entidad", "verificaciones_integridad", "migraciones",
              "comprobaciones_tecnicas", "conceptos_tesauro", "etiquetas_concepto"}


def _fondos_de(sesion: Session) -> set | None:
    """Los fondos tocados en este flush; None = todos."""
    fondos: set = set()
    relaciones = []
    for obj in list(sesion.new) + list(sesion.dirty) + list(sesion.deleted):
        tabla = getattr(obj, "__tablename__", None)
        if tabla == "recursos_documentales":
            fondos.add(obj.id if obj.nivel == "fondo" else obj.fondo_id)
        elif tabla in _CON_FONDO:
            fondos.add(obj.fondo_id)
        elif tabla == "relaciones":
            relaciones.append(obj)
        elif tabla in _SIN_FONDO:
            return None
    if relaciones:
        conexion = sesion.connection()
        for rel in relaciones:
            for tipo, ident in ((rel.origen_tipo, rel.origen_id), (rel.destino_tipo, rel.destino_id)):
                tabla = {"recurso_documental": "recursos_documentales",
                         "entidad_vocabulario": "entidades_vocabulario",
                         "instanciacion": "instanciaciones"}.get(tipo)
                if tabla is None:
                    continue
                columna = "COALESCE(fondo_id, id)" if tabla == "recursos_documentales" else "fondo_id"
                f = conexion.execute(text(f"SELECT {columna} FROM {tabla} WHERE id = :i"), {"i": ident}).scalar()
                if f is not None:
                    fondos.add(f)
    fondos.discard(None)
    return fondos


def marcar_cambios(sesion: Session, _contexto) -> None:
    fondos = _fondos_de(sesion)
    if fondos is not None and not fondos:
        return
    conexion = sesion.connection()
    origen = ("SELECT id FROM recursos_documentales WHERE nivel = 'fondo'" if fondos is None
              else "SELECT unnest(CAST(:fondos AS uuid[]))")
    conexion.execute(text(f"""
        INSERT INTO grafos_rdf (id, fondo_id, alcance)
        SELECT gen_random_uuid(), f.id, a.alcance
        FROM ({origen}) AS f(id) CROSS JOIN (VALUES ('publico'), ('completo')) AS a(alcance)
        ON CONFLICT (fondo_id, alcance)
        DO UPDATE SET version_datos = grafos_rdf.version_datos + 1, cambiado_en = now()
    """), {"fondos": [str(f) for f in fondos]} if fondos is not None else {})


event.listen(Session, "after_flush", marcar_cambios)


# --- Sincronizar y leer ----------------------------------------------------------------------------


def _fila(db: Session, fondo_id, alcance: str) -> GrafoRdf:
    fila = db.scalar(select(GrafoRdf).where(GrafoRdf.fondo_id == fondo_id, GrafoRdf.alcance == alcance))
    if fila is None:
        fila = GrafoRdf(id=uuid.uuid4(), fondo_id=fondo_id, alcance=alcance, version_datos=1, version_sincronizada=0)
        db.add(fila)
        db.flush()
    return fila


def ntriples(g: Graph) -> bytes:
    """N-Triples ordenadas: el mismo grafo da siempre los mismos bytes (y la misma huella)."""
    lineas = sorted(linea for linea in g.serialize(format="nt").splitlines() if linea.strip())
    return ("\n".join(lineas) + "\n").encode("utf-8") if lineas else b""


def sincronizar(db: Session, fondo: RecursoDocumental, alcance: str) -> GrafoRdf:
    """Arma el grafo RiC-O del fondo, lo valida y lo reemplaza en el almacén."""
    from app.servicios import conformidad_rico, exportacion_rico

    fila = _fila(db, fondo.id, alcance)
    version = fila.version_datos
    try:
        ex = exportacion_rico.exportar(db, fondo, incluir_restringidos=alcance == "completo")
        cuerpo = ntriples(ex.grafo)
        owl = conformidad_rico.verificar_owl(ex.grafo)
        shacl = conformidad_rico.validar_shacl(ex.grafo)
        almacen().reemplazar(nombre(fondo.id, alcance), cuerpo)
    except Exception as exc:  # noqa: BLE001 — se registra y se reintenta con el próximo cambio
        log.exception("No se pudo sincronizar el grafo %s/%s", fondo.id, alcance)
        db.execute(update(GrafoRdf).where(GrafoRdf.id == fila.id).values(error=str(exc)[:1000]))
        db.flush()
        db.refresh(fila)
        raise ErrorGrafo(f"No se pudo actualizar el grafo RiC-O del fondo: {exc}") from exc
    db.execute(update(GrafoRdf).where(GrafoRdf.id == fila.id).values(
        version_sincronizada=version, sincronizado_en=datetime.now(timezone.utc), tripletas=len(ex.grafo),
        huella=hashlib.sha256(cuerpo).hexdigest(), conforme=not owl and shacl["conforme"], problemas_owl=len(owl),
        resultados_shacl=len(shacl["resultados"]), resumen=ex.resumen(), error=None))
    db.flush()
    db.refresh(fila)
    return fila


def al_dia(db: Session, fondo: RecursoDocumental, alcance: str) -> GrafoRdf:
    fila = _fila(db, fondo.id, alcance)
    return fila if fila.al_dia else sincronizar(db, fondo, alcance)


def _decimales_con_punto(g: Graph) -> None:
    """Oxigraph devuelve los xsd:decimal en su forma canónica XSD 1.1 («2»); la
    exportación los escribe «2.0», que Turtle y JSON-LD leen igual. Se vuelve a esa forma."""
    from rdflib import XSD, Literal

    for s, p, o in list(g):
        if isinstance(o, Literal) and o.datatype == XSD.decimal and "." not in str(o):
            g.remove((s, p, o))
            g.add((s, p, Literal(f"{o}.0", datatype=XSD.decimal)))


def leer(db: Session, fondo: RecursoDocumental, incluir_restringidos: bool = False):
    """El grafo guardado del fondo, como una exportación (para serializar, validar o resolver URI)."""
    from app.servicios import exportacion_rico

    alcance = "completo" if incluir_restringidos else "publico"
    fila = al_dia(db, fondo, alcance)
    g = exportacion_rico.grafo_vacio()
    cuerpo = almacen().leer(nombre(fondo.id, alcance))
    if not cuerpo and fila.tripletas:
        # El registro dice que hay grafo y el almacén no lo tiene (p. ej., la base se
        # restauró sin el volumen del grafo): se rearma desde la base.
        fila = sincronizar(db, fondo, alcance)
        cuerpo = almacen().leer(nombre(fondo.id, alcance))
    if cuerpo:
        g.parse(data=cuerpo.decode("utf-8"), format="nt")
        _decimales_con_punto(g)
    ex = exportacion_rico.Exportacion(grafo=g, fondo=fondo, omitidas=Counter((fila.resumen or {}).get("omitidas", {})))
    # Las entidades con URI propia (base + UUID), como las anota la exportación.
    base = exportacion_rico.base()
    for s in set(g.subjects()):
        resto = str(s)[len(base):] if str(s).startswith(base) else ""
        try:
            ex.nodos[uuid.UUID(resto)] = (None, None)
        except ValueError:
            pass
    ex.fila = fila
    return ex


def consultar(db: Session, fondo: RecursoDocumental, consulta: str, maximo: int) -> tuple[bytes, str]:
    """SPARQL de lectura sobre el grafo público guardado del fondo, en el almacén."""
    al_dia(db, fondo, "publico")
    return almacen().consultar(nombre(fondo.id, "publico"), consulta, maximo)


def sincronizar_pendientes(db: Session, limite: int = 4) -> int:
    """Para el trabajador: los grafos con cambios, los más viejos primero."""
    filas = db.scalars(select(GrafoRdf).where(GrafoRdf.version_sincronizada < GrafoRdf.version_datos)
                       .order_by(GrafoRdf.cambiado_en).limit(limite)).all()
    hechos = 0
    for fila in filas:
        fondo = db.get(RecursoDocumental, fila.fondo_id)
        if fondo is None:
            continue
        try:
            sincronizar(db, fondo, fila.alcance)
            hechos += 1
        except ErrorGrafo:
            # Que el trabajador no insista en cada vuelta: espera al próximo cambio.
            db.execute(update(GrafoRdf).where(GrafoRdf.id == fila.id).values(
                version_sincronizada=GrafoRdf.version_datos))
        db.commit()
    return hechos


def estado(db: Session) -> dict:
    """Estado del almacén y de cada grafo, para la pantalla y la salud del servidor."""
    filas = db.execute(select(GrafoRdf, RecursoDocumental.titulo).join(
        RecursoDocumental, RecursoDocumental.id == GrafoRdf.fondo_id).order_by(RecursoDocumental.titulo,
                                                                             GrafoRdf.alcance)).all()
    try:
        motor = almacen().estado() | {"ok": True}
    except Exception as exc:  # noqa: BLE001
        motor = {"ok": False, "motivo": str(exc)[:300]}
    return {"almacen": motor, "grafos": [{
        "fondo_id": str(f.fondo_id), "fondo": titulo, "alcance": f.alcance, "nombre": nombre(f.fondo_id, f.alcance),
        "al_dia": f.al_dia, "version_datos": f.version_datos, "version_sincronizada": f.version_sincronizada,
        "sincronizado_en": f.sincronizado_en.isoformat() if f.sincronizado_en else None, "tripletas": f.tripletas,
        "huella": f.huella, "conforme": f.conforme, "problemas_owl": f.problemas_owl,
        "resultados_shacl": f.resultados_shacl, "error": f.error} for f, titulo in filas]}
