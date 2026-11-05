"""Límite de intentos de ingreso por dirección IP, además del bloqueo por cuenta."""

from app.routers import auth
from tests.conftest import crear_usuario


def test_muchos_fallidos_desde_un_equipo_bloquean_aunque_sean_cuentas_distintas(cliente, db, monkeypatch):
    monkeypatch.setattr(auth, "INTENTOS_POR_IP", 3)
    crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    for i in range(3):  # tres cuentas distintas: el bloqueo por cuenta no salta
        r = cliente.post("/api/auth/login", json={"correo": f"otra{i}@correo.com", "contrasena": "equivocada"})
        assert r.status_code == 401
    r = cliente.post("/api/auth/login", json={"correo": "ana@correo.com", "contrasena": "equivocada"})
    assert r.status_code == 429 and "este equipo" in r.json()["detail"]
