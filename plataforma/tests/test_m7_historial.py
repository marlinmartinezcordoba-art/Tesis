"""M7 · Trazabilidad y auditoría (/documentos/:id/historial): RF-M7-01 a
RF-M7-03 — incluida la reconstrucción del estado exacto en un instante."""

import datetime

from django.urls import reverse
from django.utils import timezone

from ric import flujo
from ric.models import EventoRiC, RelacionRiC

from ._ayudas import CasoModulos, candidato


class HistorialTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento()
        [p] = self.proponer(self.record, candidato())
        p.validar(self.archivista, aceptar=True)
        self.relacion = RelacionRiC.objects.get(relacion_id="R027")

    def test_roles(self):
        self.client.force_login(self.consulta)
        self.assertContains(self.client.get(reverse("historial", args=[self.record.pk]), follow=True), "requiere el rol")
        self.client.force_login(self.revisor)
        self.assertEqual(self.client.get(reverse("historial_lista")).status_code, 200)

    def test_linea_de_tiempo_con_propuesta_y_decision_humana(self):
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("historial", args=[self.record.pk]))
        self.assertContains(resp, "Extracción de texto")
        self.assertContains(resp, "Propuesta generada por IA")  # RF-M7-01
        self.assertContains(resp, "Validación humana")
        self.assertContains(resp, "archivista")
        self.assertContains(resp, "Cadena de eventos verificada")
        self.assertContains(resp, "ver la descripción en este momento")

    def test_reconstruye_el_estado_anterior_de_la_descripcion(self):
        antes = timezone.now()
        self.relacion.relacion_id = "R026"
        self.relacion.save()  # F07: la versión anterior (R027) queda guardada
        filas = flujo.descripcion_en(self.record, antes)
        self.assertEqual([f["relacion_id"] for f in filas], ["R027"])  # RF-M7-03
        self.assertTrue(filas[0]["reconstruida"])
        ahora = flujo.descripcion_en(self.record, timezone.now())
        self.assertEqual([f["relacion_id"] for f in ahora], ["R026"])
        self.assertEqual(flujo.descripcion_en(self.record, antes - datetime.timedelta(days=1)), [])

    def test_la_pantalla_muestra_la_reconstruccion(self):
        antes = timezone.now()
        self.relacion.relacion_id = "R026"
        self.relacion.save()
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("historial", args=[self.record.pk]), {"momento": antes.isoformat()})
        self.assertContains(resp, "Descripción al")
        self.assertContains(resp, "R027 has creator")
        self.assertContains(resp, "reconstruida desde el historial")

    def test_cadena_alterada_se_detecta(self):
        evento = EventoRiC.objects.filter(instanciacion=self.inst).first()
        EventoRiC.objects.filter(pk=evento.pk).update(agente="alguien más")
        self.client.force_login(self.archivista)
        self.assertContains(self.client.get(reverse("historial", args=[self.record.pk])), "presenta una alteración")
