"""Módulo 10 · Panel de indicadores (historia de usuario 10): cifras
vigentes por periodo elegido (RF-M10-01/02/03), alerta de revisión
atrasada que incluye las fichas sin revisar del M6 (RF-M10-04) y cada
indicador enlazado a la lista exacta de documentos que lo compone."""

import datetime

from django.urls import reverse
from django.utils import timezone

from ric import indicadores
from ric.models import ConfiguracionSistema, Record, RelacionRiC

from ._ayudas import CasoModulos, candidato


class IndicadoresTest(CasoModulos):
    def _antiguo(self, record, dias):
        Record.objects.filter(pk=record.pk).update(fecha_registro=timezone.now() - datetime.timedelta(days=dias))

    def test_selector_de_periodo_cambia_el_volumen_y_la_grafica(self):
        reciente, _ = self.documento(nombre="Reciente")
        viejo, _ = self.documento(nombre="Viejo", archivo="viejo.txt", texto="Texto viejo del Cabildo.")
        self._antiguo(viejo, 60)
        self.client.force_login(self.archivista)
        semana = self.client.get(reverse("panel"), {"periodo": "7"})
        self.assertEqual(semana.context["ingestados"], 1)
        self.assertEqual(len(semana.context["grafica"]["serie"]), 7)
        self.assertEqual(semana.context["grafica"]["titulo"], "por día")
        trimestre = self.client.get(reverse("panel"), {"periodo": "90"})
        self.assertEqual(trimestre.context["ingestados"], 2)
        self.assertEqual(trimestre.context["grafica"]["titulo"], "por semana")
        anio = self.client.get(reverse("panel"), {"periodo": "365"})
        self.assertEqual(anio.context["grafica"]["titulo"], "por mes")
        self.assertContains(anio, 'aria-current="true">Último año')
        self.assertEqual(self.client.get(reverse("panel"), {"periodo": "raro"}).context["periodo"], "30")

    def test_porcentaje_validado_del_periodo(self):
        a, _ = self.documento(nombre="A")
        self.documento(nombre="B", archivo="b.txt", texto="Otro texto.")
        a.publicado = True
        a.fecha_publicacion = timezone.now()
        a.save()
        self.assertEqual(indicadores.porcentaje_validado("30"), {"total": 2, "publicados": 1, "porcentaje": 50})

    def test_tiempo_de_revision_desde_el_fin_del_analisis(self):
        record, _ = self.documento()
        [p] = self.proponer(record, candidato())
        p.validar(self.archivista, aceptar=True)
        RelacionRiC.objects.filter(relacion_id="R027").update(fecha_validacion=timezone.now() - datetime.timedelta(hours=36))
        record.publicado = True
        record.fecha_publicacion = timezone.now()
        record.save()
        tiempos = indicadores.tiempos_de_revision("30")
        self.assertEqual(tiempos["revision"]["dias"], 1.5)  # RF-M10-03
        self.assertEqual(tiempos["revision"]["documentos"], 1)

    def test_alerta_incluye_fichas_sin_revisar_del_m6(self):
        record, _ = self.documento()
        [p] = self.proponer(record, candidato())
        p.validar(self.archivista, aceptar=True)  # ya no hay propuestas pendientes, pero la ficha espera revisión
        RelacionRiC.objects.filter(relacion_id="R027").update(fecha_validacion=timezone.now() - datetime.timedelta(days=9))
        self.assertIn(record.pk, indicadores.esperando_revision())
        [alerta] = indicadores.atrasados(7)
        self.assertEqual(alerta["record"], record)
        self.assertEqual(alerta["dias"], 9)
        config = ConfiguracionSistema.actual()
        config.dias_limite_revision = 10
        config.save()
        self.assertEqual(indicadores.atrasados(10), [])

    def test_publicado_no_cuenta_como_pendiente(self):
        record, _ = self.documento()
        [p] = self.proponer(record, candidato())
        p.validar(self.archivista, aceptar=True)
        record.publicado = True
        record.save()
        self.assertNotIn(record.pk, indicadores.esperando_revision())

    def test_cada_indicador_lleva_a_la_lista_que_lo_compone(self):
        pendiente, _ = self.documento(nombre="Pendiente")
        self.proponer(pendiente, candidato())
        publicado, _ = self.documento(nombre="Publicado", archivo="p.txt", texto="Otro documento.")
        publicado.publicado = True
        publicado.fecha_publicacion = timezone.now()
        publicado.save()
        self.client.force_login(self.archivista)
        panel = self.client.get(reverse("panel"))
        for filtro in ("ingestados", "validados", "publicados", "pendientes"):
            self.assertContains(panel, f"?filtro={filtro}")
        lista = self.client.get(reverse("revision_lista"), {"filtro": "pendientes"})
        self.assertContains(lista, "Documentos pendientes de revisión")
        self.assertContains(lista, "<td>Pendiente</td>")
        self.assertNotContains(lista, "<td>Publicado</td>")
        lista = self.client.get(reverse("revision_lista"), {"filtro": "validados", "periodo": "7"})
        self.assertContains(lista, "<td>Publicado</td>")
        self.assertNotContains(lista, "<td>Pendiente</td>")
        self.assertContains(lista, "última semana")

    def test_las_cifras_coinciden_con_sus_listas(self):
        for i in range(3):
            self.documento(nombre=f"Doc {i}", archivo=f"d{i}.txt", texto=f"Texto número {i}.")
        self.client.force_login(self.archivista)
        cifra = self.client.get(reverse("panel"), {"periodo": "30"}).context["ingestados"]
        lista = self.client.get(reverse("revision_lista"), {"filtro": "ingestados", "periodo": "30"}).context["filas"]
        self.assertEqual(cifra, len(lista))
