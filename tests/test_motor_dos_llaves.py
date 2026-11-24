"""Dos llaves de Gemini: los pedidos se reparten y, si una agota su cuota, se sigue con la otra."""

import json

import httpx

from app.servicios import motor


class _Respuesta:
    def __init__(self, codigo, texto=""):
        self.status_code, self.text = codigo, texto

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}]}


def test_si_una_llave_agota_la_cuota_sigue_con_la_otra(monkeypatch):
    usadas = []

    def post(url, json=None, headers=None, timeout=None):  # noqa: A002
        usadas.append(headers["x-goog-api-key"])
        return _Respuesta(429, "quota exceeded") if headers["x-goog-api-key"] == "agotada" else _Respuesta(200)

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(motor.time, "sleep", lambda s: None)
    m = motor.MotorGemini(["agotada", "buena"], "gemini-x")
    for _ in range(3):
        assert m._llamar({"contents": []})
    assert set(usadas) == {"agotada", "buena"} and usadas.count("buena") == 3


def test_con_una_sola_llave_funciona_como_antes(monkeypatch):
    usadas = []
    monkeypatch.setattr(httpx, "post", lambda url, json=None, headers=None, timeout=None:
                        usadas.append(headers["x-goog-api-key"]) or _Respuesta(200))
    assert motor.MotorGemini("unica", "gemini-x")._llamar({"contents": []})
    assert usadas == ["unica"]
