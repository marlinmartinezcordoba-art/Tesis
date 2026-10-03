"""
Punto SPARQL de solo lectura (hallazgo INS-04).

La fuente es siempre el grafo público de un fondo, el mismo de /id/ y de la
descarga sin sesión (exportacion_rico.exportar con incluir_restringidos=
False): nunca la base de datos ni el grafo completo. Solo consultas de
lectura (SELECT, ASK, CONSTRUCT, DESCRIBE), sin SERVICE (que haría al
servidor consultar otros sitios), con límite de tiempo y de resultados.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as Agotado

from rdflib import Graph
from rdflib.plugins.sparql import prepareQuery

SEGUNDOS = 10
MAXIMO_FILAS = 10_000
_PROHIBIDO = re.compile(r"\b(SERVICE|LOAD|INSERT|DELETE|CLEAR|DROP|CREATE|COPY|MOVE|ADD)\b", re.I)
_LECTURA = {"SelectQuery", "AskQuery", "ConstructQuery", "DescribeQuery"}
_HILOS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sparql")


class ErrorSparql(ValueError):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo


def _sin_literales(consulta: str) -> str:
    """La consulta sin cadenas ni IRI, para buscar palabras clave sin confundirlas con datos."""
    return re.sub(r'"[^"]*"|\'[^\']*\'|<[^>\s]*>', " ", consulta)


def consultar(grafo: Graph, consulta: str) -> tuple[bytes, str]:
    if not consulta or not consulta.strip():
        raise ErrorSparql("Falta la consulta.")
    if len(consulta) > 20_000:
        raise ErrorSparql("La consulta es demasiado larga.")
    if _PROHIBIDO.search(_sin_literales(consulta)):
        raise ErrorSparql("Solo se admiten consultas de lectura sobre este fondo (sin SERVICE, LOAD ni actualizaciones).",
                          403)
    try:
        preparada = prepareQuery(consulta)
    except Exception as exc:  # noqa: BLE001 — el analizador da muchos tipos de error
        raise ErrorSparql(f"La consulta no es SPARQL válido: {exc}") from exc
    if preparada.algebra.name not in _LECTURA:
        raise ErrorSparql("Solo se admiten SELECT, ASK, CONSTRUCT y DESCRIBE.", 403)
    futuro = _HILOS.submit(lambda: grafo.query(preparada))
    try:
        resultado = futuro.result(timeout=SEGUNDOS)
    except Agotado as exc:
        raise ErrorSparql(f"La consulta tardó más de {SEGUNDOS} segundos.", 503) from exc
    if resultado.type in ("CONSTRUCT", "DESCRIBE"):
        if len(resultado.graph) > MAXIMO_FILAS:
            raise ErrorSparql(f"El resultado supera {MAXIMO_FILAS} tripletas: acote la consulta.", 413)
        return resultado.graph.serialize(format="turtle").encode(), "text/turtle; charset=utf-8"
    if resultado.type == "ASK":
        return json.dumps({"head": {}, "boolean": bool(resultado.askAnswer)}).encode(), "application/sparql-results+json"
    filas = list(resultado)
    if len(filas) > MAXIMO_FILAS:
        raise ErrorSparql(f"El resultado supera {MAXIMO_FILAS} filas: use LIMIT.", 413)
    variables = [str(v) for v in resultado.vars]

    def termino(t):
        if t is None:
            return None
        if hasattr(t, "datatype") or hasattr(t, "language"):
            from rdflib import Literal

            if isinstance(t, Literal):
                d = {"type": "literal", "value": str(t)}
                if t.language:
                    d["xml:lang"] = t.language
                elif t.datatype:
                    d["datatype"] = str(t.datatype)
                return d
        from rdflib import BNode

        return {"type": "bnode" if isinstance(t, BNode) else "uri", "value": str(t)}

    cuerpo = {"head": {"vars": variables},
              "results": {"bindings": [{v: termino(f[i]) for i, v in enumerate(variables) if f[i] is not None}
                                       for f in filas]}}
    return json.dumps(cuerpo, ensure_ascii=False).encode(), "application/sparql-results+json"
