"""
Cierre de brechas, lote 1 (matriz maestra v3.0, auditoría del 4 de octubre):

- RF-AUD-002: el registro de auditoría encadena la huella de cada evento con
  la del anterior; alterar o quitar un evento rompe la cadena aunque alguien
  desactive el disparador de solo anexar.
- RF-OPS-001 / NFR-10: /api/salud revisa de verdad la base, el almacén, el
  trabajador y el respaldo, para un monitor externo.
- RF-SEC-003: segundo factor TOTP con códigos de respaldo, exigible por rol.
"""

import os
import time
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.core import doble_factor
from app.core.config import settings
from app.models.auditoria import RegistroAuditoria
from app.models.usuario import Usuario
from app.servicios import parametros, salud
from app.servicios.auditoria import registrar, verificar_cadena
from tests.conftest import CONTRASENA, crear_usuario, ingresar


# --- RF-AUD-002: auditoría encadenada ----------------------------------------------------------


def _eventos(db, n=3):
    for k in range(n):
        registrar(db, modulo="autenticacion", accion="inicio_sesion", detalle=f"evento {k}",
                  nuevo={"b": 2, "a": [1, k]})
    db.flush()
    return db.scalars(select(RegistroAuditoria).order_by(RegistroAuditoria.orden.desc()).limit(n)).all()[::-1]


def test_cada_evento_queda_encadenado_con_el_anterior(db):
    a, b, c = _eventos(db)
    db.expire_all()
    a, b, c = (db.get(RegistroAuditoria, x.id) for x in (a, b, c))
    assert (b.orden, c.orden) == (a.orden + 1, a.orden + 2)
    assert b.huella_anterior == a.huella and c.huella_anterior == b.huella
    assert len(c.huella) == 64
    v = verificar_cadena(db)
    assert v["integra"] and v["roto_en"] is None and v["sello"]["huella"] == c.huella


def test_alterar_o_quitar_un_evento_rompe_la_cadena_aunque_se_desactive_el_disparador(db):
    a, b, c = _eventos(db)
    db.execute(text("ALTER TABLE registro_auditoria DISABLE TRIGGER registro_auditoria_inmutable"))
    db.execute(text("UPDATE registro_auditoria SET detalle = 'alterado' WHERE id = :i"), {"i": b.id})
    assert verificar_cadena(db)["roto_en"] == b.orden
    db.execute(text("UPDATE registro_auditoria SET detalle = 'evento 1' WHERE id = :i"), {"i": b.id})
    assert verificar_cadena(db)["integra"]
    db.execute(text("DELETE FROM registro_auditoria WHERE id = :i"), {"i": b.id})
    assert verificar_cadena(db)["roto_en"] == c.orden
    db.execute(text("ALTER TABLE registro_auditoria ENABLE TRIGGER registro_auditoria_inmutable"))


def test_la_cadena_por_la_api_y_el_sello_en_la_revision_semanal(cliente, db, cabeceras_admin):
    r = cliente.get("/api/auditoria/cadena", headers=cabeceras_admin)
    assert r.status_code == 200 and r.json()["integra"], r.text
    r = cliente.post("/api/auditoria/consolidado/revisado", headers=cabeceras_admin, json={"nota": "ok"})
    assert r.status_code == 200, r.text
    ev = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "consolidado_revisado"))
    assert ev.valor_nuevo["cadena_integra"] is True and len(ev.valor_nuevo["sello"]["huella"]) == 64


# --- RF-OPS-001 / NFR-10: salud real -------------------------------------------------------------


def test_salud_dice_que_falta_y_solo_la_base_tumba_el_servicio(cliente, monkeypatch):
    latido = Path(settings.directorio_almacenamiento) / salud.ARCHIVO_LATIDO
    latido.unlink(missing_ok=True)
    r = cliente.get("/api/salud")
    assert r.status_code == 200
    d = r.json()
    assert d["base_de_datos"]["ok"] and d["almacen"]["ok"]
    assert d["estado"] == "degradado" and not d["trabajador"]["ok"] and not d["respaldo"]["ok"]
    salud.latir()
    assert cliente.get("/api/salud").json()["trabajador"]["ok"]
    viejo = time.time() - salud.LATIDO_MAXIMO_S - 60
    os.utime(latido, (viejo, viejo))
    assert "no responde" in cliente.get("/api/salud").json()["trabajador"]["motivo"]
    monkeypatch.setattr(salud, "_base", lambda db: {"ok": False, "motivo": "La base de datos no responde."})
    caida = cliente.get("/api/salud")
    assert caida.status_code == 503 and caida.json()["estado"] == "caido"
    # Sin sesión y sin datos sensibles: ni rutas ni contraseñas.
    assert "almacen" in caida.json() and settings.database_url not in caida.text


# --- RF-SEC-003: segundo factor ----------------------------------------------------------------


