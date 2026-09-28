"""Panel de inicio (rediseño): las nuevas métricas — distribución de
entidades, ingesta por día, actividad reciente, documentos recientes —
deben ser datos reales, nunca simulados. Estas pruebas verifican eso, no
solo que la pantalla cargue.
"""

import datetime
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ric.models import CorporateBody, Instantiation, Record

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class DistribucionDeEntidadesTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(self.archivista)

    def test_cuenta_records_y_agentes_reales_por_separado(self):
        Record.objects.create(nombre="Acta")
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        resp = self.client.get(reverse("ric_inicio"))
        distribucion = {f["tipo"]: f["total"] for f in resp.context["distribucion"]}
        self.assertEqual(distribucion["Record"], 1)
        self.assertEqual(distribucion["Agent"], 1)
        self.assertEqual(resp.context["total_entidades"], 2)

    def test_sin_ninguna_entidad_el_total_es_cero(self):
        resp = self.client.get(reverse("ric_inicio"))
        self.assertEqual(resp.context["total_entidades"], 0)
        self.assertIn("#e6e3dc", resp.context["gradiente_distribucion"])

    def test_invitado_de_consulta_no_ve_el_panel_de_distribucion(self):
        invitado = User.objects.create_user("consulta", password="x", is_staff=False)
        self.client.force_login(invitado)
        resp = self.client.get(reverse("ric_inicio"))
        self.assertNotIn("distribucion", resp.context)


@override_settings(MEDIA_ROOT=MEDIA)
class DocumentosSinTextoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(self.archivista)

    def test_documento_sin_ninguna_paginatexto_cuenta_como_sin_texto(self):
        record = Record.objects.create(nombre="Acta")
        Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("a.wav", b"contenido no soportado"),
        )
        resp = self.client.get(reverse("ric_inicio"))
        self.assertEqual(resp.context["documentos_sin_texto"], 1)

    def test_documento_con_texto_extraido_no_cuenta(self):
        from ric.extraccion import extraer_texto_de_instanciacion

        record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("a.txt", b"Texto real del documento."),
        )
        extraer_texto_de_instanciacion(inst)
        resp = self.client.get(reverse("ric_inicio"))
        self.assertEqual(resp.context["documentos_sin_texto"], 0)


@override_settings(MEDIA_ROOT=MEDIA)
class ActividadPorDiaTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(self.archivista)

    def test_catorce_dias_con_el_de_hoy_al_final(self):
        record = Record.objects.create(nombre="Acta")
        Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("a.txt", b"contenido"),
        )
        resp = self.client.get(reverse("ric_inicio"))
        serie = resp.context["actividad_dias"]
        self.assertEqual(len(serie), 14)
        hoy = timezone.localdate().strftime("%d/%m")
        self.assertEqual(serie[-1]["etiqueta"], hoy)
        self.assertEqual(serie[-1]["total"], 1)
        self.assertEqual(serie[-1]["porcentaje"], 100)

    def test_sin_ingesta_reciente_todas_las_barras_en_cero(self):
        resp = self.client.get(reverse("ric_inicio"))
        serie = resp.context["actividad_dias"]
        self.assertTrue(all(d["total"] == 0 for d in serie))
        self.assertTrue(all(d["porcentaje"] == 0 for d in serie))


@override_settings(MEDIA_ROOT=MEDIA)
class ActividadYDocumentosRecientesTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(self.archivista)

    def test_extraer_texto_deja_un_evento_visible_en_el_inicio(self):
        from ric.extraccion import extraer_texto_de_instanciacion

        record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia del acta", record_resource=record,
            archivo=SimpleUploadedFile("a.txt", b"Texto real."),
        )
        extraer_texto_de_instanciacion(inst)
        resp = self.client.get(reverse("ric_inicio"))
        self.assertContains(resp, "Extracción de texto")
        self.assertContains(resp, "Copia del acta")

    def test_documento_reciente_aparece_en_la_tabla(self):
        record = Record.objects.create(nombre="Acta")
        Instantiation.objects.create(
            nombre="Escaneo original", record_resource=record,
            archivo=SimpleUploadedFile("a.txt", b"contenido"),
        )
        resp = self.client.get(reverse("ric_inicio"))
        self.assertContains(resp, "Escaneo original")

    def test_sin_documentos_muestra_aviso_honesto(self):
        resp = self.client.get(reverse("ric_inicio"))
        self.assertContains(resp, "Todavía no se ha subido ningún documento")
