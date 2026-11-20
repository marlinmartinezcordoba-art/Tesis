"""
Módulo de evaluación apagado (RICORA_EVALUACION=0, el valor por defecto).

- La API de evaluación responde 404 para todos, también la administración.
- La sesión dice que está apagado (la interfaz lo quita del menú).
- Los datos no se tocan: al encenderlo (RICORA_EVALUACION=1) vuelven.
"""

from app.core.config import settings
from tests.conftest import CONTRASENA


def test_apagada_la_api_no_existe_y_la_sesion_lo_dice(cliente, admin, cabeceras_admin, monkeypatch):
    assert cliente.get("/api/evaluacion/propiedades", headers=cabeceras_admin).status_code == 200
    monkeypatch.setattr(settings, "evaluacion_activa", False)
    r = cliente.get("/api/evaluacion/propiedades", headers=cabeceras_admin)
    assert r.status_code == 404 and "desactivado" in r.json()["detail"]
    usuario = cliente.post("/api/auth/login", json={"correo": admin.correo, "contrasena": CONTRASENA}).json()["usuario"]
    assert usuario["evaluacion_activa"] is False
