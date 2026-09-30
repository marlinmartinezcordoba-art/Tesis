"""
Pruebas del módulo transversal de autenticación y autorización
(sección 10 del prompt del módulo), más las del ciclo de sesión, los
enlaces de un solo uso y la auditoría que este módulo activa.
"""

import re
from datetime import timedelta

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core import permisos
from app.core.config import settings
from app.db.base import ahora
from app.db.session import get_db
from app.main import RUTAS_PUBLICAS, app
from app.models.auditoria import RegistroAuditoria
from app.models.sesion import Sesion
from app.models.token_acceso import TokenUnUso
from app.models.usuario import Usuario
from tests.conftest import CONTRASENA, crear_usuario, ingresar

NUEVA = "Fondo1930historico"


def eventos(db, accion, **filtros):
    consulta = select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
    for campo, valor in filtros.items():
        consulta = consulta.where(getattr(RegistroAuditoria, campo) == valor)
    return db.scalars(consulta.order_by(RegistroAuditoria.id)).all()


def token_de(texto):
    return re.search(r"/acceso/([\w-]+)", texto).group(1)


# --- Inicio de sesión ---------------------------------------------------------------


class TestIngreso:
    def test_ingreso_correcto_devuelve_token_rol_y_galleta(self, cliente, db):
        u = crear_usuario(db, "catalina@ricora.prueba", "archivista")
        r = cliente.post("/api/auth/login", json={"correo": "  Catalina@RICORA.prueba ", "contrasena": CONTRASENA})
        assert r.status_code == 200
        datos = r.json()
        assert datos["rol"] == "archivista" and datos["token_acceso"]
        assert datos["usuario"]["correo"] == "catalina@ricora.prueba"
        galleta = r.headers["set-cookie"]
        assert "ricora_renovacion=" in galleta and "HttpOnly" in galleta and "SameSite=strict" in galleta
        assert "Path=/api/auth" in galleta
        assert len(eventos(db, "inicio_sesion", usuario_id=u.id)) == 1

    def test_mismo_mensaje_generico_para_correo_inexistente_y_contrasena_errada(self, cliente, db):
        crear_usuario(db, "julian@ricora.prueba")
        errada = cliente.post("/api/auth/login", json={"correo": "julian@ricora.prueba", "contrasena": "otra-cosa-123"})
        inexistente = cliente.post("/api/auth/login", json={"correo": "nadie@ricora.prueba", "contrasena": CONTRASENA})
        assert errada.status_code == inexistente.status_code == 401
        assert errada.json() == inexistente.json() == {"detail": "Correo o contraseña incorrectos."}

    def test_usuario_desactivado_no_ingresa_aunque_la_contrasena_sea_correcta(self, cliente, db):
        crear_usuario(db, "laura@ricora.prueba", "consulta", activo=False)
        r = cliente.post("/api/auth/login", json={"correo": "laura@ricora.prueba", "contrasena": CONTRASENA})
        assert r.status_code == 401
        assert r.json()["detail"] == "Correo o contraseña incorrectos."

    def test_cuenta_sin_contrasena_definida_no_ingresa(self, cliente, db):
        crear_usuario(db, "invitada@ricora.prueba", contrasena=None)
        r = cliente.post("/api/auth/login", json={"correo": "invitada@ricora.prueba", "contrasena": CONTRASENA})
        assert r.status_code == 401

    def test_bloqueo_tras_intentos_fallidos(self, cliente, db):
        crear_usuario(db, "bloqueo@ricora.prueba")
        for _ in range(settings.intentos_fallidos_maximos):
            assert cliente.post("/api/auth/login", json={"correo": "bloqueo@ricora.prueba", "contrasena": "mala-clave-1"}).status_code == 401
        r = cliente.post("/api/auth/login", json={"correo": "bloqueo@ricora.prueba", "contrasena": CONTRASENA})
        assert r.status_code == 429
        assert "Espere" in r.json()["detail"]

    def test_bloqueo_tambien_para_correos_inexistentes(self, cliente, db):
        for _ in range(settings.intentos_fallidos_maximos):
            cliente.post("/api/auth/login", json={"correo": "fantasma@ricora.prueba", "contrasena": "x"})
        assert cliente.post("/api/auth/login", json={"correo": "fantasma@ricora.prueba", "contrasena": "x"}).status_code == 429

    def test_ninguna_respuesta_expone_la_contrasena_cifrada(self, cliente, db, cabeceras_admin):
        crear_usuario(db, "otro@ricora.prueba")
        for ruta in ("/api/auth/perfil", "/api/auth/usuarios"):
            cuerpo = cliente.get(ruta, headers=cabeceras_admin).text
            assert "contrasena_hash" not in cuerpo and "$2b$" not in cuerpo


