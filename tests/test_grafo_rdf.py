"""
Grafo RiC-O persistente (almacén de tripletas Oxigraph).

- Cada cambio que entra en el grafo de un fondo lo marca, en la misma
  transacción; el grafo guardado se rearma, se valida (OWL y SHACL) y se
  reemplaza de una vez. Nunca se sirve uno viejo.
- SPARQL, URI /id/ y descargas leen del almacén, no de las tablas.
- El trabajador sincroniza lo pendiente sin que nadie lo pida.
- El servicio HTTP del grafo (producción) exige su ficha y solo acepta
  nombres de grafo de RICORA; el cliente remoto da lo mismo que el embebido.
"""

from fastapi.testclient import TestClient
from rdflib import Literal, Namespace, URIRef
from sqlalchemy import select

from app.models.grafo_rdf import GrafoRdf
from app.servicios import exportacion_rico, grafo_rdf
from tests.conftest import crear_usuario, ingresar
from tests.test_exportacion_rico import fondo_rico  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401

RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")


def _fila(db, fondo, alcance="publico"):
    return db.scalar(select(GrafoRdf).where(GrafoRdf.fondo_id == fondo.id, GrafoRdf.alcance == alcance))


def _titulos(g, nodo):
    return {str(o) for o in g.objects(nodo, RICO.title)}


def test_el_grafo_guardado_sigue_cada_cambio_y_es_conforme(db, fondo_rico):  # noqa: F811
    fondo, o114 = fondo_rico["fondo"], fondo_rico["o114"]
    nodo = exportacion_rico.uri(o114.id)
    ex = grafo_rdf.leer(db, fondo)
    fila = _fila(db, fondo)
    assert fila.al_dia and fila.conforme and fila.tripletas == len(ex.grafo) and len(fila.huella) == 64
    assert o114.titulo in _titulos(ex.grafo, nodo)
    # El grafo vive en el almacén, con nombre propio.
    assert grafo_rdf.almacen().leer(grafo_rdf.nombre(fondo.id, "publico"))
    # Un cambio en la descripción marca el fondo en la misma transacción…
    antes = fila.version_datos
    o114.titulo = "Oficio N.º 114 (corregido)"
    db.flush()
    db.refresh(fila)
    assert fila.version_datos > antes and not fila.al_dia
    # …y al leer se rearma: el título viejo ya no está en el almacén.
    g = grafo_rdf.leer(db, fondo).grafo
    assert _titulos(g, nodo) == {"Oficio N.º 114 (corregido)"}
    assert _fila(db, fondo).al_dia
    # Lo mismo responde el SPARQL, que corre en el almacén.
    cuerpo, _ = grafo_rdf.consultar(db, fondo, f"SELECT ?t WHERE {{ <{nodo}> <{RICO.title}> ?t }}", 100)
    assert "corregido" in cuerpo.decode()


def test_si_el_almacen_perdio_el_grafo_se_rearma(db, fondo_rico):  # noqa: F811
    fondo = fondo_rico["fondo"]
    tripletas = len(grafo_rdf.leer(db, fondo).grafo)
    grafo_rdf.almacen().reemplazar(grafo_rdf.nombre(fondo.id, "publico"), b"")  # volumen perdido
    assert len(grafo_rdf.leer(db, fondo).grafo) == tripletas


def test_un_cambio_en_una_relacion_marca_su_fondo(db, fondo_rico):  # noqa: F811
    fondo = fondo_rico["fondo"]
    grafo_rdf.leer(db, fondo)
    fila = _fila(db, fondo)
    antes = fila.version_datos
    from app.models.descripcion import Relacion

    rel = db.scalars(select(Relacion).where(Relacion.origen_id == fondo_rico["o114"].id)).first()
    rel.estado = "anulada"
    db.flush()
    db.refresh(fila)
    assert fila.version_datos > antes


def test_el_trabajador_sincroniza_lo_pendiente(db, fondo_rico):  # noqa: F811
    fondo = fondo_rico["fondo"]
    fondo_rico["o114"].titulo = "Oficio para el trabajador"
    db.flush()
    while grafo_rdf.sincronizar_pendientes(db, limite=10):
        pass
    for alcance in grafo_rdf.ALCANCES:
        assert _fila(db, fondo, alcance).al_dia
    g = exportacion_rico.grafo_vacio()
    g.parse(data=grafo_rdf.almacen().leer(grafo_rdf.nombre(fondo.id, "completo")).decode(), format="nt")
    assert (exportacion_rico.uri(fondo_rico["o114"].id), RICO.title, Literal("Oficio para el trabajador")) in g


def test_estado_y_rearmar_solo_la_administracion(cliente, db, fondo_rico, cabeceras_admin):  # noqa: F811
    fondo = fondo_rico["fondo"]
    db.commit()
    r = cliente.post("/api/exportacion/grafo/sincronizar", headers=cabeceras_admin, params={"fondo_id": str(fondo.id)})
    assert r.status_code == 200, r.text
    estado = r.json()
    assert estado["almacen"]["ok"] and estado["almacen"]["motor"].startswith("Oxigraph")
    propios = [g for g in estado["grafos"] if g["fondo_id"] == str(fondo.id)]
    assert {g["alcance"] for g in propios} == {"publico", "completo"} and all(g["al_dia"] and g["conforme"] for g in propios)
    crear_usuario(db, "lector@correo.com", "archivista")
    lector = ingresar(cliente, "lector@correo.com")
    assert cliente.get("/api/exportacion/grafo", headers=lector).status_code == 200
    assert cliente.post("/api/exportacion/grafo/sincronizar", headers=lector,
                        params={"fondo_id": str(fondo.id)}).status_code == 403
    assert cliente.get("/api/salud").json()["grafo_rdf"]["ok"] is True


def test_servicio_http_del_grafo_y_cliente_remoto():
    from app import grafo_servidor

    http = TestClient(grafo_servidor.app)
    nombre = "urn:ricora:grafo:prueba:publico"
    nt = b'<http://ricora.prueba/id/a> <https://www.ica.org/standards/RiC/ontology#title> "Acta" .\n'
    assert http.put("/grafos", params={"grafo": nombre}, content=nt).status_code == 401
    remoto = grafo_rdf.Remoto("http://grafo")
    remoto._http = TestClient(grafo_servidor.app, headers={grafo_rdf.CABECERA: grafo_rdf.ficha_servicio()})
    remoto.reemplazar(nombre, nt)
    assert remoto.leer(nombre) == nt
    cuerpo, tipo = remoto.consultar(nombre, "SELECT ?t WHERE { ?s ?p ?t }", 10)
    assert tipo.startswith("application/sparql-results+json") and b'"Acta"' in cuerpo
    assert remoto.estado()["tripletas"] >= 1
    # Reemplazar es de una vez: el grafo anterior no queda mezclado.
    remoto.reemplazar(nombre, nt.replace(b"Acta", b"Oficio"))
    assert b"Acta" not in remoto.leer(nombre)
    # Solo grafos de RICORA, sin inyección en el nombre.
    try:
        remoto.reemplazar("urn:otro> } ; DROP ALL ; INSERT DATA { GRAPH <urn:x", nt)
        raise AssertionError("aceptó un nombre de grafo ajeno")
    except grafo_rdf.ErrorGrafo:
        pass
    assert isinstance(URIRef(nombre), URIRef)
