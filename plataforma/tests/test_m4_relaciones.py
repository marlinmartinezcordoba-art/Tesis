"""M4 · Modelado de relaciones (/analisis/:id/grafo): RF-M4-01 a RF-M4-04."""

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from ric import grafo
from ric.models import CorporateBody, EventoRiC, RelacionRiC, VersionRiC

from ._ayudas import CasoModulos, candidato


class GrafoDelDocumentoTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        [p] = self.proponer(self.record, candidato())
        p.validar(self.archivista, aceptar=True)
        self.relacion = RelacionRiC.objects.get(relacion_id="R027")
        self.proponer(self.record, candidato(entidad_nombre="Bogotá", entidad_tipo="E22", relacion_id="R019", evidencia="Bogotá"))
        self.client.force_login(self.archivista)

    def test_categorias_de_relacion(self):
        self.assertEqual(grafo.categoria_relacion("R027"), "procedencia")
        self.assertEqual(grafo.categoria_relacion("R019"), "asociacion")

    def test_datos_del_lienzo_traen_relaciones_validadas_y_propuestas_pendientes(self):
        datos = self.client.get(reverse("analisis_grafo_datos", args=[self.record.pk])).json()
        ids = {n["data"]["id"] for n in datos["nodes"]}
        self.assertIn(f"Record:{self.record.pk}", ids)
        arista = next(e["data"] for e in datos["edges"] if e["data"]["id"] == f"rel:{self.relacion.pk}")
        self.assertEqual(arista["categoria"], "procedencia")
        self.assertIn({"id": "R027", "nombre": "has creator", "categoria": "procedencia"}, arista["opciones"])  # RF-M4-03: lista controlada
        self.assertTrue(all(o["id"] != "R070" for o in arista["opciones"]))  # dominio Date: no aplica
        propuesta = [e["data"] for e in datos["edges"] if e["data"].get("propuesta")]
        self.assertEqual(len(propuesta), 1)  # RF-M4-01: lo generado automáticamente, punteado

    def test_la_pantalla_carga_con_leyenda_y_boton_a_revision(self):
        resp = self.client.get(reverse("analisis_grafo", args=[self.record.pk]))
        self.assertContains(resp, "Procedencia")
        self.assertContains(resp, "Enviar a revisión final")
        self.assertContains(resp, "cytoscape")

    def test_corregir_el_tipo_de_relacion_desde_la_lista_controlada(self):
        resp = self.client.post(reverse("analisis_relacion", args=[self.record.pk, self.relacion.pk]), {"accion": "cambiar_tipo", "relacion_id": "R026"}, follow=True)
        self.assertContains(resp, "Tipo de relación corregido")
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.relacion_id, "R026")
        self.assertEqual(self.relacion.estado, RelacionRiC.Estado.MODIFICADA)
        self.assertTrue(VersionRiC.objects.filter(content_type=ContentType.objects.get_for_model(RelacionRiC), object_id=self.relacion.pk).exists())
        self.assertTrue(EventoRiC.objects.filter(tipo=EventoRiC.Tipo.RELACION_EDITADA, detalle__a="R026").exists())

    def test_un_tipo_que_viola_dominio_o_rango_se_rechaza(self):
        resp = self.client.post(reverse("analisis_relacion", args=[self.record.pk, self.relacion.pk]), {"accion": "cambiar_tipo", "relacion_id": "R070"}, follow=True)
        self.assertContains(resp, "R070")
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.relacion_id, "R027")

    def test_eliminar_la_relacion_no_elimina_las_entidades(self):
        resp = self.client.post(reverse("analisis_relacion", args=[self.record.pk, self.relacion.pk]), {"accion": "eliminar", "motivo": "No es el productor."}, follow=True)
        self.assertContains(resp, "se conserva en los vocabularios")
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.estado, RelacionRiC.Estado.RECHAZADA)  # RF-M4-04 + CC-02: queda en el historial
        self.assertEqual(self.relacion.motivo_decision, "No es el productor.")
        self.assertTrue(CorporateBody.objects.filter(nombre="Cabildo de Santafé").exists())
        datos = self.client.get(reverse("analisis_grafo_datos", args=[self.record.pk])).json()
        self.assertFalse(any(e["data"]["id"] == f"rel:{self.relacion.pk}" for e in datos["edges"]))

    def test_el_revisor_ve_el_lienzo_pero_no_edita(self):
        self.client.force_login(self.revisor)
        self.assertEqual(self.client.get(reverse("analisis_grafo", args=[self.record.pk])).status_code, 200)
        resp = self.client.post(reverse("analisis_relacion", args=[self.record.pk, self.relacion.pk]), {"accion": "eliminar"}, follow=True)
        self.assertContains(resp, "requiere el rol archivista")
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.estado, RelacionRiC.Estado.ACEPTADA)