# --- Token y ciclo de sesión ---------------------------------------------------------


class TestSesion:
    def test_sin_token_o_con_token_falso_responde_401(self, cliente):
        assert cliente.get("/api/auth/perfil").status_code == 401
        r = cliente.get("/api/auth/perfil", headers={"Authorization": "Bearer abc.def.ghi"})
        assert r.status_code == 401 and r.json()["detail"] == "no_autenticado"

    def test_token_expirado_pide_renovar_y_la_renovacion_funciona(self, cliente, db, monkeypatch):
        crear_usuario(db, "exp@ricora.prueba")
        monkeypatch.setattr(settings, "minutos_token_acceso", -1)
        cabeceras = ingresar(cliente, "exp@ricora.prueba")
        r = cliente.get("/api/auth/perfil", headers=cabeceras)
        assert r.status_code == 401 and r.json()["detail"] == "token_expirado"
        monkeypatch.setattr(settings, "minutos_token_acceso", 15)
        renovado = cliente.post("/api/auth/refresh")
        assert renovado.status_code == 200
        nuevo = {"Authorization": f"Bearer {renovado.json()['token_acceso']}"}
        assert cliente.get("/api/auth/perfil", headers=nuevo).status_code == 200

    def test_la_renovacion_rota_el_secreto_y_reusar_uno_viejo_cierra_la_sesion(self, cliente, db):
        u = crear_usuario(db, "rota@ricora.prueba")
        ingresar(cliente, "rota@ricora.prueba")
        vieja = cliente.cookies.get("ricora_renovacion")
        assert cliente.post("/api/auth/refresh").status_code == 200
        assert cliente.cookies.get("ricora_renovacion") != vieja
        cliente.cookies.clear()
        r = cliente.post("/api/auth/refresh", cookies={"ricora_renovacion": vieja})
        assert r.status_code == 401
        sesion = db.scalar(select(Sesion).where(Sesion.usuario_id == u.id))
        assert sesion.motivo_cierre == "reutilizacion_token"

    def test_cerrar_sesion_invalida_el_token_y_queda_en_auditoria(self, cliente, db):
        u = crear_usuario(db, "salir@ricora.prueba")
        cabeceras = ingresar(cliente, "salir@ricora.prueba")
        assert cliente.post("/api/auth/logout").status_code == 204
        assert cliente.get("/api/auth/perfil", headers=cabeceras).status_code == 401
        assert cliente.post("/api/auth/refresh").status_code == 401
        cierre = eventos(db, "cierre_sesion", usuario_id=u.id)
        assert len(cierre) == 1 and cierre[0].valor_nuevo["motivo"] == "cierre_voluntario"

    def test_expiracion_por_inactividad_cierra_con_evento_y_hora_de_ultima_actividad(self, cliente, db):
        u = crear_usuario(db, "inactiva@ricora.prueba")
        cabeceras = ingresar(cliente, "inactiva@ricora.prueba")
        sesion = db.scalar(select(Sesion).where(Sesion.usuario_id == u.id))
        ultima = ahora() - timedelta(minutes=settings.minutos_inactividad_sesion + 5)
        sesion.iniciada_en = ultima - timedelta(hours=1)
        sesion.ultima_actividad = ultima
        db.commit()
        r = cliente.get("/api/auth/perfil", headers=cabeceras)
        assert r.status_code == 401 and r.json()["detail"] == "sesion_cerrada"
        db.refresh(sesion)
        assert sesion.motivo_cierre == "expiracion"
        assert sesion.cerrada_en == ultima
        cierre = eventos(db, "cierre_sesion", usuario_id=u.id)
        assert len(cierre) == 1 and cierre[0].valor_nuevo["motivo"] == "expiracion"

    def test_sesiones_vencidas_se_cierran_solas_al_ingresar_otra_persona(self, cliente, db):
        u = crear_usuario(db, "olvidada@ricora.prueba")
        ingresar(cliente, "olvidada@ricora.prueba")
        sesion = db.scalar(select(Sesion).where(Sesion.usuario_id == u.id))
        sesion.vence_en = ahora() - timedelta(minutes=1)
        db.commit()
        crear_usuario(db, "otra@ricora.prueba")
        ingresar(cliente, "otra@ricora.prueba")
        db.refresh(sesion)
        assert sesion.motivo_cierre == "expiracion"

    def test_administrador_revoca_sesiones_antes_de_que_expire_el_token(self, cliente, db, cabeceras_admin):
        u = crear_usuario(db, "revocar@ricora.prueba")
        with TestClient(app) as otro:
            cabeceras = ingresar(otro, "revocar@ricora.prueba")
            assert otro.get("/api/auth/perfil", headers=cabeceras).status_code == 200
            r = cliente.post(f"/api/auth/usuarios/{u.id}/cerrar-sesiones", headers=cabeceras_admin)
            assert r.status_code == 200 and "1" in r.json()["mensaje"]
            assert otro.get("/api/auth/perfil", headers=cabeceras).status_code == 401


