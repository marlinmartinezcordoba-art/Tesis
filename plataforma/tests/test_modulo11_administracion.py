"""M11 · Administración y seguridad (/admin/usuarios).

RF-M11-01: crear, editar y desactivar usuarios con exactamente uno de los
cuatro roles; invitación con un enlace de un solo uso.
RF-M11-02: ningún proveedor de IA se guarda sin una prueba de conexión
exitosa de esos mismos datos.
RF-M11-03: toda acción restringida según el rol; ninguna ruta abierta sin sesión."""

import re
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core import mail
from django.test import RequestFactory, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from ric import invitaciones, roles
from ric.models import ConfiguracionSistema, ProveedorIAConfig, RegistroAuditoria, SolicitudRestablecimiento

from ._ayudas import CasoModulos

CORRECTA = "Clave-Robusta-2026"


def _nuevo(**cambios):
    datos = {"nombre_completo": "Zully Rojas", "email": "zully@entidad.gov.co", "username": "zully", "rol": roles.REVISOR}
    datos.update(cambios)
    return datos


def _enlace(usuario):
    return invitaciones.enlace(RequestFactory().get("/"), usuario)


class UsuariosTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.superusuario)

    def test_solo_el_administrador_administra(self):
        for cuenta in (self.archivista, self.revisor, self.consulta):
            self.client.force_login(cuenta)
            resp = self.client.get(reverse("admin_usuarios"), follow=True)
            self.assertContains(resp, "Esta acción requiere el rol administrador")
            self.client.post(reverse("admin_usuarios"), _nuevo(username=f"intruso_{cuenta.pk}"))
        self.assertFalse(User.objects.filter(username__startswith="intruso_").exists())

    def test_crear_con_cada_uno_de_los_cuatro_roles(self):
        for rol in roles.ROLES_ASIGNABLES:
            resp = self.client.post(reverse("admin_usuarios"), _nuevo(username=f"u_{rol}", email=f"{rol}@entidad.gov.co", rol=rol), follow=True)
            self.assertContains(resp, "Cuenta creada")
        for rol in roles.ROLES_ASIGNABLES:
            u = User.objects.get(username=f"u_{rol}")
            self.assertEqual(roles.rol_de(u), rol)
            # exactamente un rol: las marcas no se contradicen
            self.assertEqual(u.is_superuser, rol == roles.ADMINISTRADOR)
            self.assertEqual(u.groups.filter(name="revisor").exists(), rol == roles.REVISOR)
            self.assertFalse(u.has_usable_password())  # la contraseña la crea la persona

    def test_sin_correo_en_el_servidor_entrega_el_enlace_una_vez(self):
        with override_settings(EMAIL_HOST=""):
            resp = self.client.post(reverse("admin_usuarios"), _nuevo(), follow=True)
        self.assertContains(resp, "copie el enlace de invitación")
        self.assertContains(resp, 'id="enlace-invitacion"')
        self.assertContains(resp, "/ric/invitacion/")
        resp = self.client.get(reverse("admin_usuarios"))
        self.assertNotContains(resp, 'id="enlace-invitacion"')  # no se vuelve a mostrar

    @override_settings(EMAIL_HOST="smtp.entidad.gov.co", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_invitacion_por_correo_sin_contrasena(self):
        resp = self.client.post(reverse("admin_usuarios"), _nuevo(), follow=True)
        self.assertContains(resp, "Invitación enviada a zully@entidad.gov.co")
        self.assertEqual(len(mail.outbox), 1)
        cuerpo = mail.outbox[0].body
        self.assertIn("/ric/invitacion/", cuerpo)
        self.assertNotIn("Contraseña inicial", cuerpo)
        self.assertNotContains(resp, 'id="enlace-invitacion"')

    def test_el_enlace_crea_la_contrasena_y_luego_deja_de_servir(self):
        self.client.post(reverse("admin_usuarios"), _nuevo())
        zully = User.objects.get(username="zully")
        url = _enlace(zully)
        self.client.logout()
        self.assertContains(self.client.get(url), "Cree su contraseña")
        resp = self.client.post(url, {"password": CORRECTA, "password_confirmar": "otra"})
        self.assertContains(resp, "no coinciden")
        resp = self.client.post(url, {"password": "123", "password_confirmar": "123"})
        self.assertContains(resp, "demasiado corta", status_code=200)
        resp = self.client.post(url, {"password": CORRECTA, "password_confirmar": CORRECTA}, follow=True)
        self.assertContains(resp, "Su contraseña quedó creada")
        self.assertIsNotNone(authenticate(username="zully", password=CORRECTA))
        # un solo uso
        self.assertContains(self.client.get(url), "Este enlace ya no sirve", status_code=400)
        self.assertTrue(RegistroAuditoria.objects.filter(detalle__invitacion="contraseña creada por la persona").exists())

    def test_enlace_alterado_o_de_cuenta_inactiva(self):
        self.client.post(reverse("admin_usuarios"), _nuevo())
        zully = User.objects.get(username="zully")
        url = _enlace(zully)
        self.assertEqual(self.client.get(url[:-3] + "xyz/").status_code, 400)
        zully.is_active = False
        zully.save()
        self.assertEqual(self.client.get(url).status_code, 400)

    def test_validaciones_al_crear(self):
        casos = [
            (_nuevo(username="archivista"), "Ya existe una cuenta con el nombre de usuario"),
            (_nuevo(username="con espacios"), "sin espacios"),
            (_nuevo(email="no-es-correo"), "formato válido"),
            (_nuevo(nombre_completo=""), "Escriba el nombre"),
            (_nuevo(email=""), "Escriba el correo"),
            (_nuevo(rol="jefe"), "Elija uno de los cuatro roles"),
        ]
        for datos, error in casos:
            resp = self.client.post(reverse("admin_usuarios"), datos)
            self.assertContains(resp, error)
            self.assertContains(resp, 'nu.showModal()')  # la ventana se reabre con lo escrito
        User.objects.filter(username="archivista").update(email="zully@entidad.gov.co")
        self.assertContains(self.client.post(reverse("admin_usuarios"), _nuevo(username="otra")), "ya pertenece a otra cuenta")
        self.assertFalse(User.objects.filter(username__in=["zully", "otra"]).exists())

    def test_editar_nombre_correo_y_rol_queda_auditado(self):
        url = reverse("admin_usuario_editar", args=[self.consulta.pk])
        resp = self.client.post(url, {"accion": "editar", "nombre_completo": "Ana Pérez", "email": "ana@entidad.gov.co", "rol": roles.ARCHIVISTA}, follow=True)
        self.assertContains(resp, "actualizada: archivista")
        self.consulta.refresh_from_db()
        self.assertEqual((self.consulta.first_name, self.consulta.email), ("Ana Pérez", "ana@entidad.gov.co"))
        self.assertEqual(roles.rol_de(self.consulta), roles.ARCHIVISTA)
        cambios = RegistroAuditoria.objects.filter(accion="modificar", object_id=str(self.consulta.pk))
        self.assertTrue(any(r.despues.get("rol") == roles.ARCHIVISTA for r in cambios))
        self.assertTrue(any(r.despues.get("email") == "ana@entidad.gov.co" for r in cambios))

    def test_siempre_queda_un_administrador(self):
        url = reverse("admin_usuario_editar", args=[self.superusuario.pk])
        resp = self.client.post(url, {"accion": "editar", "nombre_completo": "Marlín", "email": "m@e.co", "rol": roles.CONSULTA}, follow=True)
        self.assertContains(resp, "único administrador activo")
        self.superusuario.refresh_from_db()
        self.assertTrue(self.superusuario.is_superuser)
        roles.asignar_rol(self.revisor, roles.ADMINISTRADOR)
        self.client.post(url, {"accion": "editar", "nombre_completo": "Marlín", "email": "m@e.co", "rol": roles.CONSULTA})
        self.superusuario.refresh_from_db()
        self.assertFalse(self.superusuario.is_superuser)

    def test_desactivar_reactivar_y_no_a_si_mismo(self):
        url = reverse("admin_usuario_editar", args=[self.revisor.pk])
        self.client.post(url, {"accion": "desactivar"})
        self.revisor.refresh_from_db()
        self.assertFalse(self.revisor.is_active)
        self.assertIsNone(authenticate(username="revisor", password="x"))
        self.client.post(url, {"accion": "reactivar"})
        self.revisor.refresh_from_db()
        self.assertTrue(self.revisor.is_active)
        resp = self.client.post(reverse("admin_usuario_editar", args=[self.superusuario.pk]), {"accion": "desactivar"}, follow=True)
        self.assertContains(resp, "No puede desactivar su propia cuenta")

    def test_restablecer_acceso_invalida_la_contrasena_y_da_un_enlace(self):
        otro = self.client_class()
        otro.post(reverse("ric_login"), {"username": "archivista", "password": "x"})
        with override_settings(EMAIL_HOST=""):
            resp = self.client.post(reverse("admin_usuario_editar", args=[self.archivista.pk]), {"accion": "restablecer"}, follow=True)
        self.assertContains(resp, "su contraseña anterior dejó de servir")
        self.assertContains(resp, 'id="enlace-invitacion"')
        self.archivista.refresh_from_db()
        self.assertFalse(self.archivista.has_usable_password())
        self.assertEqual(otro.get(reverse("inicio")).status_code, 302)  # su sesión se cerró

    def test_tabla_de_usuarios(self):
        self.client.post(reverse("admin_usuarios"), _nuevo())
        resp = self.client.get(reverse("admin_usuarios"))
        for texto in ('id="filtro-texto"', 'id="filtro-rol"', "Solo activos", "Invitación pendiente", "Nunca", "(usted)",
                      'class="rol-badge rol-administrador"', 'data-abrir="nuevo-usuario"', f'id="editar-{self.revisor.pk}"'):
            self.assertContains(resp, texto)
        for rol in ("Archivista", "Revisor", "Consulta", "Administrador"):
            self.assertContains(resp, f"<b>{rol}</b>")


class OlvidoContrasenaTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.revisor.email = "revisor@entidad.gov.co"
        self.revisor.first_name = "Rosa Revisora"
        self.revisor.save()

    def test_el_ingreso_ofrece_restablecer(self):
        resp = self.client.get(reverse("ric_login"))
        self.assertContains(resp, "¿Olvidó su contraseña?")
        self.assertContains(resp, reverse("olvido_contrasena"))

    def test_misma_respuesta_exista_o_no_la_cuenta(self):
        existe = self.client.post(reverse("olvido_contrasena"), {"identidad": "revisor"})
        no_existe = self.client.post(reverse("olvido_contrasena"), {"identidad": "nadie"})
        self.assertContains(existe, "Solicitud recibida")
        limpiar = lambda r: re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", r.content.decode())
        self.assertEqual(limpiar(existe), limpiar(no_existe))
        self.assertTrue(RegistroAuditoria.objects.filter(accion="solicitar_restablecimiento", exitoso=False, detalle__identidad="nadie").exists())

    @override_settings(EMAIL_HOST="")
    def test_sin_correo_la_solicitud_llega_al_administrador(self):
        self.client.post(reverse("olvido_contrasena"), {"identidad": "REVISOR@entidad.gov.co"})
        self.client.post(reverse("olvido_contrasena"), {"identidad": "revisor"})  # no duplica
        self.assertEqual(SolicitudRestablecimiento.objects.filter(usuario=self.revisor, atendida=False).count(), 1)
        self.assertIsNotNone(authenticate(username="revisor", password="x"))  # su contraseña sigue sirviendo
        self.client.force_login(self.superusuario)
        self.assertContains(self.client.get(reverse("inicio")), "Pidió restablecer su contraseña")
        resp = self.client.get(reverse("admin_usuarios"))
        self.assertContains(resp, "1 persona(s) pidieron restablecer su contraseña")
        self.assertContains(resp, "Pidió restablecer")
        resp = self.client.post(reverse("admin_usuario_editar", args=[self.revisor.pk]), {"accion": "restablecer"}, follow=True)
        self.assertContains(resp, 'id="enlace-invitacion"')
        solicitud = SolicitudRestablecimiento.objects.get(usuario=self.revisor)
        self.assertTrue(solicitud.atendida)
        self.assertEqual((solicitud.via, solicitud.atendida_por), ("administrador", self.superusuario))
        self.assertNotContains(self.client.get(reverse("admin_usuarios")), "pidieron restablecer")

    @override_settings(EMAIL_HOST="smtp.entidad.gov.co", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_con_correo_llega_el_enlace_y_crea_la_nueva_contrasena(self):
        resp = self.client.post(reverse("olvido_contrasena"), {"identidad": "revisor"})
        self.assertContains(resp, "le llegará un correo")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Restablecer su contraseña de RICORA")
        url = re.search(r"http://\S+/ric/invitacion/\S+/", mail.outbox[0].body).group(0)
        self.assertTrue(SolicitudRestablecimiento.objects.get(usuario=self.revisor).atendida)
        self.assertIsNotNone(authenticate(username="revisor", password="x"))  # hasta que cree la nueva
        self.client.post(url, {"password": CORRECTA, "password_confirmar": CORRECTA})
        self.assertIsNone(authenticate(username="revisor", password="x"))
        self.assertIsNotNone(authenticate(username="revisor", password=CORRECTA))
        self.assertContains(self.client.get(url), "Este enlace ya no sirve", status_code=400)

    @override_settings(EMAIL_HOST="")
    def test_cuenta_inactiva_no_genera_solicitud(self):
        self.revisor.is_active = False
        self.revisor.save()
        self.assertContains(self.client.post(reverse("olvido_contrasena"), {"identidad": "revisor"}), "Solicitud recibida")
        self.assertFalse(SolicitudRestablecimiento.objects.exists())

    @override_settings(EMAIL_HOST="smtp.entidad.gov.co", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_limite_de_solicitudes_por_hora(self):
        for _ in range(8):
            self.client.post(reverse("olvido_contrasena"), {"identidad": "revisor"}, REMOTE_ADDR="10.0.0.9")
        self.assertEqual(len(mail.outbox), 5)
        self.assertTrue(RegistroAuditoria.objects.filter(detalle__motivo="límite por hora").exists())


class ProveedoresIATest(CasoModulos):
    DATOS = {"proveedor": "gemini", "modelo": "gemini-3.5-flash", "clave_api": "AIza-secreta-1234"}

    def setUp(self):
        super().setUp()
        self.client.force_login(self.superusuario)

    def _probar(self, exitosa=True, **datos):
        with patch("ric.proveedores.probar_conexion", return_value=(exitosa, "Conexión correcta" if exitosa else "La clave no es válida.")):
            return self.client.post(reverse("admin_proveedor_probar_nuevo"), {**self.DATOS, **datos}).json()

    def test_no_se_guarda_sin_prueba(self):
        resp = self.client.post(reverse("admin_proveedor_agregar"), {**self.DATOS, "activar": "1"}, follow=True)
        self.assertContains(resp, "Pruebe la conexión con éxito antes de guardar")
        self.assertFalse(ProveedorIAConfig.objects.exists())

    def test_probar_y_guardar_como_fuente(self):
        prueba = self._probar()
        self.assertTrue(prueba["ok"])
        self.assertTrue(prueba["comprobante"])
        resp = self.client.post(reverse("admin_proveedor_agregar"), {**self.DATOS, "comprobante": prueba["comprobante"], "activar": "1"}, follow=True)
        self.assertContains(resp, "guardado y activado como fuente")
        config = ProveedorIAConfig.objects.get()
        self.assertTrue(config.activo and config.prueba_exitosa)
        self.assertContains(resp, "•••• 1234")
        self.assertNotContains(resp, "AIza-secreta-1234")

    def test_prueba_fallida_no_da_comprobante(self):
        prueba = self._probar(exitosa=False)
        self.assertFalse(prueba["ok"])
        self.assertEqual(prueba["comprobante"], "")
        self.assertTrue(RegistroAuditoria.objects.filter(exitoso=False, detalle__prueba_proveedor="gemini").exists())

    def test_si_cambian_los_datos_hay_que_probar_de_nuevo(self):
        prueba = self._probar()
        resp = self.client.post(reverse("admin_proveedor_agregar"), {**self.DATOS, "clave_api": "otra-clave", "comprobante": prueba["comprobante"]}, follow=True)
        self.assertContains(resp, "Los datos cambiaron después de la prueba")
        self.assertFalse(ProveedorIAConfig.objects.exists())

    def test_comprobante_vencido(self):
        prueba = self._probar()
        with patch("ric.vistas_admin._VIGENCIA_PRUEBA", -1):
            resp = self.client.post(reverse("admin_proveedor_agregar"), {**self.DATOS, "comprobante": prueba["comprobante"]}, follow=True)
        self.assertContains(resp, "La prueba de conexión venció")
        self.assertFalse(ProveedorIAConfig.objects.exists())

    def test_probar_requiere_sesion_de_administrador(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("admin_proveedor_probar_nuevo"), self.DATOS).status_code, 401)
        self.client.force_login(self.archivista)
        self.assertEqual(self.client.post(reverse("admin_proveedor_probar_nuevo"), self.DATOS).status_code, 403)

    def test_volver_a_probar_uno_guardado(self):
        config = ProveedorIAConfig.objects.create(proveedor="claude", clave_api="mala", prueba_exitosa=True)
        with patch("ric.proveedores.probar_conexion", return_value=(False, "La clave de API de Anthropic no es válida.")):
            resp = self.client.post(reverse("admin_proveedor_probar", args=[config.pk]), follow=True)
        self.assertContains(resp, "no es válida")
        config.refresh_from_db()
        self.assertIs(config.prueba_exitosa, False)
        resp = self.client.post(reverse("admin_proveedor_activar", args=[config.pk]), follow=True)
        self.assertContains(resp, "Pruebe la conexión con éxito antes")

    def test_solo_un_proveedor_activo_a_la_vez(self):
        a = ProveedorIAConfig.objects.create(proveedor="gemini", prueba_exitosa=True, activo=True)
        b = ProveedorIAConfig.objects.create(proveedor="claude", prueba_exitosa=True)
        self.client.post(reverse("admin_proveedor_activar", args=[b.pk]))
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertFalse(a.activo)
        self.assertTrue(b.activo)

    def test_el_proveedor_activo_alimenta_el_motor(self):
        from ric import proveedores

        self.assertIsNone(proveedores.proveedor_activo())
        ProveedorIAConfig.objects.create(proveedor="gemini", modelo="gemini-3.5-flash", clave_api="k", prueba_exitosa=True, activo=True)
        self.assertEqual(proveedores.proveedor_activo().modelo, "gemini-3.5-flash")

    def test_retirar_es_borrado_logico(self):
        config = ProveedorIAConfig.objects.create(proveedor="local-spacy")
        self.client.post(reverse("admin_proveedor_eliminar", args=[config.pk]))
        self.assertFalse(ProveedorIAConfig.objects.exists())
        self.assertTrue(ProveedorIAConfig.todos.filter(pk=config.pk, eliminado=True).exists())


class ParametrosTest(CasoModulos):
    def test_guardar_parametros_con_validacion(self):
        self.client.force_login(self.superusuario)
        validos = {"dias_limite_revision": "15", "umbral_calidad_ocr": "70", "umbral_confianza_revision": "0.6", "umbral_similitud_vocabulario": "0.85"}
        self.assertContains(self.client.post(reverse("admin_parametros"), validos, follow=True), "Parámetros guardados")
        config = ConfiguracionSistema.actual()
        self.assertEqual((config.dias_limite_revision, config.umbral_confianza_revision), (15, 0.6))
        resp = self.client.post(reverse("admin_parametros"), {**validos, "dias_limite_revision": "0"}, follow=True)
        self.assertContains(resp, "Rangos")
        self.assertEqual(ConfiguracionSistema.actual().dias_limite_revision, 15)


# --- RF-M11-03: toda acción restringida según el rol ------------------------

# Rutas públicas a propósito: el ingreso, «¿Olvidó su contraseña?», la
# invitación (el enlace es la credencial), la salida, el administrador técnico de Django (tiene su propio
# ingreso) y los archivos de desarrollo (solo existen con DEBUG, nunca en el servidor).
PUBLICAS = {"ric_login", "invitacion", "ric_logout", "olvido_contrasena"}


def _rutas(patrones=None, prefijo=""):
    for p in patrones if patrones is not None else get_resolver().url_patterns:
        if isinstance(p, URLResolver):
            if str(p.pattern).startswith("admin/") and not str(p.pattern).startswith("admin/usuarios"):
                continue
            yield from _rutas(p.url_patterns, prefijo + str(p.pattern))
        elif isinstance(p, URLPattern) and p.name and p.name not in PUBLICAS:
            yield p.name, prefijo + str(p.pattern)


def _url(patron):
    url = re.sub(r"<int:\w+>", "1", patron)
    url = re.sub(r"<(str:)?\w+>", "record", url)
    return "/" + url.lstrip("^").rstrip("$")


class PermisosPorRolTest(CasoModulos):
    def test_ninguna_ruta_responde_sin_sesion(self):
        rutas = list(_rutas())
        self.assertGreater(len(rutas), 60)
        abiertas = []
        for nombre, patron in rutas:
            for metodo in (self.client.get, self.client.post):
                resp = metodo(_url(patron))
                if resp.status_code == 200 or (resp.status_code == 302 and "entrar" not in resp["Location"] and "login" not in resp["Location"]):
                    abiertas.append((nombre, metodo.__name__, resp.status_code))
        self.assertEqual(abiertas, [], "Rutas que responden sin sesión")

    def test_administracion_solo_para_el_administrador(self):
        rutas = [(n, p) for n, p in _rutas() if n.startswith("admin_")]
        self.assertGreaterEqual(len(rutas), 10)
        for cuenta in (self.archivista, self.revisor, self.consulta):
            self.client.force_login(cuenta)
            for nombre, patron in rutas:
                for metodo in (self.client.get, self.client.post):
                    resp = metodo(_url(patron))
                    self.assertIn(resp.status_code, (302, 403, 405), f"{cuenta.username} {metodo.__name__} {nombre}")
                    if resp.status_code == 302:
                        self.assertNotIn("admin/usuarios", resp["Location"])
        denegados = RegistroAuditoria.objects.filter(accion="acceso_denegado")
        self.assertTrue(denegados.filter(usuario_nombre="consulta").exists())

    def test_cada_rol_llega_solo_a_lo_suyo(self):
        matriz = {
            "ingesta": {roles.ARCHIVISTA},
            "analisis_lista": {roles.ARCHIVISTA, roles.REVISOR},
            "revision_lista": {roles.ARCHIVISTA, roles.REVISOR},
            "catalogo": {roles.ARCHIVISTA, roles.REVISOR, roles.CONSULTA},
            "panel": {roles.ARCHIVISTA, roles.REVISOR, roles.CONSULTA},
            "admin_usuarios": set(),
        }
        for cuenta in (self.archivista, self.revisor, self.consulta, self.superusuario):
            self.client.force_login(cuenta)
            rol = roles.rol_de(cuenta)
            for nombre, permitidos in matriz.items():
                codigo = self.client.get(reverse(nombre)).status_code
                esperado = 200 if (rol == roles.ADMINISTRADOR or rol in permitidos) else 302
                self.assertEqual(codigo, esperado, f"{rol} → {nombre}")
