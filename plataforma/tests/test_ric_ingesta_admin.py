"""F01 (Ingesta y preservación de evidencia): pruebas de que subir un
archivo por el admin —de a uno o en carga masiva— calcula el hash y
extrae el texto (OCR si aplica) automáticamente, sin un paso manual
aparte. Antes de esto, `calcular_y_guardar_hash()` existía pero nunca se
llamaba en el flujo real; estas pruebas cubren ese defecto."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from ric.models import Instantiation, Record

MEDIA = tempfile.mkdtemp()
TEXTO = "Acta del Cabildo de Santafé, 20 de julio de 1810."


@override_settings(MEDIA_ROOT=MEDIA)
class IngestaAutomaticaAdminTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="x")
        self.client.force_login(self.admin)
        self.record = Record.objects.create(nombre="Acta")

    def _archivo(self, nombre="acta.txt", contenido=None):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(nombre, (contenido or TEXTO).encode())

    def test_alta_directa_de_instantiation_calcula_hash_y_extrae_texto(self):
        url = reverse("admin:ric_instantiation_add")
        respuesta = self.client.post(url, {
            "nombre": "Copia digital",
            "record_resource": self.record.pk,
            "archivo": self._archivo(),
            "tipo_soporte": "", "extension_soporte": "",
            "tipo_representacion": "", "caracteristicas_fisicas": "",
            "paginas-TOTAL_FORMS": "0", "paginas-INITIAL_FORMS": "0",
            "paginas-MIN_NUM_FORMS": "0", "paginas-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(respuesta.status_code, 302, respuesta.context["adminform"].errors if respuesta.status_code != 302 else None)
        inst = Instantiation.objects.get(record_resource=self.record)
        self.assertEqual(len(inst.sha256), 64)
        self.assertEqual(inst.paginas.count(), 1)
        self.assertIn("Cabildo", inst.texto_extraido)

    def test_alta_de_formato_no_soportado_preserva_hash_sin_texto(self):
        url = reverse("admin:ric_instantiation_add")
        respuesta = self.client.post(url, {
            "nombre": "Audio",
            "record_resource": self.record.pk,
            "archivo": self._archivo(nombre="nota.mp3", contenido="ID3"),
            "tipo_soporte": "", "extension_soporte": "",
            "tipo_representacion": "", "caracteristicas_fisicas": "",
            "paginas-TOTAL_FORMS": "0", "paginas-INITIAL_FORMS": "0",
            "paginas-MIN_NUM_FORMS": "0", "paginas-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(respuesta.status_code, 302)
        inst = Instantiation.objects.get(record_resource=self.record)
        self.assertEqual(len(inst.sha256), 64)
        self.assertEqual(inst.paginas.count(), 0)

    def test_carga_masiva_de_varios_archivos_en_el_record(self):
        url = reverse("admin:ric_record_change", args=[self.record.pk])
        respuesta = self.client.post(url, {
            "nombre": "Acta", "tipo_forma_documental": "", "record_set": "",
            "instanciaciones-TOTAL_FORMS": "2", "instanciaciones-INITIAL_FORMS": "0",
            "instanciaciones-MIN_NUM_FORMS": "0", "instanciaciones-MAX_NUM_FORMS": "1000",
            "instanciaciones-0-record_resource": self.record.pk,
            "instanciaciones-0-nombre": "Copia 1",
            "instanciaciones-0-archivo": self._archivo("acta1.txt"),
            "instanciaciones-0-tipo_soporte": "",
            "instanciaciones-1-record_resource": self.record.pk,
            "instanciaciones-1-nombre": "Copia 2",
            "instanciaciones-1-archivo": self._archivo("acta2.txt"),
            "instanciaciones-1-tipo_soporte": "",
        })
        self.assertEqual(respuesta.status_code, 302)
        instancias = Instantiation.objects.filter(record_resource=self.record).order_by("nombre")
        self.assertEqual(instancias.count(), 2)
        self.assertEqual([i.nombre for i in instancias], ["Copia 1", "Copia 2"])
        for inst in instancias:
            self.assertEqual(len(inst.sha256), 64)
            self.assertEqual(inst.paginas.count(), 1)

    def test_extraer_texto_manual_sigue_disponible_para_reprocesar(self):
        # F01: aunque ahora la extracción es automática al ingerir, la
        # acción manual del admin se conserva para volver a correr OCR
        # (por ejemplo si el archivo se reemplazó).
        from ric.models import Instantiation as Inst

        inst = Inst.objects.create(
            nombre="Copia", record_resource=self.record, archivo=self._archivo(),
        )
        inst.paginas.all().delete()
        self.assertEqual(inst.paginas.count(), 0)

        url = reverse("admin:ric_instantiation_changelist")
        self.client.post(url, {
            "action": "extraer_texto",
            "_selected_action": [str(inst.pk)],
        })
        inst.refresh_from_db()
        self.assertEqual(inst.paginas.count(), 1)
