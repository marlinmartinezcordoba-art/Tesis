"""IA local (Ollama): RICORA le hace los mismos pedidos que a Gemini y los traduce a la API de Ollama.
Ningún texto sale del servidor. Aquí no se llama a ningún servicio: httpx.post se reemplaza."""

import json

import pytest

from app.core.config import settings
from app.servicios import asistente, motor


class Respuesta:
    def __init__(self, status_code=200, datos=None):
        self.status_code = status_code
        self._datos = datos or {}
        self.text = json.dumps(self._datos)

    def json(self):
        return self._datos


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(settings, "motor_ia", "local")
    monkeypatch.setattr(settings, "ollama_url", "http://ia_local:11434")
    monkeypatch.setattr(settings, "modelo_local", "qwen2.5:7b")
    pedidos = []

    def post(url, json=None, timeout=None, **_):
        pedidos.append((url, json, timeout))
        contenido = '{"filas": [{"serie": "Actas"}]}' if json.get("format") else "El RiC es el modelo del ICA."
        return Respuesta(200, {"model": "qwen2.5:7b", "message": {"content": contenido}, "eval_count": 12})

    monkeypatch.setattr(motor.httpx, "post", post)
    return pedidos


def test_con_motor_local_se_usa_ollama_y_no_gemini(local, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    m = motor.motor_activo()
    assert isinstance(m, motor.MotorLocal)
    assert m.modelo == "qwen2.5:7b"


def test_sin_motor_local_sigue_gemini(monkeypatch):
    monkeypatch.setattr(settings, "motor_ia", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    m = motor.motor_activo()
    assert type(m) is motor.MotorGemini


def test_estructurar_traduce_el_esquema_y_los_mensajes(local):
    m = motor.motor_activo()
    esquema = {"type": "OBJECT", "properties": {"filas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "serie": {"type": "STRING", "nullable": True}}}}}}
    datos = m.estructurar("Lee la TRD.", "texto de la TRD", esquema)
    assert datos == {"filas": [{"serie": "Actas"}]}
    url, pedido, tiempo = local[0]
    assert url == "http://ia_local:11434/api/chat"
    assert pedido["model"] == "qwen2.5:7b" and pedido["stream"] is False
    assert pedido["messages"] == [{"role": "system", "content": "Lee la TRD."},
                                  {"role": "user", "content": "texto de la TRD"}]
    assert pedido["format"] == {"type": "object", "properties": {"filas": {"type": "array", "items": {
        "type": "object", "properties": {"serie": {"type": "string"}}}}}}
    assert pedido["options"]["temperature"] == 0
    assert tiempo == settings.segundos_motor_local


def test_conversar_pasa_los_turnos_del_asistente(local):
    m = motor.motor_activo()
    texto = m.conversar("Eres el asistente.", [{"role": "user", "parts": [{"text": "Hola"}]},
                                                 {"role": "model", "parts": [{"text": "Hola, ¿en qué ayudo?"}]},
                                                 {"role": "user", "parts": [{"text": "¿Qué es el RiC?"}]}])
    assert texto == "El RiC es el modelo del ICA."
    roles = [x["role"] for x in local[0][1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert local[0][1]["options"]["num_predict"] == 700


def test_modelo_sin_descargar_da_un_mensaje_claro(local, monkeypatch):
    monkeypatch.setattr(motor.httpx, "post", lambda *a, **k: Respuesta(404, {"error": "model not found"}))
    with pytest.raises(motor.MotorError, match="se está descargando"):
        motor.motor_activo().conversar("x", [{"role": "user", "parts": [{"text": "hola"}]}])


def test_sin_conexion_con_la_ia_local_da_un_mensaje_claro(local, monkeypatch):
    def caida(*a, **k):
        raise motor.httpx.ConnectError("sin conexión")

    monkeypatch.setattr(motor.httpx, "post", caida)
    with pytest.raises(motor.MotorError, match="no responde"):
        motor.motor_activo().conversar("x", [{"role": "user", "parts": [{"text": "hola"}]}])


def test_el_asistente_avisa_que_la_ia_es_local(local):
    e = asistente.estado()
    assert e["disponible"] and e["local"]
    assert "no sale" in e["aviso"]
