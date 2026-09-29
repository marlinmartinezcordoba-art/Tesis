"""F16 (Seguridad): "cada ingreso pide contraseña" — hasta el archivo
original de un documento debe pasar por una vista con sesión iniciada,
nunca por una URL abierta.

Se descubrió, revisando esto, que Django solo sirve /media/ cuando
DEBUG=1: en el servidor real (DJANGO_DEBUG=0) esa URL no existe en
absoluto, así que antes de esta vista el archivo original no tenía
ninguna forma real de descargarse en producción — ni siquiera con sesión
iniciada."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ric.models import Instantiation, Record

MEDIA = tempfile.mkdtemp()
TEXTO = "Acta del Cabildo de Santafé, 20 de julio de 1810."


@override_settings(MEDIA_ROOT=MEDIA)
class ServirArchivoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.usuario = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta")
        self.inst = Instantiation.objects.create(
            nombre="Copia", record_resource=self.record,
            archivo=SimpleUploadedFile("acta.txt", TEXTO.encode()),
        )

    def test_sin_sesion_no_entrega_el_archivo(self):
        respuesta = self.client.get(reverse("ric_archivo", args=[self.inst.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("ric_login"), respuesta.url)

    def test_con_sesion_entrega_el_contenido_real_del_archivo(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("ric_archivo", args=[self.inst.pk]))
        self.assertEqual(respuesta.status_code, 200)
        contenido = b"".join(respuesta.streaming_content)
        self.assertEqual(contenido, TEXTO.encode())

    def test_archivo_inexistente_da_404(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("ric_archivo", args=[999999]))
        self.assertEqual(respuesta.status_code, 404)


@override_settings(MEDIA_ROOT=MEDIA)
class TodasLasVistasRicExigenSesionTest(TestCase):
    """"Que cada ingreso pida contraseña": ninguna URL de /ric/ debe
    responder 200 sin sesión iniciada."""

    def test_urls_get_sin_argumentos_redirigen_a_login(self):
        urls_get = [
            "panel", "ingesta", "preproceso", "analisis_lista", "vocabularios",
            "vocabularios_duplicados", "revision_lista", "historial_lista",
            "catalogo", "exportar", "ric_sparql", "ric_evaluacion", "admin_usuarios",
        ]
        for nombre in urls_get:
            respuesta = self.client.get(reverse(nombre))
            self.assertEqual(respuesta.status_code, 302, f"{nombre} no exige sesión")
            self.assertIn(reverse("ric_login"), respuesta.url, nombre)


class BotonSalirTest(TestCase):
    """El botón "Salir" del menú debe cerrar la sesión de verdad.

    Dos bugs reales encontrados en el camino:
    1. Antes "Salir" era un <a href> (petición GET) a /admin/logout/, que
       desde Django 4.1 solo acepta POST — el enlace daba 405 y la sesión
       nunca se cerraba.
    2. /admin/logout/ está además envuelto por el propio chequeo de
       permisos del admin de Django: para una persona sin is_staff (el
       invitado de consulta de F16), esa URL ni siquiera llega a cerrar
       la sesión, solo rebota a /admin/ sin pasar por la vista de logout.

    Por eso "Salir" ahora apunta a ric_logout (LogoutView de Django sin
    envolver), que cierra la sesión de cualquier persona autenticada,
    tenga o no is_staff."""

    def test_la_pagina_ya_no_usa_un_enlace_get_para_salir(self):
        usuario = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("panel"))
        self.assertNotContains(respuesta, '<a href="/admin/logout/">')
        self.assertContains(respuesta, reverse("ric_logout"))

    def test_enviar_el_formulario_de_salir_cierra_la_sesion_de_un_archivista(self):
        usuario = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(usuario)
        respuesta = self.client.post(reverse("ric_logout"), follow=True)
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.get(reverse("panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("ric_login"), respuesta.url)

    def test_enviar_el_formulario_de_salir_cierra_la_sesion_de_un_invitado(self):
        # el bug de /admin/logout/ (punto 2 arriba) era justo para este caso
        usuario = User.objects.create_user("consulta", password="x", is_staff=False)
        self.client.force_login(usuario)
        respuesta = self.client.post(reverse("ric_logout"), follow=True)
        self.assertEqual(respuesta.status_code, 200)

        respuesta = self.client.get(reverse("panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("ric_login"), respuesta.url)


class PantallaDeIngresoTest(TestCase):
    """/ric/entrar/: el único punto de ingreso, para los dos perfiles.

    Antes de esto, LOGIN_URL era /admin/login/ — cuyo formulario de
    Django rechaza de plano a cualquier usuario sin is_staff ("para
    obtener cuenta de personal"), así que un invitado de consulta (F16)
    no podía iniciar sesión de ninguna manera, ni con la contraseña
    correcta."""

    def test_get_muestra_el_formulario(self):
        respuesta = self.client.get(reverse("ric_login"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Entrar")

    def test_un_archivista_si_puede_entrar_aqui(self):
        User.objects.create_user("archivista", password="x", is_staff=True)
        respuesta = self.client.post(reverse("ric_login"), {"username": "archivista", "password": "x"})
        self.assertRedirects(respuesta, reverse("panel"))

    def test_un_invitado_de_consulta_tambien_puede_entrar_aqui(self):
        # esto es justo lo que /admin/login/ no permitía
        User.objects.create_user("consulta", password="x", is_staff=False)
        respuesta = self.client.post(reverse("ric_login"), {"username": "consulta", "password": "x"})
        self.assertRedirects(respuesta, reverse("panel"))

    def test_credenciales_incorrectas_no_entran(self):
        User.objects.create_user("consulta", password="x", is_staff=False)
        respuesta = self.client.post(reverse("ric_login"), {"username": "consulta", "password": "mala"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "incorrect")

    def test_una_pantalla_protegida_redirige_aqui_y_no_al_admin(self):
        respuesta = self.client.get(reverse("panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("ric_login"), respuesta.url)
        self.assertNotIn("/admin/login/", respuesta.url)
