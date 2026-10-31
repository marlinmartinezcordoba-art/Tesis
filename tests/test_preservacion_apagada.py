"""
Preservación digital apagada (RICORA_PRESERVACION=0, el valor por defecto).

- La API de preservación responde 404 para todos, también la administración.
- Los permisos del rol que se entregan a la interfaz no incluyen el módulo,
  y la sesión dice que está apagado (la interfaz oculta lo que depende de él).
- La salud del servidor no se degrada por no tener respaldos programados.
- Los datos y los permisos guardados no se tocan: al encenderlo vuelven.
"""

from app.core.config import settings
from app.core.permisos import permisos_efectivos
from app.servicios import salud
from tests.conftest import CONTRASENA


def test_apagada_la_api_no_existe_y_la_sesion_lo_dice(cliente, db, admin, cabeceras_admin, monkeypatch):
    assert cliente.get("/api/preservacion/respaldos", headers=cabeceras_admin).status_code == 200
    monkeypatch.setattr(settings, "preservacion_activa", False)
    for ruta in ("/api/preservacion/respaldos", "/api/preservacion/panel"):
        r = cliente.get(ruta, headers=cabeceras_admin)
        assert r.status_code == 404 and "desactivado" in r.json()["detail"]
    sesion = cliente.post("/api/auth/login", json={"correo": admin.correo, "contrasena": CONTRASENA}).json()
    usuario = sesion["usuario"]
    assert usuario["preservacion_activa"] is False and "preservacion" not in usuario["permisos"]
    assert "descripcion" in usuario["permisos"]
    assert "preservacion" not in cliente.get("/api/auth/perfil", headers=cabeceras_admin).json()["permisos"]
    # Lo guardado en el rol no cambia: solo se filtra al entregarlo.
    assert permisos_efectivos({"preservacion": "escribir", "ingesta": "leer"}) == {"ingesta": "leer"}
    assert salud._respaldo(db)["ok"] is True


def test_encendida_vuelve(monkeypatch):
    monkeypatch.setattr(settings, "preservacion_activa", True)
    assert permisos_efectivos({"preservacion": "escribir"}) == {"preservacion": "escribir"}


def test_apagada_no_es_un_paso_del_avance_del_fondo(cliente, db, cabeceras_admin, monkeypatch):
    """La tesis no trata la preservación: con el módulo apagado no aparece en el avance del fondo."""
    from tests.test_disposicion import _fondo

    fnd, _, _ = _fondo(cliente, db, cabeceras_admin)
    monkeypatch.setattr(settings, "preservacion_activa", False)
    pasos = [p["clave"] for p in cliente.get(f"/api/fondos/{fnd.id}/avance", headers=cabeceras_admin).json()["pasos"]]
    assert "preservacion" not in pasos and pasos[0] == "instrumentos"
