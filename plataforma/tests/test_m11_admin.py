"""M11 · Administración y seguridad (/admin/usuarios): RF-M11-01 a RF-M11-03
y el flujo "Dar de alta un usuario y activar un proveedor de IA"."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse

from ric import roles
from ric.models import ConfiguracionSistema, ProveedorIAConfig

from ._ayudas import CasoModulos


class UsuariosTest(CasoModulos):
    def test_solo_el_superusuario_administra(self):
        for usuario in (self.archivista, self.revisor, self.consulta):
            self.client.force_login(usuario)
            resp = self.client.get(reverse("admin_usuarios"), follow=True)
            self.assertContains(resp, "Esta acción requiere")
        self.assertEqual(self.client.get(reverse("admin_usuarios")).status_code, 302)

    def test_roles_de_cada_cuenta(self):
        self.assertEqual(roles.rol_de(self.superusuario), roles.SUPERUSUARIO)
        self.assertEqual(roles.rol_de(self.archivista), roles.ARCHIVISTA)
        self.assertEqual(roles.rol_de(self.revisor), roles.REVISOR)
        self.assertEqual(roles.rol_de(self.consulta), roles.CONSULTA)

    def _crear(self, **datos):
        base = {"username": "zully", "nombre_completo": "Zully", "email": "zully@ejemplo.org",
                "password": "ContraseñaSegura987", "password_confirmar": "ContraseñaSegura987", "rol": "revisor"}
        base.update(datos)
        return self.client.post(reverse("admin_usuarios"), base, follow=True)

    def test_crear_usuario_revisor_sin_correo_configurado_lo_dice(self):
        self.client.force_login(self.superusuario)
        resp = self._crear()
        self.assertContains(resp, "Cuenta creada")
        self.assertContains(resp, "Correo no configurado")
        zully = User.objects.get(username="zully")
        self.assertEqual(roles.rol_de(zully), roles.REVISOR)
        self.assertFalse(zully.is_staff)
        self.assertEqual(zully.email, "zully@ejemplo.org")
        self.assertTrue(zully.check_password("ContraseñaSegura987"))

    def test_crear_archivista_y_consulta(self):
        self.client.force_login(self.superusuario)
        self._crear(username="catalina", rol="archivista")
        self._crear(username="invitado", rol="consulta")
        self.assertTrue(User.objects.get(username="catalina").is_staff)
        self.assertEqual(roles.rol_de(User.objects.get(username="invitado")), roles.CONSULTA)

    def test_validaciones_al_crear(self):
        self.client.force_login(self.superusuario)
        self.assertContains(self._crear(username="archivista"), "Ya existe una cuenta")
        self.assertContains(self._crear(password_confirmar="otra"), "no coinciden")
        self.assertEqual(self._crear(password="12345", password_confirmar="12345").status_code, 200)
        self.assertContains(self._crear(rol="dios"), "Elija un rol válido")
        self.assertFalse(User.objects.filter(username="zully").exists())

    def test_cambiar_rol_desactivar_y_reactivar(self):
        self.client.force_login(self.superusuario)
        url = reverse("admin_usuario_editar", args=[self.consulta.pk])
        self.client.post(url, {"accion": "cambiar_rol", "rol": "revisor"})
        self.assertEqual(roles.rol_de(User.objects.get(pk=self.consulta.pk)), roles.REVISOR)
        self.client.post(url, {"accion": "desactivar"})
        self.assertFalse(User.objects.get(pk=self.consulta.pk).is_active)
        self.client.logout()
        resp = self.client.post(reverse("ric_login"), {"username": "consulta", "password": "x"})
        self.assertEqual(resp.status_code, 200)  # no entra
        self.client.force_login(self.superusuario)
        self.client.post(url, {"accion": "reactivar"})
        self.assertTrue(User.objects.get(pk=self.consulta.pk).is_active)

    def test_restablecer_contrasena(self):
        self.client.force_login(self.superusuario)
        self.client.post(reverse("admin_usuario_editar", args=[self.consulta.pk]), {"accion": "restablecer", "password": "NuevaClaveLarga2026", "password_confirmar": "NuevaClaveLarga2026"})
        self.assertTrue(User.objects.get(pk=self.consulta.pk).check_password("NuevaClaveLarga2026"))

    def test_no_se_puede_desactivar_al_superusuario(self):
        self.client.force_login(self.superusuario)
        resp = self.client.post(reverse("admin_usuario_editar", args=[self.superusuario.pk]), {"accion": "desactivar"}, follow=True)
        self.assertContains(resp, "no se puede degradar ni desactivar")
        self.assertTrue(User.objects.get(pk=self.superusuario.pk).is_active)

    def test_tabla_de_usuarios_con_su_rol(self):
        self.client.force_login(self.superusuario)
        resp = self.client.get(reverse("admin_usuarios"))
        for etiqueta in ("Administrador", "Archivista", "Revisor", "Consulta"):
            self.assertContains(resp, etiqueta)


class ProveedoresIATest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.superusuario)

    def test_agregar_probar_y_activar(self):
        resp = self.client.post(reverse("admin_proveedor_agregar"), {"proveedor": "gemini", "modelo": "gemini-2.5-pro", "clave_api": "AIza-secreta-1234"}, follow=True)
        self.assertContains(resp, "Pruebe la conexión antes de activarlo")
        config = ProveedorIAConfig.objects.get()
        self.assertFalse(config.activo)
        self.assertContains(resp, "•••• 1234")
        self.assertNotContains(resp, "AIza-secreta-1234")
        # activar sin probar: bloqueado
        resp = self.client.post(reverse("admin_proveedor_activar", args=[config.pk]), follow=True)
        self.assertContains(resp, "Pruebe la conexión con éxito antes")
        with patch("ric.proveedores.probar_conexion", return_value=(True, "Conexión correcta con Gemini")):
            resp = self.client.post(reverse("admin_proveedor_probar", args=[config.pk]), follow=True)
        self.assertContains(resp, "Conexión correcta con Gemini")
        config.refresh_from_db()
        self.assertTrue(config.prueba_exitosa)
        resp = self.client.post(reverse("admin_proveedor_activar", args=[config.pk]), follow=True)
        self.assertContains(resp, "activado como fuente del motor")
        config.refresh_from_db()
        self.assertTrue(config.activo)

    def test_prueba_fallida_queda_registrada(self):
        config = ProveedorIAConfig.objects.create(proveedor="claude", clave_api="mala")
        with patch("ric.proveedores.probar_conexion", return_value=(False, "La clave de API de Anthropic no es válida.")):
            resp = self.client.post(reverse("admin_proveedor_probar", args=[config.pk]), follow=True)
        self.assertContains(resp, "no es válida")
        config.refresh_from_db()
        self.assertIs(config.prueba_exitosa, False)

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
        ProveedorIAConfig.objects.create(proveedor="gemini", modelo="gemini-2.5-flash", clave_api="k", prueba_exitosa=True, activo=True)
        proveedor = proveedores.proveedor_activo()
        self.assertEqual(proveedor.nombre, "gemini")
        self.assertEqual(proveedor.modelo, "gemini-2.5-flash")

    def test_eliminar(self):
        config = ProveedorIAConfig.objects.create(proveedor="local-spacy")
        self.client.post(reverse("admin_proveedor_eliminar", args=[config.pk]))
        self.assertFalse(ProveedorIAConfig.objects.exists())


class ParametrosTest(CasoModulos):
    def test_guardar_parametros_con_validacion(self):
        self.client.force_login(self.superusuario)
        resp = self.client.post(reverse("admin_parametros"), {"dias_limite_revision": "15", "umbral_calidad_ocr": "70", "umbral_confianza_revision": "0.6", "umbral_similitud_vocabulario": "0.85"}, follow=True)
        self.assertContains(resp, "Parámetros guardados")
        config = ConfiguracionSistema.actual()
        self.assertEqual(config.dias_limite_revision, 15)
        self.assertEqual(config.umbral_confianza_revision, 0.6)
        resp = self.client.post(reverse("admin_parametros"), {"dias_limite_revision": "0", "umbral_calidad_ocr": "70", "umbral_confianza_revision": "0.6", "umbral_similitud_vocabulario": "0.85"}, follow=True)
        self.assertContains(resp, "Rangos")
        self.assertEqual(ConfiguracionSistema.actual().dias_limite_revision, 15)
