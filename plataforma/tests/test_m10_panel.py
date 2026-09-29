"""M10 · Panel de indicadores (/panel): RF-M10-01 a RF-M10-04, con datos
reales — nunca simulados."""

import datetime

from django.urls import reverse
from django.utils import timezone

from ric.models import ConfiguracionSistema, CorporateBody, PropuestaRiC, Record

from ._ayudas import CasoModulos, candidato


class PanelTest(CasoModulos):
    def test_es_la_pagina_de_inicio_y_exige_sesion(self):
        resp = self.client.get("/")
        self.assertRedirects(resp, reverse("panel"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("panel")).status_code, 302)
        resp = self.client.post(reverse("ric_login"), {"username": "archivista", "password": "x"})
        self.assertRedirects(resp, reverse("panel"))

    def test_sin_datos_dice_sin_datos(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("panel"))
        self.assertIsNone(resp.context["validado"]["porcentaje"])
        self.assertIsNone(resp.context["tiempos"]["revision"])
        self.assertEqual(len(resp.context["grafica"]["serie"]), 30)  # RF-M10-01: último mes, por día
        self.assertContains(resp, "sin publicaciones en el periodo")
        self.assertContains(resp, "Todavía no se ha subido ningún documento")

    def test_porcentaje_validado_y_tiempo_de_revision(self):
        record, inst = self.documento()
        Record.objects.create(nombre="Otro")
        record.publicado = True
        record.fecha_publicacion = timezone.now() + datetime.timedelta(hours=48)
        record.save()
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("panel"))
        self.assertEqual(resp.context["validado"]["porcentaje"], 50)  # RF-M10-02
        self.assertEqual(resp.context["tiempos"]["ciclo"]["dias"], 2.0)  # ciclo completo carga → publicación
        self.assertEqual(resp.context["grafica"]["serie"][-1]["total"], 2)

    def test_alerta_de_revision_atrasada_con_limite_configurable(self):
        record, inst = self.documento()
        [p] = self.proponer(record, candidato())
        PropuestaRiC.objects.filter(pk=p.pk).update(fecha_creacion=timezone.now() - datetime.timedelta(days=10))
        self.client.force_login(self.revisor)
        resp = self.client.get(reverse("panel"))
        self.assertEqual(len(resp.context["alertas"]), 1)  # RF-M10-04
        self.assertContains(resp, "llevan más de 7 días esperando revisión")
        self.assertContains(resp, reverse("revision_lista") + "?filtro=atrasados")
        config = ConfiguracionSistema.actual()
        config.dias_limite_revision = 30
        config.save()
        resp = self.client.get(reverse("panel"))
        self.assertEqual(len(resp.context["alertas"]), 0)

    def test_documentos_en_curso_reemplazan_la_bandeja(self):
        record, inst = self.documento()
        self.proponer(record, candidato())
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("panel"))
        self.assertContains(resp, "Documentos en curso")
        self.assertContains(resp, "Decidir propuestas")

    def test_distribucion_cuenta_agentes_una_sola_vez(self):
        Record.objects.create(nombre="Acta")
        CorporateBody.objects.create(nombre="Cabildo")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("panel"))
        distribucion = {f["tipo"]: f["total"] for f in resp.context["distribucion"]}
        self.assertEqual(distribucion["Agent"], 1)
        self.assertEqual(resp.context["total_entidades"], 2)

    def test_consulta_ve_un_panel_reducido(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("panel"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("distribucion", resp.context)
        self.assertNotContains(resp, "Ingesta por día")
        self.assertNotContains(resp, "?filtro=")  # las cifras no enlazan a listas de trabajo interno
        self.assertContains(resp, "Consulta y exportación")
