"""F16 (Seguridad): crear cuentas de acceso desde la propia plataforma,
sin pasar por el panel técnico de Django — la usuaria lo pidió
explícitamente para darle acceso a sus compañeras de tesis (Zully,
Catalina)."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class CrearUsuarioTest(TestCase):
    def setUp(self):
        self.superusuario = User.objects.create_superuser("marlin", password="claveSegura123")
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.consulta = User.objects.create_user("consulta", password="x", is_staff=False)

    def test_requiere_login(self):
        resp = self.client.get(reverse("ric_usuarios"))
        self.assertEqual(resp.status_code, 302)

    def test_un_archivista_normal_no_puede_entrar(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_usuarios"), follow=True)
        self.assertContains(resp, "Solo una cuenta superusuario")

    def test_un_invitado_de_consulta_no_puede_entrar(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("ric_usuarios"), follow=True)
        self.assertContains(resp, "Solo una cuenta superusuario")

    def test_el_superusuario_crea_una_cuenta_archivista(self):
        self.client.force_login(self.superusuario)
        resp = self.client.post(reverse("ric_usuarios"), {
            "username": "zully", "nombre_completo": "Zully",
            "password": "ContraseñaSegura987", "password_confirmar": "ContraseñaSegura987",
            "rol": "archivista",
        }, follow=True)
        self.assertContains(resp, "Cuenta creada")
        zully = User.objects.get(username="zully")
        self.assertTrue(zully.is_staff)
        self.assertFalse(zully.is_superuser)
        self.assertEqual(zully.first_name, "Zully")
        self.assertTrue(zully.check_password("ContraseñaSegura987"))

    def test_el_superusuario_crea_una_cuenta_de_consulta(self):
        self.client.force_login(self.superusuario)
        resp = self.client.post(reverse("ric_usuarios"), {
            "username": "catalina", "nombre_completo": "Catalina",
            "password": "OtraContraseñaSegura456", "password_confirmar": "OtraContraseñaSegura456",
            "rol": "consulta",
        }, follow=True)
        self.assertContains(resp, "Cuenta creada")
        catalina = User.objects.get(username="catalina")
        self.assertFalse(catalina.is_staff)

    def test_la_nueva_cuenta_puede_iniciar_sesion_de_verdad(self):
        self.client.force_login(self.superusuario)
        self.client.post(reverse("ric_usuarios"), {
            "username": "zully", "password": "ContraseñaSegura987",
            "password_confirmar": "ContraseñaSegura987", "rol": "archivista",
        })
        self.client.logout()
        resp = self.client.post(reverse("ric_login"), {"username": "zully", "password": "ContraseñaSegura987"})
        self.assertRedirects(resp, reverse("ric_inicio"))

    def test_nombre_de_usuario_repetido_da_error_claro(self):
        self.client.force_login(self.superusuario)
        resp = self.client.post(reverse("ric_usuarios"), {
            "username": "archivista", "password": "ContraseñaSegura987",
            "password_confirmar": "ContraseñaSegura987", "rol": "archivista",
        })
        self.assertContains(resp, "Ya existe una cuenta")
        self.assertEqual(User.objects.filter(username="archivista").count(), 1)

    def test_contrasenas_que_no_coinciden_dan_error(self):
        self.client.force_login(self.superusuario)
        resp = self.client.post(reverse("ric_usuarios"), {
            "username": "zully", "password": "ContraseñaSegura987",
            "password_confirmar": "OtraDistinta999", "rol": "archivista",
        })
        self.assertContains(resp, "no coinciden")
        self.assertFalse(User.objects.filter(username="zully").exists())

    def test_contrasena_debil_se_rechaza(self):
        self.client.force_login(self.superusuario)
        resp = self.client.post(reverse("ric_usuarios"), {
            "username": "zully", "password": "12345", "password_confirmar": "12345",
            "rol": "archivista",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="zully").exists())

    def test_lista_las_cuentas_existentes_con_su_perfil(self):
        self.client.force_login(self.superusuario)
        resp = self.client.get(reverse("ric_usuarios"))
        self.assertContains(resp, "archivista")
        self.assertContains(resp, "consulta")
        self.assertContains(resp, "Superusuario")
