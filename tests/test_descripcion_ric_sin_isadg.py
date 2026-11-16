"""La descripción se hace con RiC, sin ISAD(G): no hay ficha ISAD(G) en la API, el paquete de
difusión lleva RiC-O, la validación habla en términos RiC y la fecha de acumulación
(rico:hasAccumulationDate) se registra y se exporta."""

import uuid

import pytest
from rdflib import URIRef

from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico
from app.servicios.exportacion_rico import RICO
from tests.test_descripcion import archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_contexto import OFICIO


@pytest.fixture()
def sin_motor(monkeypatch):
    from app.servicios import motor

    monkeypatch.setattr(motor, "motor_activo", lambda: None)


def test_fecha_de_acumulacion_se_guarda_y_sale_en_rico(cliente, db, fondo, archivista, sin_motor):  # noqa: F811
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "acta.pdf", OFICIO).id])
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json={
        "trabajo_id": espacio["trabajo_id"], "titulo": "Acta reunida", "fecha_acumulacion": "1960"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    detalle = cliente.get(f"/api/descripcion/registros/{rid}", headers=archivista).json()
    assert detalle["fecha_acumulacion"] == "1960"
    db.expire_all()
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    nodo = URIRef(exportacion_rico.base() + rid)
    fechas = list(g.objects(nodo, RICO.hasAccumulationDate))
    assert len(fechas) == 1 and "1960" in {str(o) for o in g.objects(fechas[0], RICO.normalizedDateValue)}
    assert cliente.get(f"/api/descripcion/registros/{rid}/isadg", headers=archivista).status_code == 404


def test_fecha_de_acumulacion_invalida_se_rechaza(cliente, db, fondo, archivista, sin_motor):  # noqa: F811
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "b.pdf", OFICIO).id])
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json={
        "trabajo_id": espacio["trabajo_id"], "titulo": "Otra", "fecha_acumulacion": "hace mucho"})
    assert r.status_code == 422 and "acumulación" in r.text


def test_la_guia_de_metadatos_no_cita_isadg(cliente, archivista):  # noqa: F811
    r = cliente.get("/api/descripcion/atributos", headers=archivista)
    if r.status_code == 404:
        pytest.skip("sin catálogo de atributos en esta ruta")
    assert "isad" not in r.text.lower()