# --- Recuperación e invitación -------------------------------------------------------


class TestRecuperacion:
    def test_responde_igual_exista_o_no_el_correo(self, cliente, db, buzon):
        crear_usuario(db, "existe@ricora.prueba")
        a = cliente.post("/api/auth/recuperar", json={"correo": "existe@ricora.prueba"})
        b = cliente.post("/api/auth/recuperar", json={"correo": "noexiste@ricora.prueba"})
        assert a.status_code == b.status_code == 202
        assert a.json() == b.json()
        assert [m["para"] for m in buzon] == ["existe@ricora.prueba"]

    def test_el_enlace_funciona_una_sola_vez(self, cliente, db, buzon):
        crear_usuario(db, "unavez@ricora.prueba")
        cliente.post("/api/auth/recuperar", json={"correo": "unavez@ricora.prueba"})
        token = token_de(buzon[-1]["texto"])
        assert buzon[-1]["texto"].count("http://ricora.prueba/acceso/") == 1
        info = cliente.get(f"/api/auth/token/{token}")
        assert info.status_code == 200 and info.json()["tipo"] == "recuperacion"
        assert cliente.post(f"/api/auth/recuperar/{token}", json={"contrasena": NUEVA}).status_code == 200
        assert cliente.post(f"/api/auth/recuperar/{token}", json={"contrasena": "Otra2026clave"}).status_code == 404
        assert cliente.get(f"/api/auth/token/{token}").status_code == 404
        ingresar(cliente, "unavez@ricora.prueba", NUEVA)

    def test_el_enlace_deja_de_funcionar_al_vencer(self, cliente, db, buzon):
        u = crear_usuario(db, "vence@ricora.prueba")
        cliente.post("/api/auth/recuperar", json={"correo": "vence@ricora.prueba"})
        token = token_de(buzon[-1]["texto"])
        registro = db.scalar(select(TokenUnUso).where(TokenUnUso.usuario_id == u.id))
        assert registro.vence_en - registro.creado_en == timedelta(minutes=30)
        registro.vence_en = ahora() - timedelta(seconds=1)
        db.commit()
        assert cliente.post(f"/api/auth/recuperar/{token}", json={"contrasena": NUEVA}).status_code == 404

    def test_solo_sirve_el_ultimo_enlace_pedido(self, cliente, db, buzon):
        crear_usuario(db, "doble@ricora.prueba")
        cliente.post("/api/auth/recuperar", json={"correo": "doble@ricora.prueba"})
        cliente.post("/api/auth/recuperar", json={"correo": "doble@ricora.prueba"})
        primero, segundo = token_de(buzon[0]["texto"]), token_de(buzon[1]["texto"])
        assert cliente.get(f"/api/auth/token/{primero}").status_code == 404
        assert cliente.get(f"/api/auth/token/{segundo}").status_code == 200

    def test_restablecer_cierra_las_sesiones_abiertas(self, cliente, db, buzon):
        crear_usuario(db, "cierra@ricora.prueba")
        cabeceras = ingresar(cliente, "cierra@ricora.prueba")
        cliente.post("/api/auth/recuperar", json={"correo": "cierra@ricora.prueba"})
        cliente.post(f"/api/auth/recuperar/{token_de(buzon[-1]['texto'])}", json={"contrasena": NUEVA})
        assert cliente.get("/api/auth/perfil", headers=cabeceras).status_code == 401

    def test_la_contrasena_nueva_debe_cumplir_las_reglas(self, cliente, db, buzon):
        crear_usuario(db, "reglas@ricora.prueba")
        cliente.post("/api/auth/recuperar", json={"correo": "reglas@ricora.prueba"})
        token = token_de(buzon[-1]["texto"])
        for mala in ("corta1", "sinnumerosaqui", "1234567890123", "reglas2026xyz"):
            r = cliente.post(f"/api/auth/recuperar/{token}", json={"contrasena": mala})
            assert r.status_code == 422, mala
        assert cliente.post(f"/api/auth/recuperar/{token}", json={"contrasena": NUEVA}).status_code == 200

    def test_limite_de_solicitudes_por_hora_sin_cambiar_la_respuesta(self, cliente, db, buzon):
        crear_usuario(db, "limite@ricora.prueba")
        respuestas = {cliente.post("/api/auth/recuperar", json={"correo": "limite@ricora.prueba"}).json()["mensaje"]
                      for _ in range(settings.recuperaciones_por_hora + 2)}
        assert len(respuestas) == 1
        assert len(buzon) == settings.recuperaciones_por_hora

    def test_sin_correo_configurado_el_administrador_ve_la_solicitud(self, cliente, db, cabeceras_admin):
        crear_usuario(db, "sincorreo@ricora.prueba")
        assert cliente.post("/api/auth/recuperar", json={"correo": "sincorreo@ricora.prueba"}).status_code == 202
        lista = cliente.get("/api/auth/usuarios", headers=cabeceras_admin).json()
        assert lista["correo_configurado"] is False
        fila = next(u for u in lista["usuarios"] if u["correo"] == "sincorreo@ricora.prueba")
        assert fila["recuperacion_solicitada"] is True


