"""
Asistente RICORA con IA (app/servicios/asistente.py).

Sin motor configurado responde 503 y la pantalla queda en modo guiado. Con motor,
envía la conversación con la instrucción del asistente y el contexto de la pantalla,
y la auditoría registra la consulta sin guardar el texto de la pregunta.
"""

import pytest
from sqlalchemy import select

from app.models.auditoria import RegistroAuditoria
from app.servicios import asistente, motor
from tests.conftest import crear_usuario, ingresar


class MotorFalso:
    modelo = "modelo-de-prueba"

    def __init__(self):
        self.recibido = None

    def conversar(self, instruccion, contenido, buscar=False):
        self.recibido = (instruccion, contenido)
        return "**Respuesta** de prueba: vaya a Instrumentos > TRD y CCD."


@pytest.fixture()
def falso(monkeypatch):
    m = MotorFalso()
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    return m


def test_sin_motor_queda_en_modo_guiado(cliente, db, monkeypatch):
    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    ana = ingresar(cliente, "ana@correo.com")
    e = cliente.get("/api/asistente/estado", headers=ana).json()
    assert e["disponible"] is False and "reserva legal" in e["aviso"]
    r = cliente.post("/api/asistente/preguntar", headers=ana, json={"mensajes": [{"rol": "persona", "texto": "Hola"}]})
    assert r.status_code == 503 and "motor de análisis" in r.json()["detail"]


def test_responde_con_contexto_y_audita_sin_guardar_la_pregunta(cliente, db, falso):
    usuario = crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    ana = ingresar(cliente, "ana@correo.com")
    assert cliente.get("/api/asistente/estado", headers=ana).json()["disponible"] is True
    pregunta = "¿Cómo cargo la TRD de la cédula 1234567?"
    r = cliente.post("/api/asistente/preguntar", headers=ana, json={
        "mensajes": [{"rol": "persona", "texto": "Hola"}, {"rol": "asistente", "texto": "¿En qué le ayudo?"},
                     {"rol": "persona", "texto": pregunta}],
        "pantalla": {"titulo": "Fondos · Cargar CCD y TRD", "pasos": ["Todo parte de aquí."]},
        "fondo": "Instituto de prueba"})
    assert r.status_code == 200, r.text
    assert r.json()["respuesta"].startswith("Respuesta de prueba") and "**" not in r.json()["respuesta"]
    instruccion, contenido = falso.recibido
    assert "RiC-O" in instruccion and "Ley 594" in instruccion
    assert [c["role"] for c in contenido] == ["user", "model", "user"]
    ultimo = contenido[-1]["parts"][0]["text"]
    assert "Instituto de prueba" in ultimo and "Cargar CCD y TRD" in ultimo and "¿Cómo cargo la TRD de la cédula" in ultimo
    # La cédula no sale del servidor (Ley 1581): llega al motor reemplazada por su tipo.
    assert "1234567" not in ultimo and "[Cédula" in ultimo
    evento = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "asistente_consultado"))
    assert evento.usuario_id == usuario.id and evento.valor_nuevo["modelo"] == "modelo-de-prueba"
    assert "1234567" not in str(evento.valor_nuevo) and "1234567" not in (evento.detalle or "")


def test_exige_sesion_y_una_pregunta_al_final(cliente, db, falso):
    assert cliente.post("/api/asistente/preguntar", json={"mensajes": [{"rol": "persona", "texto": "Hola"}]}).status_code == 401
    crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    ana = ingresar(cliente, "ana@correo.com")
    r = cliente.post("/api/asistente/preguntar", headers=ana, json={"mensajes": [{"rol": "asistente", "texto": "Hola"}]})
    assert r.status_code == 422
    largo = [{"rol": "persona" if i % 2 == 0 else "asistente", "texto": f"m{i}"} for i in range(25)]
    assert cliente.post("/api/asistente/preguntar", headers=ana, json={"mensajes": largo}).status_code == 200
    assert len(falso.recibido[1]) == asistente.MAX_TURNOS


def test_el_revisor_de_solo_lectura_tambien_puede_preguntar(cliente, db, falso):
    crear_usuario(db, "rev@correo.com", "revisor", nombre="Rosa Vélez")
    rev = ingresar(cliente, "rev@correo.com")
    r = cliente.post("/api/asistente/preguntar", headers=rev, json={"mensajes": [{"rol": "persona", "texto": "¿Qué es el FUID?"}]})
    assert r.status_code == 200
