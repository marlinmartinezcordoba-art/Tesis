"""Estado de los 20 módulos (F01-F20) dentro de la propia plataforma — la
usuaria pidió verlo en pantalla, no solo en un documento aparte, y que se
explique qué nombre técnico corresponde a qué nombre de su Matriz Maestra
(ej. "Instantiation" = su "Ingesta")."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ric.estado_modulos import MODULOS


class EstadoModulosTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("archivista", password="x")
        self.client.force_login(self.usuario)

    def test_requiere_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("ric_modulos"))
        self.assertEqual(respuesta.status_code, 302)

    def test_lista_los_20_modulos_con_su_codigo(self):
        respuesta = self.client.get(reverse("ric_modulos"))
        self.assertEqual(respuesta.status_code, 200)
        for m in MODULOS:
            self.assertContains(respuesta, m["codigo"])
            self.assertContains(respuesta, m["nombre"])

    def test_explica_la_correspondencia_de_nombres_de_f01(self):
        respuesta = self.client.get(reverse("ric_modulos"))
        self.assertContains(respuesta, "Instantiation")
        self.assertContains(respuesta, "Ingesta de documentos (F01/F02)")

    def test_el_resumen_suma_los_20_modulos(self):
        respuesta = self.client.get(reverse("ric_modulos"))
        total = sum(respuesta.context["resumen"].values())
        self.assertEqual(total, 20)

    def test_cada_modulo_tiene_estado_valido(self):
        estados_validos = {"completo", "pendiente", "parcial", "no"}
        for m in MODULOS:
            self.assertIn(m["estado"], estados_validos, m["codigo"])
