"""
Enlace asistido con Wikidata (app/servicios/wikidata.py).

RICORA propone candidatos con su descripción y su VIAF; la archivista confirma
con el mismo camino de un identificador escrito a mano, que sale como owl:sameAs.
Wikidata no se consulta de verdad en las pruebas: se simula su respuesta.
"""

import httpx
import pytest

from app.servicios import wikidata
from tests.test_especializacion_ric import agente
from tests.test_preservacion import archivista, fondo  # noqa: F401  (fixtures)


class Respuesta:
    def __init__(self, datos, codigo=200):
        self.datos, self.status_code = datos, codigo

    def json(self):
        return self.datos


@pytest.fixture()
def wikidata_falso(monkeypatch):
    pedidos = []

    def get(url, params=None, headers=None, timeout=None):
        pedidos.append((params, headers))
        if params["action"] == "wbsearchentities":
            return Respuesta({"search": [{"id": "Q1", "label": "Gustavo Rojas Pinilla", "description": "militar"},
                                         {"id": "Q2", "label": "Gustavo Rojas", "description": "futbolista"}]})
        return Respuesta({"entities": {
            "Q1": {"labels": {"es": {"value": "Gustavo Rojas Pinilla"}},
                   "descriptions": {"es": {"value": "militar y político colombiano"}},
                   "claims": {"P214": [{"mainsnak": {"datavalue": {"value": "12345678"}}}]}},
            "Q2": {"labels": {"es": {"value": "Gustavo Rojas"}}, "descriptions": {}, "claims": {}}}})

    monkeypatch.setattr(httpx, "get", get)
    return pedidos


def test_propone_candidatos_con_viaf_y_la_archivista_confirma(cliente, db, fondo, archivista, wikidata_falso):  # noqa: F811
    persona = agente(db, fondo, "Gustavo Rojas Pinilla")
    db.commit()
    r = cliente.get(f"/api/vocabulario/{persona.id}/candidatos-wikidata", headers=archivista)
    assert r.status_code == 200, r.text
    c = r.json()["candidatos"]
    assert [x["qid"] for x in c] == ["Q1", "Q2"]
    assert c[0]["viaf"] == "12345678" and c[0]["descripcion"] == "militar y político colombiano" and not c[0]["ya_enlazado"]
    # Solo el nombre sale hacia Wikidata, con un agente que identifica al sistema.
    params, cabeceras = wikidata_falso[0]
    assert params["search"] == "Gustavo Rojas Pinilla" and "RICORA" in cabeceras["User-Agent"]
    # Nada se enlazó solo: la archivista confirma con el camino de siempre.
    assert cliente.post(f"/api/vocabulario/{persona.id}/identificadores", headers=archivista,
                        json={"esquema": "wikidata", "valor": "Q1"}).status_code == 201
    assert cliente.post(f"/api/vocabulario/{persona.id}/identificadores", headers=archivista,
                        json={"esquema": "viaf", "valor": "12345678"}).status_code == 201
    c = cliente.get(f"/api/vocabulario/{persona.id}/candidatos-wikidata", headers=archivista).json()["candidatos"]
    assert c[0]["ya_enlazado"] is True


def test_si_wikidata_no_responde_lo_dice_sin_romper_la_ficha(cliente, db, fondo, archivista, monkeypatch):  # noqa: F811
    persona = agente(db, fondo, "Alcaldía de Tunja", "entidad_corporativa")
    db.commit()

    def caido(*a, **k):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(httpx, "get", caido)
    r = cliente.get(f"/api/vocabulario/{persona.id}/candidatos-wikidata", headers=archivista)
    assert r.status_code == 502 and "Wikidata" in r.json()["detail"]
    assert cliente.get(f"/api/vocabulario/{persona.id}", headers=archivista).status_code == 200
