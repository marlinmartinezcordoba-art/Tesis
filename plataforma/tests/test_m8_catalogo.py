"""M8 · Catálogo y consulta (/catalogo): RF-M8-01 a RF-M8-04 y el flujo
"Buscar una entidad o un documento en el catálogo"."""

from django.urls import reverse
from django.utils import timezone

from ric.models import CorporateBody, Instantiation

from ._ayudas import CasoModulos, candidato


class CatalogoTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento(nombre="Acta del Cabildo")
        [p] = self.proponer(self.record, candidato())
        p.validar(self.archivista, aceptar=True)
        self.cabildo = CorporateBody.objects.get(nombre="Cabildo de Santafé")
        self.borrador, _ = self.documento(nombre="Borrador sin publicar", archivo="b.txt")

    def _publicar(self, record):
        record.publicado = True
        record.fecha_publicacion = timezone.now()
        record.save()

    def test_consulta_solo_ve_documentos_publicados(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("catalogo"))
        self.assertNotContains(resp, "Acta del Cabildo")
        self.assertContains(resp, "Su cuenta es de consulta")
        self._publicar(self.record)
        resp = self.client.get(reverse("catalogo"))
        self.assertContains(resp, "Acta del Cabildo")
        self.assertNotContains(resp, "Borrador sin publicar")  # RF-M8-04

    def test_archivista_ve_todo_con_su_estado(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("catalogo"))
        self.assertContains(resp, "Acta del Cabildo")
        self.assertContains(resp, "Borrador sin publicar")
        self.assertContains(resp, "En revisión archivística")

    def test_busqueda_por_texto_libre_y_por_nombre_de_entidad(self):
        self._publicar(self.record)
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("catalogo"), {"q": "levantamiento"})  # palabra del contenido
        self.assertContains(resp, "Acta del Cabildo")
        resp = self.client.get(reverse("catalogo"), {"q": "cabildo"})
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertContains(resp, "1 documento(s) relacionado(s)")

    def test_filtro_por_clase_de_entidad(self):
        self._publicar(self.record)
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("catalogo"), {"q": "cabildo", "clase": "agente"})
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertNotContains(resp, "📄 Documento")
        resp = self.client.get(reverse("catalogo"), {"q": "cabildo", "clase": "lugar"})
        self.assertNotContains(resp, "Cabildo de Santafé")

    def test_sugerencias_mientras_se_escribe(self):
        self._publicar(self.record)
        self.client.force_login(self.consulta)
        datos = self.client.get(reverse("catalogo_sugerencias"), {"q": "cab"}).json()
        self.assertIn("Acta del Cabildo", datos["sugerencias"])
        self.assertIn("Cabildo de Santafé", datos["sugerencias"])

    def test_ficha_de_entidad_navega_a_sus_documentos_y_al_grafo(self):
        self._publicar(self.record)
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("catalogo_ficha", args=["corporatebody", self.cabildo.pk]))
        self.assertContains(resp, "Acta del Cabildo")  # RF-M8-02
        self.assertContains(resp, reverse("catalogo_ficha", args=["record", self.record.pk]))  # RF-M8-03
        self.assertContains(resp, reverse("ric_grafo", args=["corporatebody", self.cabildo.pk]))  # Ver en grafo
        resp = self.client.get(reverse("catalogo_ficha", args=["record", self.record.pk]))
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertContains(resp, "has creator")

    def test_ficha_de_documento_no_publicado_no_se_abre_a_consulta(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("catalogo_ficha", args=["record", self.record.pk]), follow=True)
        self.assertContains(resp, "todavía no está publicado")

    def test_instanciacion_reservada_oculta_el_documento_a_consulta(self):
        self._publicar(self.record)
        self.client.force_login(self.archivista)
        self.client.post(reverse("catalogo_ficha", args=["record", self.record.pk]), {f"acceso_{self.inst.pk}": "reservado"})
        self.inst.refresh_from_db()
        self.assertEqual(self.inst.condicion_acceso, Instantiation.CondicionAcceso.RESERVADO)
        self.client.force_login(self.consulta)
        self.assertNotContains(self.client.get(reverse("catalogo")), "Acta del Cabildo")

    def test_seleccion_para_exportar_lleva_a_exportar_precargado(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("catalogo"))
        self.assertContains(resp, f'name="doc" value="{self.record.pk}"')
        self.assertContains(resp, "Exportar selección")
