"""
Contrato de la API (brecha RF-INT-003).

- Toda ruta de /api declara su respuesta en OpenAPI: un esquema JSON o el
  tipo de archivo que entrega (Excel, PDF, RDF…).
- Cada respuesta real que reciben las pruebas se valida contra ese esquema
  (tests/contrato.py, en el cliente de pruebas): esta prueba comprueba que
  el validador está activo y detecta una diferencia.
- /api/v1/… es la dirección estable de la API y cada respuesta dice su versión.
"""

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.main import app
from tests import contrato

# Rutas sin cuerpo JSON propio: la documentación interactiva y la descripción
# OpenAPI misma (FastAPI las genera).
EXCLUIDAS = {"/api/docs", "/api/openapi.json"}


def _documentada(op: dict) -> bool:
    for codigo, respuesta in op.get("responses", {}).items():
        if not codigo.startswith("2") and not codigo.startswith("3"):
            continue
        contenido = respuesta.get("content")
        if not contenido:  # 204, redirecciones
            return True
        for tipo, valor in contenido.items():
            if not tipo.startswith("application/json") or valor.get("schema") not in ({}, None):
                return True
    return False


def test_toda_ruta_de_la_api_declara_su_respuesta():
    esquema = app.openapi()
    sin = []
    for ruta, operaciones in esquema["paths"].items():
        if ruta in EXCLUIDAS:
            continue
        for metodo, op in operaciones.items():
            if not _documentada(op):
                sin.append(f"{metodo.upper()} {ruta}")
    assert sin == [], f"{len(sin)} ruta(s) sin esquema de respuesta: {sin}"


def test_cada_ruta_tiene_resumen_y_etiqueta():
    sin = [f"{m} {r.path}" for r in app.routes if isinstance(r, APIRoute) and r.include_in_schema
           for m in r.methods if not (r.summary and (r.tags or []))]
    assert sin == [], sin


def test_el_validador_de_contrato_detecta_una_respuesta_distinta_de_la_declarada(monkeypatch):
    monkeypatch.delenv("RICORA_CONTRATO_INFORME", raising=False)
    class Declarado(BaseModel):
        estado: str
        base_de_datos: dict

    class RespuestaFalsa:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __init__(self, datos):
            self.datos = datos
            self.content = b"{}"

        def json(self):
            return self.datos

    ruta = contrato.ruta_de(app, "GET", "/api/salud")
    respaldo = ruta.responses
    ruta.responses = {200: {"model": Declarado}}
    try:
        contrato.validar(app, "GET", "http://testserver/api/salud", RespuestaFalsa({"estado": "ok", "base_de_datos": {}}))
        with pytest.raises(AssertionError, match="Contrato de la API: GET /api/salud"):
            contrato.validar(app, "GET", "http://testserver/api/v1/salud", RespuestaFalsa({"estado": 3}))
    finally:
        ruta.responses = respaldo


def test_la_version_1_es_alias_estable_y_cada_respuesta_dice_su_version(cliente):
    a = cliente.get("/api/salud")
    b = cliente.get("/api/v1/salud")
    assert b.status_code == a.status_code and b.json()["estado"] == a.json()["estado"]
    assert a.headers["x-api-version"] == "1" and b.headers["x-api-version"] == "1"
    # Con sesión, permisos y todo: el alias es la misma ruta.
    assert cliente.get("/api/v1/fondos").status_code == 401
    assert "x-api-version" not in cliente.get("/").headers  # la interfaz no es la API
    assert "/api/v1/" in app.openapi()["info"]["description"]
