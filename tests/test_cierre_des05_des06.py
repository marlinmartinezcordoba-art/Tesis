"""
DES-05: la custodia es una cadena con fechas y nota, también sobre un archivo.
DES-06: la historia archivística (ISAD-G 3.2.3) tiene su propio campo.
"""

from rdflib import Literal, Namespace

from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, ric_o, vocabulario
from tests.test_descripcion import archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_v3 import TEXTO, publicar, sin_motor  # noqa: F401

RICO = Namespace(ric_o.RICO)
HISTORIA = "Llegó al Archivo Histórico en 1970 por transferencia de la Alcaldía; antes estuvo en la Notaría Primera."


def test_cadena_de_custodia_con_fechas_e_historia_archivistica(cliente, db, fondo, archivista, sin_motor):
    d = documento(db, fondo, "a.pdf", TEXTO)
    espacio = iniciar(cliente, archivista, [d.id])
    r = publicar(cliente, archivista, espacio, historia_archivistica=HISTORIA, entidades=[
        {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "productor", "valor": "Alcaldía", "crear_nueva": True},
        {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "custodio", "valor": "Notaría Primera",
         "crear_nueva": True, "edtf": "1950/1969", "nota": "Depósito provisional."},
        {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "custodio", "valor": "Archivo Histórico",
         "crear_nueva": True, "edtf": "1970/"}])
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["historia_archivistica"] == HISTORIA and doc["origen_historia_archivistica"] == "persona"
    tramos = {e["valor"]: e for e in doc["entidades"] if e.get("rol") == "custodio"}
    assert tramos["Notaría Primera"]["periodo"] == "1950/1969" and tramos["Notaría Primera"]["nota"] == "Depósito provisional."
    assert tramos["Archivo Histórico"]["periodo"] == "1970/"
    publica = cliente.get(f"/api/catalogo/registros/{doc['id']}", headers=archivista).json()
    assert publica["historia_archivistica"] == HISTORIA
    # Custodia sobre el archivo mismo (el dominio de hasOrHadHolder admite Instantiation).
    archivo_hist = next(e for e in doc["entidades"] if e["valor"] == "Archivo Histórico")
    c = cliente.post(f"/api/descripcion/instanciaciones/{d.id}/custodios", headers=archivista,
                     json={"agente_id": archivo_hist["entidad_id"], "fecha_edtf": "2020/", "nota": "Digitalización"})
    assert c.status_code == 201, c.text
    assert c.json()["custodios"][0]["periodo"] == "2020/"
    assert cliente.post(f"/api/descripcion/instanciaciones/{d.id}/custodios", headers=archivista,
                        json={"agente_id": archivo_hist["entidad_id"], "fecha_edtf": "hace mucho"}).status_code == 422
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    u = exportacion_rico.uri
    assert (u(doc["id"]), RICO.history, Literal(HISTORIA)) in g
    assert (u(d.id), RICO.hasOrHadHolder, u(archivo_hist["entidad_id"])) in g
