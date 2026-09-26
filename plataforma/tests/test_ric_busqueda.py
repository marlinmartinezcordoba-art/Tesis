"""Pruebas de la búsqueda contextual (T053 / F14): texto completo sobre lo
ya extraído y nombres de entidades, con navegación al grafo de cada una."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ric import busqueda
from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import CorporateBody, Instantiation, Record, RecordSet

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class BuscarTextoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.record = Record.objects.create(nombre="Acta")
        self.inst = Instantiation.objects.create(
            nombre="Copia", record_resource=self.record,
            archivo=SimpleUploadedFile("acta.txt", "El cabildo reunido acuerda proclamar la independencia.".encode()),
        )
        extraer_texto_de_instanciacion(self.inst)

    def test_encuentra_por_forma_conjugada_no_solo_la_cadena_exacta(self):
        resultados = list(busqueda.buscar_texto("proclamación"))  # no "proclamar" literal
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].instanciacion_id, self.inst.pk)

    def test_consulta_sin_coincidencia_no_devuelve_nada(self):
        self.assertEqual(list(busqueda.buscar_texto("dinosaurio")), [])

    def test_consulta_de_varias_palabras_sin_coincidencia_no_devuelve_nada(self):
        # ts_rank puede devolver un valor flotante minúsculo pero distinto de
        # cero para una consulta AND de varios términos que no encaja del
        # todo (p. ej. 1e-20) — filtrar por rank__gt=0 lo dejaría pasar; hay
        # que filtrar por la coincidencia booleana real (@@), no por el rank.
        self.assertEqual(list(busqueda.buscar_texto("dinosaurios en la luna")), [])


class BuscarEntidadesTest(TestCase):
    def setUp(self):
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        self.fondo = RecordSet.objects.create(nombre="Fondo Cabildo Colonial")
        CorporateBody.objects.create(nombre="Otra entidad")

    def test_encuentra_coincidencias_parciales_de_nombre(self):
        resultados = busqueda.buscar_entidades("cabildo")
        nombres = {e.nombre for e in resultados}
        self.assertEqual(nombres, {"Cabildo de Santafé", "Fondo Cabildo Colonial"})

    def test_no_duplica_filas_de_tipos_con_herencia_multitabla(self):
        # CorporateBody hereda de Group (RiC-CM E09): no debe buscarse dos
        # veces la misma fila como Group y como CorporateBody.
        resultados = busqueda.buscar_entidades("Cabildo de Santafé")
        self.assertEqual(len(resultados), 1)


class BusquedaViewTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        CorporateBody.objects.create(nombre="Cabildo de Santafé")

    def test_requiere_login(self):
        resp = self.client.get(reverse("ric_busqueda"), {"q": "cabildo"})
        self.assertEqual(resp.status_code, 302)

    def test_sin_query_no_busca(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_busqueda"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["entidades"], [])

    def test_encuentra_y_enlaza_al_grafo(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_busqueda"), {"q": "cabildo"})
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertContains(resp, "/ric/grafo/corporatebody/")
