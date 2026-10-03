"""
Hallazgo O-32: el perfil SHACL cubre todas las clases que la exportación
emite (Event, Identifier, AgentName, PlaceName, el título de Instantiation y
el Mechanism, que ahora sí tiene focos) y la validación corre en cada
descarga completa, con el resultado en la auditoría.
"""

import pytest
from rdflib import RDF, Literal
from sqlalchemy import select

from app.models.auditoria import RegistroAuditoria
from app.servicios import conformidad_rico
from tests.test_cierre_o31 import fondo_completo  # noqa: F401
from tests.test_exportacion_rico import RICO, exportar, fondo_rico, u  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def _uno(g, clase):
    return next(g.subjects(RDF.type, RICO[clase]))


@pytest.mark.parametrize("clase,ruta,forma", [
    ("Event", RICO.name, "Event"),
    ("Event", RICO.affectsOrAffected, "Event"),
    ("Identifier", RICO.textualValue, "Identifier"),
    ("Identifier", RICO.hasIdentifierType, "Identifier"),
    ("AgentName", RICO.textualValue, "AgentName"),
    ("Instantiation", RICO.title, "Instantiation"),
    ("Mechanism", RICO.technicalCharacteristics, "Mechanism"),
])
def test_cada_clase_emitida_tiene_su_forma(db, fondo_completo, clase, ruta, forma):
    g = exportar(db, fondo_completo).grafo
    foco = _uno(g, clase)
    assert conformidad_rico.validar_shacl(g)["conforme"]
    g.remove((foco, ruta, None))
    r = conformidad_rico.validar_shacl(g)
    assert not r["conforme"]
    assert any(x["foco"] == str(foco) and x["forma"] == f"perfil:{forma}" for x in r["resultados"]), r["resultados"]


def test_nombre_de_lugar_sin_valor_no_es_conforme(db, fondo_completo):
    g = exportar(db, fondo_completo).grafo
    tunja = u(fondo_completo["tunja"].id)
    nodo = u(fondo_completo["tunja"].id) + "/nombre/prueba"
    from rdflib import URIRef

    nodo = URIRef(nodo)
    g.add((nodo, RDF.type, RICO.PlaceName))
    g.add((tunja, RICO.hasOrHadPlaceName, nodo))
    r = conformidad_rico.validar_shacl(g)
    assert any(x["foco"] == str(nodo) and x["forma"] == "perfil:PlaceName" for x in r["resultados"]), r["resultados"]
    g.add((nodo, RICO.textualValue, Literal("Hunza", lang="es")))
    assert conformidad_rico.validar_shacl(g)["conforme"]


def test_el_mecanismo_tiene_focos_en_la_exportacion(db, fondo_completo):
    """La forma pr:Mechanism ya no es letra muerta (O-19 cerró la exportación del mecanismo)."""
    g = exportar(db, fondo_completo).grafo
    assert list(g.subjects(RDF.type, RICO.Mechanism))


def test_cada_descarga_completa_valida_y_lo_deja_en_la_auditoria(cliente, db, fondo_rico, archivista):
    f = fondo_rico
    r = cliente.get("/api/exportacion/rdf", headers=archivista, params={"fondo_id": str(f["fondo"].id)})
    assert r.status_code == 200
    assert r.headers["x-ricora-conformidad"] == "conforme"
    evento = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "rdf_exportado"))
    assert evento.valor_nuevo["conforme"] is True
    assert evento.valor_nuevo["resultados_shacl"] == 0 and evento.valor_nuevo["problemas_owl"] == 0


def test_una_descarga_no_conforme_se_sirve_marcada_y_con_alerta(cliente, db, fondo_rico, archivista, monkeypatch):
    """No se niega la descarga (los datos son de la entidad), pero queda
    marcada, en la auditoría y con una alerta para la administración."""
    from app.models.alerta import Alerta

    monkeypatch.setattr(conformidad_rico, "validar_shacl",
                        lambda g: {"conforme": False, "resultados": [{"foco": "x", "ruta": None, "mensaje": "m",
                                                                      "severidad": "sh:Violation", "forma": "pr:X",
                                                                      "valor": None}]})
    f = fondo_rico
    r = cliente.get("/api/exportacion/rdf", headers=archivista, params={"fondo_id": str(f["fondo"].id)})
    assert r.status_code == 200 and r.headers["x-ricora-conformidad"] == "no-conforme"
    evento = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "rdf_exportado"))
    assert evento.valor_nuevo["conforme"] is False and evento.valor_nuevo["resultados_shacl"] == 1
    assert db.scalar(select(Alerta).where(Alerta.tipo == "exportacion_no_conforme"))
