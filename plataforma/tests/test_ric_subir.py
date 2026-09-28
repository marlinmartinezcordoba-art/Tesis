"""Pantalla simple "Subir documento" (fuera del panel técnico de Django):
la usuaria pidió mayor usabilidad porque no encontraba dónde estaba F01
en el admin — esta pantalla hace lo mismo (F01 hash, F02 OCR, F03
estructura, F04 propuesta de segmentación) en lenguaje llano."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ric.models import Instantiation, PropuestaSegmentacion, Record

MEDIA = tempfile.mkdtemp()
TEXTO = "Acta del Cabildo de Santafé, 20 de julio de 1810."


@override_settings(MEDIA_ROOT=MEDIA)
class SubirDocumentoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.usuario = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(self.usuario)

    def _archivo(self, nombre="acta.txt", contenido=None):
        return SimpleUploadedFile(nombre, (contenido or TEXTO).encode())

    def test_requiere_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse("ric_subir"))
        self.assertEqual(respuesta.status_code, 302)

    def test_get_lista_los_expedientes_existentes(self):
        Record.objects.create(nombre="Expediente ya cargado")
        respuesta = self.client.get(reverse("ric_subir"))
        self.assertContains(respuesta, "Expediente ya cargado")

    def test_subir_a_un_expediente_nuevo_procesa_todo_automaticamente(self):
        respuesta = self.client.post(reverse("ric_subir"), {
            "nombre_nuevo": "Acta del comité", "archivos": [self._archivo()],
        })
        self.assertEqual(respuesta.status_code, 200)
        record = Record.objects.get(nombre="Acta del comité")
        inst = Instantiation.objects.get(record_resource=record)
        self.assertEqual(len(inst.sha256), 64)
        self.assertEqual(inst.paginas.count(), 1)
        self.assertGreater(inst.componentes.count(), 0)
        self.assertContains(respuesta, "Subido y procesado correctamente")

    def test_subir_a_un_expediente_existente(self):
        record = Record.objects.create(nombre="Expediente ya cargado")
        respuesta = self.client.post(reverse("ric_subir"), {
            "record_id": record.pk, "archivos": [self._archivo()],
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Instantiation.objects.filter(record_resource=record).count(), 1)
        # no se creó un segundo expediente con el mismo nombre
        self.assertEqual(Record.objects.filter(nombre="Expediente ya cargado").count(), 1)

    def test_subir_varios_archivos_a_la_vez(self):
        respuesta = self.client.post(reverse("ric_subir"), {
            "nombre_nuevo": "Lote", "archivos": [self._archivo("a.txt"), self._archivo("b.txt")],
        })
        record = Record.objects.get(nombre="Lote")
        self.assertEqual(Instantiation.objects.filter(record_resource=record).count(), 2)
        self.assertContains(respuesta, "a.txt")
        self.assertContains(respuesta, "b.txt")

    def test_sin_expediente_elegido_ni_nombre_nuevo_muestra_error(self):
        respuesta = self.client.post(reverse("ric_subir"), {"archivos": [self._archivo()]})
        self.assertContains(respuesta, "Indique a qué expediente pertenece")
        self.assertEqual(Instantiation.objects.count(), 0)

    def test_sin_archivo_muestra_error(self):
        respuesta = self.client.post(reverse("ric_subir"), {"nombre_nuevo": "Algo"})
        self.assertContains(respuesta, "Seleccione al menos un archivo")
        self.assertEqual(Record.objects.filter(nombre="Algo").count(), 0)

    def test_formato_no_soportado_avisa_pero_preserva_el_archivo(self):
        respuesta = self.client.post(reverse("ric_subir"), {
            "nombre_nuevo": "Audio", "archivos": [self._archivo("nota.mp3", "ID3")],
        })
        inst = Instantiation.objects.get(nombre="nota.mp3")
        self.assertEqual(len(inst.sha256), 64)
        self.assertContains(respuesta, "no sabe extraer texto de este formato")

    def test_un_solo_documento_no_genera_falsa_alarma_de_segmentacion(self):
        oficio_112 = (
            "ALCALDÍA MUNICIPAL DE SAN PEDRO\nOFICIO No. 112-2025\n"
            "PARA: María López, Secretaria General\nDE: Juan Pérez, Jefe de Archivo\n"
            "ASUNTO: Jornada de organización documental\nAtentamente,\nJuan Pérez\nJefe de Archivo"
        )
        respuesta = self.client.post(reverse("ric_subir"), {
            "nombre_nuevo": "Lote de oficios", "archivos": [self._archivo("oficio.txt", oficio_112)],
        })
        self.assertEqual(PropuestaSegmentacion.objects.count(), 0)  # un solo título: nada que proponer
        self.assertNotContains(respuesta, "Revísalo en el panel técnico")
        self.assertContains(respuesta, "Subido y procesado correctamente")
