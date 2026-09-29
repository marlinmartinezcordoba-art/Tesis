"""Módulo 6 · Revisión archivística ficha por ficha (historia de usuario 6):
campo editable con aceptar/rechazar en cada ficha (RF-M6-01/02), motivo
obligatorio (RF-M6-03), publicación bloqueada mientras quede una ficha sin
revisar (RF-M6-04), baja confianza primero (CC-04), entidades compartidas
protegidas, clasificación estructural fuera de la revisión y trazabilidad."""

from django.urls import reverse

from ric import flujo
from ric.models import EventoRiC, Person, RegistroAuditoria, RelacionRiC, VersionRiC

from ._ayudas import CasoModulos, candidato


class RevisionPorFichaTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        [p] = self.proponer(self.record, candidato(datos_extra={"rol_en_el_documento": "firmante"}))
        p.validar(self.archivista, aceptar=True)
        self.relacion = RelacionRiC.objects.get(relacion_id="R027")
        self.client.force_login(self.revisor)

    def _url(self, nombre, rel=None):
        return reverse(nombre, args=[self.record.pk, (rel or self.relacion).pk])

    def test_lo_aceptado_en_el_analisis_llega_pendiente_de_revision(self):
        self.assertEqual(self.relacion.revision, RelacionRiC.Revision.PENDIENTE)
        resp = self.client.get(reverse("revision", args=[self.record.pk]))
        self.assertContains(resp, "0 de 1 fichas revisadas")
        self.assertContains(resp, f'name="nombre" value="{self.relacion.destino.nombre}"')  # RF-M6-01: campo editable
        self.assertContains(resp, "✓ Aceptar")
        self.assertContains(resp, "✗ Rechazar")
        self.assertContains(resp, "Quedan 1 ficha(s) por revisar")

    def test_publicar_bloqueado_hasta_revisar_cada_ficha(self):
        resp = self.client.get(reverse("revision", args=[self.record.pk]))
        self.assertContains(resp, 'disabled>Aprobar y publicar')
        resp = self.client.post(reverse("revision_aprobar", args=[self.record.pk]), follow=True)
        self.assertContains(resp, "ficha(s) sin revisar")  # RF-M6-04 verificado en el servidor
        self.record.refresh_from_db()
        self.assertFalse(self.record.publicado)

    def test_aceptar_la_ficha_tal_cual_habilita_publicar(self):
        resp = self.client.post(self._url("revision_confirmar"), {"nombre": "Cabildo de Santafé", "nota": "Verificado contra el original"}, follow=True)
        self.assertContains(resp, "Confirmada")
        self.assertContains(resp, "ya puede aprobar y publicar")
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.revision, RelacionRiC.Revision.CONFIRMADA)
        self.assertEqual(self.relacion.revisado_por, self.revisor)
        self.assertIn("Verificado contra el original", self.relacion.nota_revision)
        self.assertTrue(EventoRiC.objects.filter(instanciacion=self.inst, tipo=EventoRiC.Tipo.VALIDACION, detalle__revision="confirmada").exists())
        self.assertContains(resp, "Todo revisado")
        self.client.post(reverse("revision_aprobar", args=[self.record.pk]))
        self.record.refresh_from_db()
        self.assertTrue(self.record.publicado)

    def test_corregir_el_nombre_en_el_campo_y_aceptar(self):
        entidad = self.relacion.destino
        self.client.post(self._url("revision_confirmar"), {"nombre": "Cabildo de Santa Fe de Bogotá"})
        entidad.refresh_from_db()
        self.relacion.refresh_from_db()
        self.assertEqual(entidad.nombre, "Cabildo de Santa Fe de Bogotá")
        self.assertEqual(self.relacion.revision, RelacionRiC.Revision.CORREGIDA)
        self.assertIn("«Cabildo de Santafé» → «Cabildo de Santa Fe de Bogotá»", self.relacion.nota_revision)
        # nada se pierde: la versión anterior y la auditoría quedan
        self.assertTrue(VersionRiC.objects.filter(object_id=entidad.pk).exists())
        self.assertTrue(RegistroAuditoria.objects.filter(accion="modificar", object_id=entidad.pk, usuario=self.revisor).exists())

    def test_entidad_compartida_con_otro_documento_no_se_renombra_desde_aqui(self):
        otro, _ = self.documento(nombre="Otra acta", archivo="otra.txt", texto="Otra acta del Cabildo de Santafé, 1811.")
        [p] = self.proponer(otro, candidato(evidencia="Cabildo de Santafé"))
        p.validar(self.archivista, aceptar=True, entidad_existente=self.relacion.destino)
        resp = self.client.get(reverse("revision", args=[self.record.pk]))
        self.assertContains(resp, "también describe 1 documento(s) más")
        resp = self.client.post(self._url("revision_confirmar"), {"nombre": "Otro nombre"}, follow=True)
        self.assertContains(resp, "lo cambiaría en todos")
        self.relacion.destino.refresh_from_db()
        self.assertEqual(self.relacion.destino.nombre, "Cabildo de Santafé")
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.revision, RelacionRiC.Revision.PENDIENTE)

    def test_rechazo_exige_motivo_y_la_ficha_vuelve_al_analisis(self):
        resp = self.client.get(reverse("revision", args=[self.record.pk]))
        self.assertContains(resp, 'required placeholder="Ej. El firmante')  # RF-M6-03 en pantalla
        self.client.post(self._url("revision_rechazar"), {"motivo": "   "})
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.estado, RelacionRiC.Estado.ACEPTADA)
        self.client.post(self._url("revision_rechazar"), {"motivo": "El firmante es el secretario."})
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.estado, RelacionRiC.Estado.RECHAZADA)
        self.assertEqual(self.relacion.revisado_por, self.revisor)
        self.assertEqual(flujo.pendientes_revision(self.record).count(), 0)

    def test_baja_confianza_aparece_primero(self):
        [p2] = self.proponer(self.record, candidato(entidad_nombre="José Acevedo y Gómez", entidad_tipo="E08", evidencia="José Acevedo y Gómez", confianza=0.3))
        p2.validar(self.archivista, aceptar=True)
        resp = self.client.get(reverse("revision", args=[self.record.pk])).content.decode()
        self.assertLess(resp.index("José Acevedo y Gómez"), resp.index('value="Cabildo de Santafé"'))
        self.assertIn("baja confianza · revísela con atención (CC-04)", resp)

    def test_clasificacion_estructural_no_requiere_revision(self):
        from ric.instrumentos import _relacion_manual
        from ric.models import RecordSet

        expediente = RecordSet.objects.create(nombre="Expediente 1", tipo_conjunto=RecordSet.Tipo.EXPEDIENTE)
        _relacion_manual(expediente, self.record, "R024", self.archivista)
        estructural = RelacionRiC.objects.get(relacion_id="R024")
        self.assertEqual(estructural.revision, RelacionRiC.Revision.NO_APLICA)
        self.assertEqual(flujo.pendientes_revision(self.record).count(), 1)  # solo la de IA
        resp = self.client.get(reverse("revision", args=[self.record.pk]))
        self.assertContains(resp, "Clasificación archivística del documento (1)")
        resp = self.client.post(self._url("revision_rechazar", estructural), {"motivo": "x"}, follow=True)
        self.assertContains(resp, "se corrige desde la ingesta")

    def test_cambiar_el_tipo_de_relacion_la_devuelve_a_revision(self):
        self.client.post(self._url("revision_confirmar"), {"nombre": "Cabildo de Santafé"})
        self.client.force_login(self.archivista)
        self.client.post(reverse("analisis_relacion", args=[self.record.pk, self.relacion.pk]), {"accion": "cambiar_tipo", "relacion_id": "R026"})
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.revision, RelacionRiC.Revision.PENDIENTE)

    def test_consulta_no_revisa(self):
        self.client.force_login(self.consulta)
        self.client.post(self._url("revision_confirmar"), {"nombre": "x"})
        self.relacion.refresh_from_db()
        self.assertEqual(self.relacion.revision, RelacionRiC.Revision.PENDIENTE)

    def test_lista_muestra_fichas_por_revisar(self):
        resp = self.client.get(reverse("revision_lista"))
        self.assertContains(resp, "1 ficha(s) por revisar")
