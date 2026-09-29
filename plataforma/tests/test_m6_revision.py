"""M6 · Revisión archivística (/revision/:id): RF-M6-01 a RF-M6-04, CC-03
en el servidor, y la ruta alterna de rechazo del flujo 2."""

from django.urls import reverse

from ric.models import EventoRiC, PropuestaRiC, RelacionRiC

from ._ayudas import CasoModulos, candidato


class RevisionTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        [p] = self.proponer(self.record, candidato(datos_extra={"rol_en_el_documento": "firmante"}))
        p.validar(self.archivista, aceptar=True)
        self.relacion = RelacionRiC.objects.get(relacion_id="R027")

    def test_roles(self):
        self.client.force_login(self.consulta)
        self.assertContains(self.client.get(reverse("revision", args=[self.record.pk]), follow=True), "requiere el rol archivista o revisor")
        self.client.force_login(self.revisor)
        self.assertEqual(self.client.get(reverse("revision_lista")).status_code, 200)

    def test_comparacion_lado_a_lado_por_ficha(self):
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("revision", args=[self.record.pk]))
        self.assertContains(resp, "Propuesto por el motor")
        self.assertContains(resp, "Decisión de la revisión")
        self.assertContains(resp, "✓ Aceptar")  # RF-M6-01: campo editable y aceptar/rechazar por ficha
        self.assertContains(resp, "Rol en el documento: firmante")
        self.assertContains(resp, "origen: propuesta de IA")  # CC-08
        self.assertContains(resp, "Confirmar rechazo")  # RF-M6-02: decisión por ficha
        self.assertContains(resp, "Aprobar y publicar")

    def test_publicar_bloqueado_mientras_haya_pendientes(self):
        self.proponer(self.record, candidato(entidad_nombre="Bogotá", entidad_tipo="E22", relacion_id="R019", evidencia="Bogotá"))
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("revision", args=[self.record.pk]))
        self.assertContains(resp, "sin decidir en el motor de análisis")
        self.assertContains(resp, "disabled")
        resp = self.client.post(reverse("revision_aprobar", args=[self.record.pk]), follow=True)
        self.assertContains(resp, "No se puede publicar")  # RF-M6-04 en el servidor
        self.record.refresh_from_db()
        self.assertFalse(self.record.publicado)

    def test_cc03_sin_procedencia_no_se_publica(self):
        self.relacion.relacion_id = "R019"  # deja de ser procedencia
        self.relacion.revision = RelacionRiC.Revision.CONFIRMADA
        self.relacion.save()
        self.client.force_login(self.revisor)
        resp = self.client.post(reverse("revision_aprobar", args=[self.record.pk]), follow=True)
        self.assertContains(resp, "relación de procedencia")
        self.record.refresh_from_db()
        self.assertFalse(self.record.publicado)

    def test_aprobar_y_publicar_pasa_al_catalogo(self):
        self.client.force_login(self.revisor)
        self.client.post(reverse("revision_confirmar", args=[self.record.pk, self.relacion.pk]), {"nombre": "Cabildo de Santafé"})
        resp = self.client.post(reverse("revision_aprobar", args=[self.record.pk]))
        self.assertRedirects(resp, reverse("catalogo"), fetch_redirect_response=False)
        self.record.refresh_from_db()
        self.assertTrue(self.record.publicado)
        self.assertEqual(self.record.publicado_por, self.revisor)
        self.assertIsNotNone(self.record.fecha_publicacion)
        self.assertTrue(EventoRiC.objects.filter(tipo=EventoRiC.Tipo.PUBLICACION, instanciacion=self.inst).exists())

    def test_rechazar_exige_motivo(self):
        self.client.force_login(self.revisor)
        resp = self.client.post(reverse("revision_rechazar", args=[self.record.pk, self.relacion.pk]), {"motivo": ""}, follow=True)
        self.assertContains(resp, "Escriba el motivo")  # RF-M6-03
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.estado, RelacionRiC.Estado.ACEPTADA)

    def test_rechazar_devuelve_al_motor_de_analisis_y_retira_del_catalogo(self):
        self.record.publicado = True
        self.record.save()
        self.client.force_login(self.revisor)
        resp = self.client.post(reverse("revision_rechazar", args=[self.record.pk, self.relacion.pk]), {"motivo": "No es el productor."})
        self.assertRedirects(resp, f"/analisis/{self.record.pk}/?rechazada={self.relacion.pk}", fetch_redirect_response=False)
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.estado, RelacionRiC.Estado.RECHAZADA)
        self.assertEqual(self.relacion.motivo_decision, "No es el productor.")
        self.record.refresh_from_db()
        self.assertFalse(self.record.publicado)
        resp = self.client.get(resp.url)
        self.assertContains(resp, "Rechazada en revisión")
        self.assertContains(resp, "No es el productor.")
        self.assertContains(resp, "nueva propuesta")  # el revisor ve el aviso; generar es del archivista
        self.client.force_login(self.archivista)
        self.assertContains(self.client.get(resp.request["PATH_INFO"] + "?rechazada=" + str(self.relacion.pk)), "Generar nueva propuesta")
        self.assertEqual(PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE).count(), 0)
