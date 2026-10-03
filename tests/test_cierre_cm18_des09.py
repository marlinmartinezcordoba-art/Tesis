"""
CM-18 y DES-09: la regla de retención de la TRD es un rico:Rule del
vocabulario, regula la serie y la heredan sus expedientes y documentos.
"""

import uuid

from rdflib import RDF, Literal, Namespace

from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, ric_o
from tests.test_autoridad import archivista, fondo, vincular  # noqa: F401
from tests.test_descripcion_v3 import publicada

RICO = Namespace(ric_o.RICO)


def test_regla_de_retencion_regula_la_serie_y_se_hereda(cliente, db, fondo, archivista):
    serie = publicada(db, fondo, "Actas", fondo, nivel="serie")
    exp = publicada(db, fondo, "Actas 1948", serie, nivel="expediente")
    acta = publicada(db, fondo, "Acta 12", exp)
    r = cliente.post("/api/vocabulario/reglas", headers=archivista, json={
        "fondo_id": str(fondo.id), "nombre": "TRD Actas (110.2)", "retencion_gestion_anios": 2,
        "retencion_central_anios": 18, "disposicion_final": "conservacion_total",
        "procedimiento": "Se transfiere al archivo histórico por su valor permanente."})
    assert r.status_code == 201, r.text
    regla_id = r.json()["entidad"]["id"] if "entidad" in r.json() else r.json()["id"]
    regla = db.get(__import__("app.models.descripcion", fromlist=["EntidadVocabulario"]).EntidadVocabulario,
                   uuid.UUID(regla_id))
    assert vincular(cliente, archivista, regla, "regla_serie", serie, con_tipo="recurso_documental").status_code == 201
    # Una serie tiene una sola regla de retención vigente.
    otra = cliente.post("/api/vocabulario/reglas", headers=archivista, json={
        "fondo_id": str(fondo.id), "nombre": "Otra", "disposicion_final": "eliminacion"}).json()
    otra_e = db.get(type(regla), uuid.UUID(otra["entidad"]["id"] if "entidad" in otra else otra["id"]))
    assert vincular(cliente, archivista, otra_e, "regla_serie", serie, con_tipo="recurso_documental").status_code == 422
    ficha = cliente.get(f"/api/instrumentos/catalogo/{acta.id}", headers=archivista).json()
    ret = ficha["retencion"]
    assert ret["gestion_anios"] == 2 and ret["central_anios"] == 18 and ret["disposicion_final"] == "conservacion_total"
    assert ret["heredada_de"]["titulo"] == "Actas"
    # Valores fuera de rango se rechazan.
    assert cliente.post("/api/vocabulario/reglas", headers=archivista, json={
        "fondo_id": str(fondo.id), "nombre": "Mala", "retencion_gestion_anios": -1}).status_code == 422
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    u = exportacion_rico.uri
    assert (u(regla.id), RDF.type, RICO.Rule) in g
    assert (u(regla.id), RICO.regulatesOrRegulated, u(serie.id)) in g
    assert (u(regla.id), RICO.generalDescription, None) in g


def test_la_ficha_de_la_regla_se_edita_y_valida(cliente, db, fondo, archivista):
    r = cliente.post("/api/vocabulario/reglas", headers=archivista, json={"fondo_id": str(fondo.id), "nombre": "TRD"})
    ident = r.json()["entidad"]["id"]
    assert cliente.patch(f"/api/vocabulario/{ident}", headers=archivista,
                         json={"retencion_gestion_anios": "3", "disposicion_final": "seleccion"}).status_code == 200
    campos = cliente.get(f"/api/vocabulario/{ident}", headers=archivista).json()["ficha"]["campos"]
    assert campos["retencion_gestion_anios"] == 3 and campos["disposicion_final"] == "seleccion"
    assert cliente.patch(f"/api/vocabulario/{ident}", headers=archivista,
                         json={"retencion_central_anios": "muchos"}).status_code == 422
    assert cliente.patch(f"/api/vocabulario/{ident}", headers=archivista,
                         json={"disposicion_final": "quemar"}).status_code == 422
