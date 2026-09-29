"""M9 · Exportación e interoperabilidad (/exportar): RF-M9-01 a RF-M9-03 y
el flujo "Exportar un lote de documentos"."""

from django.urls import reverse
from django.utils import timezone

from ric.models import Exportacion

from ._ayudas import CasoModulos, candidato


class ExportarTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento(nombre="Acta del Cabildo")
        [p] = self.proponer(self.record, candidato())
        p.validar(self.archivista, aceptar=True)
        self.otro, _ = self.documento(nombre="Otro documento", archivo="otro.txt")

    def _leer(self, exportacion):
        with exportacion.archivo.open("rb") as f:
            return f.read().decode("utf-8")

    def test_precarga_la_seleccion_del_catalogo(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("exportar"), {"doc": [self.record.pk]})
        self.assertContains(resp, f'name="doc" value="{self.record.pk}" checked')
        self.assertContains(resp, "RDF/RiC-O")
        self.assertContains(resp, "JSON-LD")
        self.assertContains(resp, "CSV")

    def test_exportar_rdf_conforme_a_rico_y_registrar(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("exportar"), {"doc": [self.record.pk, self.otro.pk], "formato": "rdf"}, follow=True)
        self.assertContains(resp, "Exportación lista")
        self.assertContains(resp, "Descargar")
        exp = Exportacion.objects.get()
        self.assertEqual(exp.usuario, self.archivista)  # RF-M9-03
        self.assertEqual(exp.total_registros, 2)
        self.assertEqual(sorted(exp.documentos), sorted([self.record.pk, self.otro.pk]))
        contenido = self._leer(exp)
        self.assertIn("rico:hasCreator", contenido)
        self.assertIn("Cabildo de Santafé", contenido)
        self.assertIn("rico:Record", contenido)

    def test_exportar_json_ld_y_csv(self):
        self.client.force_login(self.archivista)
        self.client.post(reverse("exportar"), {"doc": [self.record.pk], "formato": "json-ld"})
        self.client.post(reverse("exportar"), {"doc": [self.record.pk], "formato": "csv"})
        json_ld = Exportacion.objects.get(formato="json-ld")
        self.assertIn('"@id"', self._leer(json_ld))
        csv_ = Exportacion.objects.get(formato="csv")
        contenido = self._leer(csv_)
        self.assertIn("documento_id,documento,forma_documental,relacion_id", contenido)
        self.assertIn("R027,has creator,Procedencia,Cabildo de Santafé,CorporateBody", contenido)

    def test_descargar_entrega_el_archivo(self):
        self.client.force_login(self.archivista)
        self.client.post(reverse("exportar"), {"doc": [self.record.pk], "formato": "csv"})
        exp = Exportacion.objects.get()
        resp = self.client.get(reverse("exportar_descargar", args=[exp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        self.assertIn("documento_id", b"".join(resp.streaming_content).decode())

    def test_registro_de_exportaciones_en_la_pantalla(self):
        self.client.force_login(self.archivista)
        self.client.post(reverse("exportar"), {"doc": [self.record.pk], "formato": "rdf"})
        resp = self.client.get(reverse("exportar"))
        self.assertContains(resp, "Registro de exportaciones")
        self.assertContains(resp, "archivista")
        self.assertContains(resp, "RDF/RiC-O")

    def test_consulta_solo_exporta_publicados(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("exportar"), {"doc": [self.record.pk], "formato": "rdf"}, follow=True)
        self.assertContains(resp, "Seleccione al menos un documento")
        self.assertFalse(Exportacion.objects.exists())
        self.record.publicado, self.record.fecha_publicacion = True, timezone.now()
        self.record.save()
        self.client.post(reverse("exportar"), {"doc": [self.record.pk], "formato": "rdf"})
        self.assertEqual(Exportacion.objects.count(), 1)

    def test_sin_formato_ni_documentos_avisa(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("exportar"), {"doc": [self.record.pk], "formato": "xls"}, follow=True)
        self.assertContains(resp, "Elija un formato")
        resp = self.client.post(reverse("exportar"), {"formato": "rdf"}, follow=True)
        self.assertContains(resp, "Seleccione al menos un documento")