class TestInvitacion:
    def test_crear_usuario_envia_invitacion_y_la_persona_define_su_contrasena(self, cliente, db, buzon, cabeceras_admin):
        r = cliente.post("/api/auth/usuarios", headers=cabeceras_admin,
                         json={"nombre": "Catalina Torres", "correo": "Catalina@Correo.com", "rol": "archivista"})
        assert r.status_code == 201
        datos = r.json()
        assert datos["entrega"]["enviado"] is True and datos["entrega"]["enlace"] is None
        assert datos["usuario"]["invitacion_pendiente"] is True
        assert buzon[-1]["para"] == "catalina@correo.com"
        token = token_de(buzon[-1]["texto"])
        info = cliente.get(f"/api/auth/token/{token}").json()
        assert info == {"tipo": "invitacion", "nombre": "Catalina Torres", "correo": "catalina@correo.com"}
        registro = db.scalar(select(TokenUnUso).where(TokenUnUso.tipo == "invitacion"))
        assert registro.vence_en - registro.creado_en == timedelta(hours=72)
        assert cliente.post(f"/api/auth/recuperar/{token}", json={"contrasena": NUEVA}).status_code == 200
        ingresar(cliente, "catalina@correo.com", NUEVA)

    def test_el_administrador_nunca_recibe_ni_define_la_contrasena(self, cliente, db, buzon, cabeceras_admin):
        r = cliente.post("/api/auth/usuarios", headers=cabeceras_admin,
                         json={"nombre": "Julián Rincón", "correo": "julian@correo.com", "rol": "revisor",
                               "contrasena": "Intento2026admin"})
        assert r.status_code == 201
        assert "contrasena" not in r.text
        u = db.scalar(select(Usuario).where(Usuario.correo == "julian@correo.com"))
        assert u.contrasena_hash is None

    def test_sin_correo_configurado_el_enlace_se_muestra_una_vez(self, cliente, db, cabeceras_admin):
        r = cliente.post("/api/auth/usuarios", headers=cabeceras_admin,
                         json={"nombre": "Laura Pinzón", "correo": "laura@correo.com", "rol": "consulta"})
        entrega = r.json()["entrega"]
        assert entrega["enviado"] is False
        assert entrega["enlace"].startswith("http://ricora.prueba/acceso/")

    def test_correo_duplicado(self, cliente, db, cabeceras_admin):
        crear_usuario(db, "repetido@correo.com")
        r = cliente.post("/api/auth/usuarios", headers=cabeceras_admin,
                         json={"nombre": "Otra Persona", "correo": "REPETIDO@correo.com", "rol": "consulta"})
        assert r.status_code == 409

    def test_reenviar_invitacion_anula_la_anterior(self, cliente, db, buzon, cabeceras_admin):
        r = cliente.post("/api/auth/usuarios", headers=cabeceras_admin,
                         json={"nombre": "Ana Gómez", "correo": "ana@correo.com", "rol": "archivista"})
        primero = token_de(buzon[-1]["texto"])
        cliente.post(f"/api/auth/usuarios/{r.json()['usuario']['id']}/enlace", headers=cabeceras_admin)
        assert cliente.get(f"/api/auth/token/{primero}").status_code == 404
        assert cliente.get(f"/api/auth/token/{token_de(buzon[-1]['texto'])}").json()["tipo"] == "invitacion"


