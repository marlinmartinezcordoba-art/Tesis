"""
Prueba de contrato de la API (brecha RF-INT-003).

Cada respuesta 2xx en JSON que reciben las pruebas se valida contra el
esquema que su ruta declara en OpenAPI (response_model, o el modelo de
`responses`). Así la documentación no puede quedar desactualizada: si una
ruta devuelve algo distinto de lo que dice, falla la prueba que la llamó.

Con RICORA_CONTRATO_INFORME=<archivo> no falla: anota cada diferencia en
el archivo (una línea JSON por diferencia), para revisarlas todas juntas.
"""

import json
import os
from urllib.parse import urlsplit

from fastapi.routing import APIRoute
from pydantic import TypeAdapter, ValidationError
from starlette.routing import Match

_ADAPTADORES: dict = {}


def ruta_de(app, metodo: str, ruta: str) -> APIRoute | None:
    alcance = {"type": "http", "path": ruta, "method": metodo.upper()}
    for r in app.routes:
        if isinstance(r, APIRoute):
            coincide, _ = r.matches(alcance)
            if coincide == Match.FULL:
                return r
    return None


def modelo_de(route: APIRoute, codigo: int):
    """El modelo de `responses` manda (documenta todas las formas posibles de la
    respuesta); si no hay, el response_model de la ruta."""
    declarado = (route.responses or {}).get(codigo) or (route.responses or {}).get(str(codigo)) or {}
    if declarado.get("model") is not None:
        return declarado["model"]
    if route.response_model is not None and codigo == (route.status_code or 200):
        return route.response_model
    return None


def validar(app, metodo: str, url: str, respuesta) -> None:
    if not (200 <= respuesta.status_code < 300) or respuesta.status_code == 204 or not respuesta.content:
        return
    if not respuesta.headers.get("content-type", "").startswith("application/json"):
        return
    ruta = urlsplit(str(url)).path
    if ruta.startswith("/api/v1/"):
        ruta = "/api/" + ruta[len("/api/v1/"):]
    route = ruta_de(app, metodo, ruta)
    if route is None:
        return
    modelo = modelo_de(route, respuesta.status_code)
    if modelo is None:
        _fallo(route, metodo, respuesta.status_code, "la ruta no declara esquema de respuesta")
        return
    adaptador = _ADAPTADORES.setdefault(modelo, TypeAdapter(modelo))
    try:
        adaptador.validate_python(respuesta.json())
    except ValidationError as exc:
        _fallo(route, metodo, respuesta.status_code, str(exc)[:1500])


def _fallo(route, metodo, codigo, motivo) -> None:
    informe = os.environ.get("RICORA_CONTRATO_INFORME")
    if informe:
        with open(informe, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ruta": route.path, "metodo": metodo.upper(), "codigo": codigo,
                                "funcion": f"{route.endpoint.__module__}.{route.endpoint.__name__}",
                                "motivo": motivo}, ensure_ascii=False) + "\n")
        return
    raise AssertionError(f"Contrato de la API: {metodo.upper()} {route.path} ({codigo}) — {motivo}")
