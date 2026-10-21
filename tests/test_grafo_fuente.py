"""
El grafo RiC-O como fuente de verdad de lo publicado.

- Ida y vuelta exacta: las tablas de la descripción de un fondo se vuelven a
  armar desde el almacén (RiC-O + control) columna por columna.
- Lo que RiC-O dice exacto no se repite en el control (título, código,
  alcance, jerarquía, forma documental, nombres, fechas…).
- El grafo gana: si alguien cambia o borra una fila por fuera, la
  comparación lo detecta y la reconstrucción la devuelve a lo que dice el grafo.
- El grafo de control nunca sale: ni en el SPARQL ni en las descargas.
"""

from rdflib import URIRef
from sqlalchemy import delete, select, text

from app.models.descripcion import NombreEntidad
from app.models.grafo_rdf import GrafoRdf
from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, grafo_control, grafo_rdf
from tests.test_descripcion import OFICIO_114, aceptar_todo, documento, fondo, iniciar, motor_prueba  # noqa: F401
from tests.test_exportacion_rico import fondo_rico  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def _guardar(db, fnd):
    for alcance in grafo_rdf.ALCANCES:
        grafo_rdf.sincronizar(db, fnd, alcance)
    db.commit()


def test_ida_y_vuelta_exacta_y_ric_primero(db, fondo_rico):  # noqa: F811
    fnd, o114 = fondo_rico["fondo"], fondo_rico["o114"]
    _guardar(db, fnd)
    antes = grafo_control.foto(db, fnd.id)
    assert sum(len(v) for v in antes.values()) > 20
    assert grafo_rdf.comparar(db, fnd.id) == []
    # RiC-O primero: el título y la jerarquía del oficio no están en el grafo de control.
    control = grafo_rdf.almacen().leer(grafo_rdf.nombre(fnd.id, "control")).decode()
    fila = f"<urn:ricora:fila:{o114.id}>"
    propias = [linea for linea in control.splitlines() if linea.startswith(fila)]
    assert propias and not any("#titulo>" in linea or "#incluido_en_id>" in linea for linea in propias)
    assert any("#origen_titulo>" in linea for linea in propias)  # la procedencia del dato sí (RiC-O no la tiene)
    # Reconstruir sobre las mismas tablas no cambia nada, columna por columna.
    r = grafo_rdf.reconstruir(db, fnd.id)
    assert r["diferencias_despues"] == [] and r["corregidas"] == 0
    assert grafo_control.foto(db, fnd.id) == antes


def test_el_grafo_gana(db, fondo_rico):  # noqa: F811
    fnd, o114 = fondo_rico["fondo"], fondo_rico["o114"]
    _guardar(db, fnd)
    antes = grafo_control.foto(db, fnd.id)
    titulo = o114.titulo
    # Cambios por fuera del sistema (sin pasar por la descripción ni marcar el grafo).
    db.execute(text("UPDATE recursos_documentales SET titulo = 'alterado', folios = 999 WHERE id = :i"), {"i": o114.id})
    nombre = db.scalars(select(NombreEntidad).where(NombreEntidad.entidad_id.in_(
        list(antes["entidades_vocabulario"])))).first()
    assert nombre is not None
    db.execute(delete(NombreEntidad).where(NombreEntidad.id == nombre.id))
    db.flush()
    db.expire_all()
    dif = grafo_rdf.comparar(db, fnd.id)
    assert {(d["tabla"], d["columna"]) for d in dif} >= {("recursos_documentales", "titulo"),
                                                         ("recursos_documentales", "folios"),
                                                         ("nombres_entidad", None)}
    r = grafo_rdf.reconstruir(db, fnd.id)
    assert r["corregidas"] >= 3 and r["diferencias_despues"] == []
    db.expire_all()
    assert db.get(type(o114), o114.id).titulo == titulo
    assert db.get(NombreEntidad, nombre.id) is not None
    assert grafo_control.foto(db, fnd.id) == antes