# --- Gestión de usuarios y perfil ----------------------------------------------------


class TestGestionUsuarios:
    @pytest.mark.parametrize("rol", ["archivista", "revisor", "consulta"])
    def test_solo_el_administrador_crea_edita_o_desactiva(self, cliente, db, admin, rol):
        crear_usuario(db, f"{rol}@ricora.prueba", rol)
        cabeceras = ingresar(cliente, f"{rol}@ricora.prueba")
        assert cliente.get("/api/auth/usuarios", headers=cabeceras).status_code == 403
        assert cliente.post("/api/auth/usuarios", headers=cabeceras,
                            json={"nombre": "Nueva Persona", "correo": "n@correo.com", "rol": "consulta"}).status_code == 403
        assert cliente.patch(f"/api/auth/usuarios/{admin.id}", headers=cabeceras, json={"activo": False}).status_code == 403
        assert cliente.patch(f"/api/auth/usuarios/{admin.id}", headers=cabeceras, json={"rol": "consulta"}).status_code == 403
        db.refresh(admin)
        assert admin.activo and admin.rol == "administrador"

    def test_filtros_del_listado(self, cliente, db, cabeceras_admin):
        crear_usuario(db, "filtro.uno@correo.com", "archivista", nombre="Filtro Uno")
        crear_usuario(db, "filtro.dos@correo.com", "consulta", activo=False, nombre="Filtro Dos")
        def correos(**p):
            return {u["correo"] for u in cliente.get("/api/auth/usuarios", headers=cabeceras_admin, params=p).json()["usuarios"]}
        assert correos(q="filtro") == {"filtro.uno@correo.com", "filtro.dos@correo.com"}
        assert correos(q="filtro", rol="consulta") == {"filtro.dos@correo.com"}
        assert correos(q="filtro", activo="false") == {"filtro.dos@correo.com"}

    def test_cambio_de_rol_queda_en_auditoria_con_antes_y_despues(self, cliente, db, admin, cabeceras_admin):
        u = crear_usuario(db, "cambio@correo.com", "consulta")
        r = cliente.patch(f"/api/auth/usuarios/{u.id}", headers=cabeceras_admin, json={"rol": "archivista"})
        assert r.status_code == 200 and r.json()["rol"] == "archivista"
        evento = eventos(db, "usuario_editado", entidad_id=str(u.id))[-1]
        assert evento.usuario_id == admin.id
        assert evento.valor_anterior == {"rol": "consulta"} and evento.valor_nuevo == {"rol": "archivista"}

    def test_desactivar_cierra_sesiones_y_reactivar_permite_volver(self, cliente, db, cabeceras_admin):
        u = crear_usuario(db, "vaivien@correo.com")
        with TestClient(app) as otro:
            cabeceras = ingresar(otro, "vaivien@correo.com")
            cliente.patch(f"/api/auth/usuarios/{u.id}", headers=cabeceras_admin, json={"activo": False})
            assert otro.get("/api/auth/perfil", headers=cabeceras).status_code == 401
            assert otro.post("/api/auth/login", json={"correo": "vaivien@correo.com", "contrasena": CONTRASENA}).status_code == 401
            cliente.patch(f"/api/auth/usuarios/{u.id}", headers=cabeceras_admin, json={"activo": True})
            ingresar(otro, "vaivien@correo.com")
        assert db.get(Usuario, u.id) is not None  # nunca se borra
        assert len(eventos(db, "usuario_desactivado", entidad_id=str(u.id))) == 1
        assert len(eventos(db, "usuario_reactivado", entidad_id=str(u.id))) == 1

    def test_nadie_cambia_su_propio_rol_por_ningun_endpoint(self, cliente, db, admin, cabeceras_admin):
        # El administrador, sobre sí mismo.
        r = cliente.patch(f"/api/auth/usuarios/{admin.id}", headers=cabeceras_admin, json={"rol": "consulta"})
        assert r.status_code == 403
        # Mi perfil no admite cambios de datos, solo de contraseña.
        assert cliente.patch("/api/auth/perfil", headers=cabeceras_admin, json={"rol": "consulta"}).status_code == 405
        r = cliente.patch("/api/auth/perfil/contrasena", headers=cabeceras_admin,
                          json={"actual": CONTRASENA, "nueva": NUEVA, "rol": "consulta"})
        assert r.status_code == 200
        # Un archivista, sobre sí mismo.
        a = crear_usuario(db, "yo@correo.com", "archivista")
        cabeceras = ingresar(cliente, "yo@correo.com")
        assert cliente.patch(f"/api/auth/usuarios/{a.id}", headers=cabeceras, json={"rol": "administrador"}).status_code == 403
        db.refresh(admin)
        db.refresh(a)
        assert admin.rol == "administrador" and a.rol == "archivista"

    def test_no_puede_desactivarse_a_si_mismo(self, cliente, admin, cabeceras_admin):
        r = cliente.patch(f"/api/auth/usuarios/{admin.id}", headers=cabeceras_admin, json={"activo": False})
        assert r.status_code == 403

    def test_un_administrador_degradado_pierde_la_gestion_de_inmediato(self, cliente, db, admin, cabeceras_admin):
        otro = crear_usuario(db, "admin2@correo.com", "administrador")
        cabeceras_otro = ingresar(cliente, "admin2@correo.com")
        assert cliente.patch(f"/api/auth/usuarios/{admin.id}", headers=cabeceras_otro, json={"rol": "archivista"}).status_code == 200
        r = cliente.patch(f"/api/auth/usuarios/{otro.id}", headers=cabeceras_admin, json={"rol": "archivista"})
        assert r.status_code == 403  # admin ya no es administrador

    def test_perfil_y_cambio_de_contrasena(self, cliente, db):
        u = crear_usuario(db, "perfil@correo.com", "revisor", nombre="Julián Rincón")
        cabeceras = ingresar(cliente, "perfil@correo.com")
        with TestClient(app) as otro:
            otra_sesion = ingresar(otro, "perfil@correo.com")
            p = cliente.get("/api/auth/perfil", headers=cabeceras).json()
            assert p["nombre"] == "Julián Rincón" and p["rol_nombre"] == "Revisor" and p["iniciales"] == "JR"
            mala = cliente.patch("/api/auth/perfil/contrasena", headers=cabeceras, json={"actual": "no-es", "nueva": NUEVA})
            assert mala.status_code == 400
            igual = cliente.patch("/api/auth/perfil/contrasena", headers=cabeceras, json={"actual": CONTRASENA, "nueva": CONTRASENA})
            assert igual.status_code == 422
            ok = cliente.patch("/api/auth/perfil/contrasena", headers=cabeceras, json={"actual": CONTRASENA, "nueva": NUEVA})
            assert ok.status_code == 200
            assert cliente.get("/api/auth/perfil", headers=cabeceras).status_code == 200  # esta sesión sigue
            assert otro.get("/api/auth/perfil", headers=otra_sesion).status_code == 401  # las demás se cierran
        assert len(eventos(db, "contrasena_cambiada", usuario_id=u.id)) == 1
        ingresar(cliente, "perfil@correo.com", NUEVA)

    def test_correo_de_prueba(self, cliente, admin, cabeceras_admin, buzon):
        r = cliente.post("/api/auth/correo/prueba", headers=cabeceras_admin)
        assert r.status_code == 200 and buzon[-1]["para"] == admin.correo

    def test_correo_de_prueba_sin_configuracion(self, cliente, cabeceras_admin):
        assert cliente.post("/api/auth/correo/prueba", headers=cabeceras_admin).status_code == 409


