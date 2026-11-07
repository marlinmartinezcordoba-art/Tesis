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
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "ollama_url", "http://ia_local:11434")
    monkeypatch.setattr(settings, "modelo_local", "qwen2.5:7b")
    pedidos = []

    def post(url, json=None, timeout=None, **_):
        pedidos.append((url, json, timeout))
        contenido = '{"filas": [{"serie": "Actas"}]}' if json.get("format") else "El RiC es el modelo del ICA."
        return Respuesta(200, {"model": "qwen2.5:7b", "message": {"content": contenido}, "eval_count": 12})

    monkeypatch.setattr(motor.httpx, "post", post)
    return pedidos


def test_con_ia_local_sin_clave_se_usa_solo_ollama(local, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    m = motor.motor_activo()
    assert isinstance(m, motor.MotorLocal)
    assert m.modelo == "qwen2.5:7b"


def test_con_ia_local_y_clave_trabajan_los_dos(local, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    m = motor.motor_activo()
    assert isinstance(m, motor.MotorConsenso)
    assert "qwen2.5:7b" in m.nombre and "gemini" in m.nombre


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
    assert local[0][1]["options"]["num_predict"] == 900


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


# --- Consenso: Gemini y la IA local juntos ------------------------------------------------------------


def test_combinar_sube_lo_que_proponen_los_dos_y_marca_lo_de_uno_solo():
    gemini = {"titulo": "Acta del Concejo", "alcance_contenido": "Sesión ordinaria.", "evidencia_titulo": [],
              "evidencia_alcance": [], "entidades": [
                  {"tipo": "agente", "valor": "Concejo Municipal de Tunja", "fragmento": "Concejo Municipal de Tunja",
                   "documento": 1, "confianza": 0.8},
                  {"tipo": "fecha", "valor": "20 de julio de 1948", "edtf": "1948-07-20", "fragmento": "20 de julio",
                   "documento": 1, "confianza": 0.9},
                  {"tipo": "lugar", "valor": "Tunja", "fragmento": "Tunja", "documento": 1, "confianza": 0.9}]}
    local = {"titulo": "Acta", "alcance_contenido": "", "evidencia_titulo": [], "evidencia_alcance": [], "entidades": [
        {"tipo": "agente", "valor": "Concejo municipal de Tunja.", "fragmento": "Concejo", "documento": 1, "confianza": 0.7},
        {"tipo": "fecha", "valor": "1948-07-20", "edtf": "1948-07-20", "fragmento": "1948", "documento": 1, "confianza": 0.6},
        {"tipo": "agente", "valor": "Alcalde Pedro Gómez", "fragmento": "Alcalde", "documento": 1, "confianza": 0.9}]}
    c = motor.combinar(gemini, local)
    por_valor = {e["valor"]: e for e in c["entidades"]}
    assert c["titulo"] == "Acta del Concejo"
    assert por_valor["Concejo Municipal de Tunja"]["acuerdo"] == "ambos"
    assert por_valor["Concejo Municipal de Tunja"]["confianza"] == pytest.approx(0.9)
    assert por_valor["20 de julio de 1948"]["acuerdo"] == "ambos"
    # Lo que propuso uno solo queda por debajo del umbral de revisión (0,70).
    assert por_valor["Tunja"]["acuerdo"] == "gemini" and por_valor["Tunja"]["confianza"] <= 0.6
    assert por_valor["Alcalde Pedro Gómez"]["acuerdo"] == "local" and por_valor["Alcalde Pedro Gómez"]["confianza"] <= 0.6
    assert c["acuerdo"] == {"ambos": 2, "gemini": 1, "local": 1}


class _Falso:
    def __init__(self, modelo, respuesta=None, falla=None):
        self.modelo, self.nombre, self.respuesta, self.falla = modelo, modelo, respuesta, falla
        self.ultima = {"version_modelo": modelo, "fuentes": [{"titulo": "AGN", "url": "https://www.archivogeneral.gov.co"}]}
        self.buscar = None

    def analizar(self, documentos, nivel, contexto=None):
        if self.falla:
            raise motor.MotorError(self.falla)
        return self.respuesta

    def conversar(self, instruccion, contenido, buscar=False):
        if self.falla:
            raise motor.MotorError(self.falla)
        self.buscar = buscar
        return f"respuesta de {self.modelo}"


def _consenso(nube, local):
    m = motor.MotorConsenso.__new__(motor.MotorConsenso)
    motor.MotorConsenso.__init__(m, nube, local)
    return m


def test_consenso_guarda_las_dos_respuestas_y_las_combina():
    a = {"titulo": "T", "alcance_contenido": "A", "entidades": [{"tipo": "lugar", "valor": "Tunja", "confianza": 0.8}]}
    b = {"titulo": "T2", "alcance_contenido": "", "entidades": [{"tipo": "lugar", "valor": "Tunja", "confianza": 0.7}]}
    m = _consenso(_Falso("gemini-x", a), _Falso("qwen-x", b))
    r = m.analizar([], "unidad_documental")
    assert r["entidades"][0]["acuerdo"] == "ambos"
    assert m.por_motor == {"gemini": a, "local": b}
    assert m.nombre == "consenso (gemini-x + qwen-x)"


def test_si_responde_uno_solo_la_propuesta_queda_a_su_nombre():
    """Para no mezclar motores en la evaluación: sin consenso, la propuesta lleva el nombre del que respondió."""
    a = {"titulo": "T", "alcance_contenido": "A", "entidades": []}
    m = _consenso(_Falso("gemini-x", falla="límite de uso"), _Falso("qwen-x", a))
    assert m.analizar([], "unidad_documental") == a
    assert m.nombre == "qwen-x"
    assert m.por_motor["errores"] == {"gemini": "límite de uso"}


def test_el_asistente_usa_gemini_con_busqueda_y_si_falla_la_ia_local():
    nube, local = _Falso("gemini-x"), _Falso("qwen-x")
    m = _consenso(nube, local)
    assert m.conversar("i", [], buscar=True) == "respuesta de gemini-x" and nube.buscar is True
    assert m.ultima["fuentes"][0]["url"].startswith("https://www.archivogeneral")
    m = _consenso(_Falso("gemini-x", falla="límite"), local)
    assert m.conversar("i", [], buscar=True) == "respuesta de qwen-x" and m.respondio == "qwen-x"


def test_gemini_pide_la_busqueda_de_google_y_devuelve_las_fuentes(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    pedidos = []

    def post(url, json=None, headers=None, timeout=None, **_):
        pedidos.append(json)
        return Respuesta(200, {"modelVersion": "gemini-x", "candidates": [{
            "content": {"parts": [{"text": "El RiC es "}, {"text": "el modelo del ICA."}]},
            "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://www.ica.org/ric", "title": "ICA"}},
                                                      {"web": {"uri": "https://www.ica.org/ric", "title": "ICA"}}]}}]})

    monkeypatch.setattr(motor.httpx, "post", post)
    g = motor.MotorGemini("clave-de-prueba", "gemini-x")
    assert g.conversar("i", [{"role": "user", "parts": [{"text": "¿Qué es el RiC?"}]}], buscar=True) == \
        "El RiC es el modelo del ICA."
    assert pedidos[0]["tools"] == [{"google_search": {}}]
    assert g.ultima["fuentes"] == [{"titulo": "ICA", "url": "https://www.ica.org/ric"}]
