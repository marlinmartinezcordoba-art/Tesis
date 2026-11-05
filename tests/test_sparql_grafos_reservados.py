"""
Regresión de seguridad: el SPARQL público no puede leer los grafos «completo».

Oxigraph deja consultar con GRAPH ?g todos los grafos con nombre del almacén si
no se acotan también los named_graphs; los «completo» llevan lo clasificado o
reservado (Ley 1712 de 2014).
"""

from app.servicios.grafo_rdf import Embebido


def test_graph_no_alcanza_el_grafo_completo():
    a = Embebido(None)
    a.reemplazar_varios({
        "urn:ricora:grafo:00000000-0000-0000-0000-000000000001:publico": b'<urn:a> <urn:p> "publico" .',
        "urn:ricora:grafo:00000000-0000-0000-0000-000000000001:completo": b'<urn:b> <urn:p> "RESERVADO" .',
    })
    publico = "urn:ricora:grafo:00000000-0000-0000-0000-000000000001:publico"
    for consulta in ("SELECT ?o WHERE { GRAPH ?g { ?s ?p ?o } }",
                     "SELECT ?o WHERE { ?s ?p ?o }",
                     "SELECT ?o FROM NAMED <urn:ricora:grafo:00000000-0000-0000-0000-000000000001:completo> "
                     "WHERE { GRAPH ?g { ?s ?p ?o } }"):
        try:
            cuerpo, _ = a.consultar(publico, consulta, 100)
        except Exception:  # noqa: BLE001 — rechazarla también es correcto
            continue
        assert b"RESERVADO" not in cuerpo, consulta
    cuerpo, _ = a.consultar([publico], "SELECT ?o WHERE { GRAPH ?g { ?s ?p ?o } }", 100)
    assert b"publico" in cuerpo