# --- Permisos por rol en cada módulo ----------------------------------------------------


def _aplicacion_con_modulos(db):
    """Una ruta de lectura y una de escritura por módulo, protegidas con la
    misma dependencia que usará cada módulo real (acceso_modulo)."""
    prueba = FastAPI()
    for modulo in (*permisos.MODULOS_TRABAJO, "auditoria", "usuarios"):
        r = APIRouter(prefix=f"/{modulo}", dependencies=[Depends(permisos.acceso_modulo(modulo))])
        r.add_api_route("/leer", lambda: {"ok": True}, methods=["GET"])
        r.add_api_route("/escribir", lambda: {"ok": True}, methods=["POST"])
        r.add_api_route("/editar", lambda: {"ok": True}, methods=["PATCH"])
        r.add_api_route("/borrar", lambda: {"ok": True}, methods=["DELETE"])
        prueba.include_router(r)
    prueba.add_api_route("/instrumentos-catalogo", lambda: {"ok": True}, methods=["GET"],
                         dependencies=[Depends(permisos.lectura_catalogo)])
    prueba.dependency_overrides[get_db] = lambda: db
    return TestClient(prueba)


ESPERADO = {
    # módulo: {rol: (puede leer, puede escribir)}
    **{m: {"administrador": (True, True), "archivista": (True, True), "revisor": (True, False), "consulta": (False, False)}
       for m in permisos.MODULOS_TRABAJO},
    "auditoria": {"administrador": (True, False), "archivista": (True, False), "revisor": (True, False), "consulta": (False, False)},
    "usuarios": {"administrador": (True, True), "archivista": (False, False), "revisor": (False, False), "consulta": (False, False)},
}