def _activar(cliente, cab):
    r = cliente.post("/api/auth/perfil/doble-factor/iniciar", headers=cab)
    assert r.status_code == 200, r.text
    clave = r.json()["clave"]
    assert r.json()["uri"].startswith("otpauth://totp/RICORA:")
    malo = cliente.post("/api/auth/perfil/doble-factor/activar", headers=cab, json={"codigo": "000000"})
    assert malo.status_code == 400
    r = cliente.post("/api/auth/perfil/doble-factor/activar", headers=cab,
                     json={"codigo": doble_factor.codigo(clave, doble_factor.paso_actual())})
    assert r.status_code == 200, r.text
    return clave, r.json()["codigos_respaldo"]


def test_totp_cumple_los_vectores_del_rfc_6238():
    import base64

    clave = base64.b32encode(b"12345678901234567890").decode()
    assert [doble_factor.codigo(clave, t // 30) for t in (59, 1111111109, 1234567890, 2000000000)] == \
        ["287082", "081804", "005924", "279037"]
    # Un código ya usado no vuelve a servir.
    paso = doble_factor.paso_actual()
    assert doble_factor.verificar(clave, doble_factor.codigo(clave, paso), paso) is None


def test_ingreso_en_dos_pasos_con_codigo_y_con_respaldo(cliente, db):
    crear_usuario(db, "dos@ricora.prueba", "archivista")
    cab = ingresar(cliente, "dos@ricora.prueba")
    clave, respaldo = _activar(cliente, cab)
    assert len(respaldo) == 8
    db.expire_all()
    u = db.scalar(select(Usuario).where(Usuario.correo == "dos@ricora.prueba"))
    assert u.mfa_activo and respaldo[0] not in str(u.mfa_respaldo)  # solo huellas
    assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "segundo_factor_activado"))

    paso1 = cliente.post("/api/auth/login", json={"correo": "dos@ricora.prueba", "contrasena": CONTRASENA})
    assert paso1.status_code == 200 and paso1.json()["segundo_factor"] and "token_acceso" not in paso1.json()
    desafio = paso1.json()["desafio"]
    # El desafío no sirve como token de acceso.
    assert cliente.get("/api/auth/perfil", headers={"Authorization": f"Bearer {desafio}"}).status_code == 401
    malo = cliente.post("/api/auth/login/segundo-factor", json={"desafio": desafio, "codigo": "123456"})
    assert malo.status_code == 401
    bien = cliente.post("/api/auth/login/segundo-factor", json={"desafio": desafio, "codigo": respaldo[0]})
    assert bien.status_code == 200 and bien.json()["usuario"]["doble_factor"], bien.text
    # El código de respaldo se gasta.
    otra = cliente.post("/api/auth/login/segundo-factor", json={"desafio": desafio, "codigo": respaldo[0]})
    assert otra.status_code == 401
    # Con el código de la aplicación, en el paso siguiente (el de la activación ya se usó).
    siguiente = doble_factor.codigo(clave, doble_factor.paso_actual() + 1)
    r = cliente.post("/api/auth/login/segundo-factor", json={"desafio": desafio, "codigo": siguiente})
    assert r.status_code == 200, r.text


def test_rol_que_exige_segundo_factor_solo_entra_a_mi_perfil_hasta_configurarlo(cliente, db, admin, cabeceras_admin):
    parametros.cambiar(db, "doble_factor_roles", ["archivista"], admin.id, "autenticacion")
    db.commit()
    crear_usuario(db, "obligada@ricora.prueba", "archivista")
    cab = ingresar(cliente, "obligada@ricora.prueba")
    bloqueada = cliente.get("/api/descripcion/cola", headers=cab)
    assert bloqueada.status_code == 403 and bloqueada.json()["detail"] == "segundo_factor_requerido"
    perfil = cliente.get("/api/auth/perfil/doble-factor", headers=cab).json()
    assert perfil == {"activo": False, "activado_en": None, "requerido": True, "codigos_respaldo": 0}
    _activar(cliente, cab)
    assert cliente.get("/api/descripcion/cola", headers=cab).status_code != 403
    # No puede quitárselo mientras su rol lo exija; el administrador sí lo restablece (teléfono perdido).
    u = db.scalar(select(Usuario).where(Usuario.correo == "obligada@ricora.prueba"))
    r = cliente.post(f"/api/auth/usuarios/{u.id}/doble-factor/restablecer", headers=cab)
    assert r.status_code == 403
    r = cliente.post(f"/api/auth/usuarios/{u.id}/doble-factor/restablecer", headers=cabeceras_admin)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert not db.get(Usuario, u.id).mfa_activo
    assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "segundo_factor_restablecido"))


@pytest.mark.parametrize("valor", [["administrador"], []])
def test_el_parametro_acepta_listas_de_roles(db, admin, valor):
    parametros.cambiar(db, "doble_factor_roles", valor, admin.id, "autenticacion")
    assert parametros.leer(db, "doble_factor_roles") == valor
    with pytest.raises(ValueError):
        parametros.cambiar(db, "doble_factor_roles", "administrador", admin.id, "autenticacion")
