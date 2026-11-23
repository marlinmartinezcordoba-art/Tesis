"""
Módulo de evaluación apagado (RICORA_EVALUACION=0; por defecto está encendido).

- La API de evaluación responde 404 para todos, también la administración.
- La sesión dice que está apagado (la interfaz lo quita del menú).
- Los datos no se tocan: al encenderlo (RICORA_EVALUACION=1) vuelven.
"""

from app.core.config import settings
from tests.conftest import CONTRASENA


def test_apagada_la_api_no_existe_y_la_sesion_lo_dice(cliente, admin, cabeceras_admin, monkeypatch):
    import uuid

    ruta = f"/api/evaluacion/{uuid.uuid4()}"
    assert "desactivado" not in cliente.get(ruta, headers=cabeceras_admin).text  # encendido por defecto
    monkeypatch.setattr(settings, "evaluacion_activa", False)
    r = cliente.get(ruta, headers=cabeceras_admin)
    assert r.status_code == 404 and "desactivado" in r.json()["detail"]
    usuario = cliente.post("/api/auth/login", json={"correo": admin.correo, "contrasena": CONTRASENA}).json()["usuario"]
    assert usuario["evaluacion_activa"] is False