class TestPermisosPorRol:
    @pytest.mark.parametrize("rol", ["administrador", "archivista", "revisor", "consulta"])
    def test_cada_rol_accede_solo_a_lo_que_le_corresponde(self, cliente, db, rol):
        crear_usuario(db, f"matriz.{rol}@correo.com", rol)
        cabeceras = ingresar(cliente, f"matriz.{rol}@correo.com")
        prueba = _aplicacion_con_modulos(db)
        for modulo, roles in ESPERADO.items():
            leer, escribir = roles[rol]
            assert (prueba.get(f"/{modulo}/leer", headers=cabeceras).status_code == 200) is leer, (modulo, rol, "leer")
            for metodo, ruta in (("post", "escribir"), ("patch", "editar"), ("delete", "borrar")):
                codigo = getattr(prueba, metodo)(f"/{modulo}/{ruta}", headers=cabeceras).status_code
                assert (codigo == 200) is escribir, (modulo, rol, metodo)
                if not escribir:
                    assert codigo == 403
        # El catálogo de instrumentos es la única puerta del rol consulta.
        assert prueba.get("/instrumentos-catalogo", headers=cabeceras).status_code == 200

    def test_el_revisor_no_escribe_en_ningun_modulo(self, cliente, db):
        crear_usuario(db, "revisor.solo@correo.com", "revisor")
        cabeceras = ingresar(cliente, "revisor.solo@correo.com")
        prueba = _aplicacion_con_modulos(db)
        for modulo in ESPERADO:
            for metodo, ruta in (("post", "escribir"), ("patch", "editar"), ("delete", "borrar")):
                assert getattr(prueba, metodo)(f"/{modulo}/{ruta}", headers=cabeceras).status_code == 403

    def test_sin_sesion_ningun_modulo_responde(self, db):
        prueba = _aplicacion_con_modulos(db)
        for modulo in ESPERADO:
            assert prueba.get(f"/{modulo}/leer").status_code == 401

    def test_el_rol_se_lee_de_la_base_y_no_del_token(self, cliente, db, cabeceras_admin):
        u = crear_usuario(db, "degradada@correo.com", "archivista")
        cabeceras = ingresar(cliente, "degradada@correo.com")
        prueba = _aplicacion_con_modulos(db)
        assert prueba.post("/ingesta/escribir", headers=cabeceras).status_code == 200
        cliente.patch(f"/api/auth/usuarios/{u.id}", headers=cabeceras_admin, json={"rol": "consulta"})
        assert prueba.post("/ingesta/escribir", headers=cabeceras).status_code == 403


