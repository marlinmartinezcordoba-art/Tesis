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
        self.assertIn("/admin/login/", respuesta.url)

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
            "ric_inicio", "ric_subir", "ric_registros", "ric_bandeja",
            "ric_sparql", "ric_busqueda", "ric_evaluacion", "ric_modulos",
        ]
        for nombre in urls_get:
            respuesta = self.client.get(reverse(nombre))
            self.assertEqual(respuesta.status_code, 302, f"{nombre} no exige sesión")
            self.assertIn("/admin/login/", respuesta.url, nombre)