def test_el_control_no_sale(cliente, db, fondo_rico, cabeceras_admin):  # noqa: F811
    fnd = fondo_rico["fondo"]
    _guardar(db, fnd)
    for alcance in ("publico", "completo"):
        cuerpo = grafo_rdf.almacen().leer(grafo_rdf.nombre(fnd.id, alcance)).decode()
        assert "urn:ricora:control" not in cuerpo
    ex = grafo_rdf.leer(db, fnd, incluir_restringidos=True)
    assert not any(str(p).startswith("urn:ricora:control") for p in ex.grafo.predicates())
    cuerpo, _ = grafo_rdf.consultar(db, fnd, "SELECT ?p WHERE { ?s ?p ?o FILTER(STRSTARTS(STR(?p), 'urn:ricora')) }", 10)
    assert b"urn:ricora" not in cuerpo
    assert isinstance(exportacion_rico.uri(fnd.id), URIRef)


def test_publicar_escribe_en_el_grafo_validado(cliente, db, fondo, archivista, motor_prueba, monkeypatch):  # noqa: F811
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    datos = aceptar_todo(iniciar(cliente, archivista, [d.id]))
    # Si el fondo no quedaría conforme con RiC-O, no se publica nada.
    real = grafo_rdf.sincronizar

    def no_conforme(db_, fondo_, alcance, exigir_conforme=False):
        if exigir_conforme:
            raise grafo_rdf.NoConforme("La descripción no cumple RiC-O 1.1 y no se publicó: prueba", ["prueba"])
        return real(db_, fondo_, alcance)

    monkeypatch.setattr(grafo_rdf, "sincronizar", no_conforme)
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 422 and "RiC-O" in r.json()["detail"]
    assert db.scalar(select(RecursoDocumental).where(RecursoDocumental.titulo == datos["titulo"])) is None
    # Conforme: publicar deja el grafo escrito y al día en el mismo momento (sin esperar al trabajador).
    monkeypatch.setattr(grafo_rdf, "sincronizar", real)
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 201, r.text
    db.expire_all()
    fila = db.scalar(select(GrafoRdf).where(GrafoRdf.fondo_id == fondo.id, GrafoRdf.alcance == "completo"))
    assert fila.al_dia and fila.conforme
    assert grafo_rdf.comparar(db, fondo.id) == []


def test_comparar_y_reconstruir_por_la_api(cliente, db, fondo_rico, cabeceras_admin, archivista):  # noqa: F811
    fnd, o114 = fondo_rico["fondo"], fondo_rico["o114"]
    _guardar(db, fnd)
    p = {"fondo_id": str(fnd.id)}
    assert cliente.get("/api/exportacion/grafo/coherencia", headers=archivista, params=p).json()["coinciden"] is True
    db.execute(text("UPDATE recursos_documentales SET titulo = 'alterado' WHERE id = :i"), {"i": o114.id})
    db.commit()
    c = cliente.get("/api/exportacion/grafo/coherencia", headers=archivista, params=p).json()
    assert c["coinciden"] is False and c["diferencias"][0]["columna"] == "titulo"
    assert cliente.post("/api/exportacion/grafo/reconstruir", headers=archivista, params=p).status_code == 403
    r = cliente.post("/api/exportacion/grafo/reconstruir", headers=cabeceras_admin, params=p)
    assert r.status_code == 200 and r.json()["corregidas"] == 1 and r.json()["diferencias_despues"] == []
    assert cliente.get("/api/exportacion/grafo/coherencia", headers=archivista, params=p).json()["coinciden"] is True
    # La alerta del trabajador: tablas distintas del grafo.
    db.execute(text("UPDATE recursos_documentales SET titulo = 'otra vez' WHERE id = :i"), {"i": o114.id})
    db.commit()
    assert grafo_rdf.verificar_coherencia(db) >= 1