def _dependencias(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _dependencias(d)


def test_toda_ruta_no_publica_exige_sesion():
    """Recorre todas las rutas de la aplicación real: cualquier ruta nueva
    que un módulo agregue sin la dependencia de autenticación hace fallar
    esta prueba."""
    sin_proteccion = []
    for ruta in app.routes:
        if not isinstance(ruta, APIRoute) or not ruta.path.startswith("/api"):
            continue
        if ruta.path in RUTAS_PUBLICAS:
            continue
        if permisos.usuario_actual not in set(_dependencias(ruta.dependant)):
            sin_proteccion.append(ruta.path)
    assert sin_proteccion == []


# --- Auditoría de solo anexar y cuenta administradora -----------------------------------


def test_la_auditoria_no_se_puede_modificar_ni_borrar(db, cliente):
    crear_usuario(db, "traza@correo.com")
    ingresar(cliente, "traza@correo.com")
    for sentencia in ("UPDATE registro_auditoria SET accion = 'otra'", "DELETE FROM registro_auditoria",
                      "TRUNCATE registro_auditoria"):
        with pytest.raises(DBAPIError, match="no se puede modificar ni borrar"):
            with db.begin_nested():
                db.execute(text(sentencia))


def test_cuenta_administradora_desde_el_despliegue(db, monkeypatch):
    from contextlib import contextmanager

    from app import cli

    @contextmanager
    def _misma_sesion():
        yield db

    monkeypatch.setattr(cli, "SessionLocal", _misma_sesion)
    monkeypatch.setenv("RICORA_ADMIN_CORREO", "Marlin@Correo.com")
    monkeypatch.setenv("RICORA_ADMIN_PASSWORD", "Despliegue2026ok")
    assert cli.cuenta_administradora() == 0
    u = db.scalar(select(Usuario).where(Usuario.correo == "marlin@correo.com"))
    assert u.rol == "administrador" and u.activo
    # Si la cuenta perdió el rol o quedó desactivada, el despliegue la restablece.
    u.rol, u.activo = "consulta", False
    db.commit()
    assert cli.cuenta_administradora() == 0
    db.refresh(u)
    assert u.rol == "administrador" and u.activo
    assert eventos(db, "cuenta_administradora_restablecida", entidad_id=str(u.id))[-1].valor_anterior == {
        "rol": "consulta", "activo": False}


def test_cuenta_administradora_sin_correo_usa_el_usuario_anterior(db, monkeypatch):
    from contextlib import contextmanager

    from app import cli

    @contextmanager
    def _misma_sesion():
        yield db

    monkeypatch.setattr(cli, "SessionLocal", _misma_sesion)
    monkeypatch.delenv("RICORA_ADMIN_CORREO", raising=False)
    monkeypatch.setenv("RICORA_ADMIN_USER", "Marlin")
    monkeypatch.setenv("RICORA_ADMIN_PASSWORD", "corta")  # débil: se aplica con aviso
    assert cli.cuenta_administradora() == 0
    u = db.scalar(select(Usuario).where(Usuario.correo == "marlin@ricora.local"))
    assert u is not None and u.rol == "administrador"
