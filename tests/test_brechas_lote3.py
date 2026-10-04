"""
Cierre de brechas, lote 3 · Endurecimiento (NFR-01):

- cabeceras de seguridad: política de contenido (CSP) en todas las
  respuestas y HSTS solo cuando la conexión es HTTPS;
- la salud dice si RICORA se publica sin HTTPS;
- el despliegue ya no restablece la contraseña de la cuenta administradora:
  solo la fija al crearla o si se pide expresamente.
"""

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.seguridad import verificar_contrasena
from app.main import app
from app.models.usuario import Usuario


def test_csp_en_todas_las_respuestas_y_hsts_solo_con_https(cliente):
    r = cliente.get("/api/salud")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "'unsafe-eval'" not in csp
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "upgrade-insecure-requests" not in csp
    assert "strict-transport-security" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"
    with TestClient(app, base_url="https://testserver") as seguro:
        s = seguro.get("/api/salud")
    assert s.headers["strict-transport-security"].startswith("max-age=31536000")
    assert "upgrade-insecure-requests" in s.headers["content-security-policy"]


def test_la_documentacion_de_la_api_tiene_su_propia_politica(cliente):
    docs = cliente.get("/api/docs").headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in docs
    # La interfaz no admite guiones de terceros ni en línea.
    interfaz = cliente.get("/api/salud").headers["content-security-policy"]
    script = next(p for p in interfaz.split(";") if p.strip().startswith("script-src"))
    assert "jsdelivr" not in script and "unsafe-inline" not in script


def test_la_salud_dice_si_se_publica_sin_https(cliente, monkeypatch):
    monkeypatch.setattr(settings, "url_publica", "http://localhost:8000")
    assert cliente.get("/api/salud").json()["conexion"]["ok"]  # instalación local
    monkeypatch.setattr(settings, "url_publica", "http://203.0.113.5")
    d = cliente.get("/api/salud").json()
    assert d["estado"] == "degradado" and not d["conexion"]["ok"]
    assert "clasificados o reservados" in d["conexion"]["motivo"]
    monkeypatch.setattr(settings, "url_publica", "https://203-0-113-5.sslip.io")
    assert cliente.get("/api/salud").json()["conexion"] == {"ok": True, "cifrada": True}


def test_el_despliegue_no_pisa_la_contrasena_que_cambio_la_persona(db, monkeypatch):
    from app import cli
    from app.core.seguridad import cifrar_contrasena

    @contextmanager
    def _misma_sesion():
        yield db

    monkeypatch.setattr(cli, "SessionLocal", _misma_sesion)
    monkeypatch.setenv("RICORA_ADMIN_CORREO", "admin3@correo.com")
    monkeypatch.setenv("RICORA_ADMIN_PASSWORD", "Despliegue2026ok")
    monkeypatch.delenv("RICORA_ADMIN_RESTABLECER", raising=False)
    assert cli.cuenta_administradora() == 0
    u = db.scalar(select(Usuario).where(Usuario.correo == "admin3@correo.com"))
    assert verificar_contrasena("Despliegue2026ok", u.contrasena_hash)  # al crearla, la del secreto
    # La persona la cambia en «Mi perfil»; el siguiente despliegue no la toca.
    u.contrasena_hash = cifrar_contrasena("PropiaYSegura2026")
    db.commit()
    assert cli.cuenta_administradora() == 0
    db.refresh(u)
    assert verificar_contrasena("PropiaYSegura2026", u.contrasena_hash)
    # Solo con la petición expresa (nadie la recuerda) vuelve a la del secreto.
    monkeypatch.setenv("RICORA_ADMIN_RESTABLECER", "1")
    assert cli.cuenta_administradora() == 0
    db.refresh(u)
    assert verificar_contrasena("Despliegue2026ok", u.contrasena_hash)
