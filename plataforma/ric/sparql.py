"""Endpoint SPARQL controlado sobre la proyección RDF (T051): un Store en
memoria de pyoxigraph, cargado en cada petición desde el mismo grafo
validado que sirve `ric.rdf.grafo_completo()` — nunca un Store aparte que
se pueda desincronizar de PostgreSQL, que sigue siendo la única fuente de
verdad real.

"Controlado": `Store.query()` solo acepta la gramática de consulta SPARQL
(SELECT/ASK/CONSTRUCT/DESCRIBE). INSERT/DELETE/UPDATE es una gramática
aparte de SPARQL que pyoxigraph expone en un método distinto (`Store.
update()`) que este módulo nunca llama, así que no hay manera de que una
consulta entrante modifique nada.
"""

import pyoxigraph as ox

from . import rdf

LIMITE_FILAS = 1000


class ErrorSparql(Exception):
    """Error de sintaxis o de ejecución, en lenguaje claro para la persona archivista."""


def _store(base):
    g = rdf.grafo_completo(base)
    store = ox.Store()
    if len(g):
        store.bulk_load(g.serialize(format="nt").encode("utf-8"), ox.RdfFormat.N_TRIPLES)
    return store


def _termino_a_json(termino):
    if termino is None:
        return None
    if isinstance(termino, ox.NamedNode):
        return {"type": "uri", "value": termino.value}
    if isinstance(termino, ox.BlankNode):
        return {"type": "bnode", "value": termino.value}
    if isinstance(termino, ox.Literal):
        dato = {"type": "literal", "value": termino.value}
        if termino.language:
            dato["xml:lang"] = termino.language
        elif termino.datatype and termino.datatype.value != "http://www.w3.org/2001/XMLSchema#string":
            dato["datatype"] = termino.datatype.value
        return dato
    return {"type": "literal", "value": str(termino)}


def ejecutar(query, base):
    """Ejecuta `query` contra el grafo validado actual. Devuelve un dict en
    el formato estándar de resultados SPARQL 1.1 (JSON): "results" con
    filas para SELECT/CONSTRUCT/DESCRIBE, o "boolean" para ASK. Lanza
    ErrorSparql si la consulta no es válida SPARQL de solo lectura."""
    store = _store(base)
    try:
        resultado = store.query(query)
    except Exception as e:
        raise ErrorSparql(str(e)) from e

    if isinstance(resultado, ox.QueryBoolean):
        return {"head": {}, "boolean": bool(resultado)}

    if isinstance(resultado, ox.QuerySolutions):
        variables = [v.value for v in resultado.variables]
        filas = [
            {var: _termino_a_json(solucion[var]) for var in variables if solucion[var] is not None}
            for solucion in list(resultado)[:LIMITE_FILAS]
        ]
        return {"head": {"vars": variables}, "results": {"bindings": filas}}

    # CONSTRUCT/DESCRIBE: un QueryTriples, iterable de triples.
    filas = [
        {
            "subject": _termino_a_json(t.subject),
            "predicate": _termino_a_json(t.predicate),
            "object": _termino_a_json(t.object),
        }
        for t in list(resultado)[:LIMITE_FILAS]
    ]
    return {"head": {}, "results": {"bindings": filas}}
