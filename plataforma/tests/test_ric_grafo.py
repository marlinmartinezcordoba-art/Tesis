"""Pruebas del subgrafo navegable para Cytoscape.js (T052): nodos/aristas
correctos y el endpoint HTML + JSON."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ric import grafo
from ric.models import CorporateBody, Record, RelacionRiC


class SubgrafoJsonTest(TestCase):
    def setUp(self):
        self.record = Record.objects.create(nombre="Acta del Cabildo")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")

    def test_entidad_sola_es_un_nodo_central_sin_aristas(self):
        datos = grafo.subgrafo_json(self.record)
        self.assertEqual(len(datos["nodes"]), 1)
        self.assertEqual(datos["nodes"][0]["data"]["central"], True)
        self.assertEqual(datos["edges"], [])

    def test_relacion_pendiente_no_aparece(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.PENDIENTE,
        )
        datos = grafo.subgrafo_json(self.record)
        self.assertEqual(len(datos["nodes"]), 1)
        self.assertEqual(datos["edges"], [])

    def test_relacion_aceptada_agrega_nodo_y_arista_con_etiqueta_verificada(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )
        datos = grafo.subgrafo_json(self.record)
        self.assertEqual(len(datos["nodes"]), 2)
        self.assertEqual(len(datos["edges"]), 1)
        arista = datos["edges"][0]
        self.assertEqual(arista["data"]["label"], "has creator")
        ids = {n["data"]["id"] for n in datos["nodes"]}
        self.assertEqual(arista["data"]["source"], f"Record:{self.record.pk}")
        self.assertEqual(arista["data"]["target"], f"CorporateBody:{self.cabildo.pk}")
        self.assertIn(f"Record:{self.record.pk}", ids)
        self.assertIn(f"CorporateBody:{self.cabildo.pk}", ids)

    def test_subgrafo_desde_el_destino_tambien_ve_la_relacion(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )
        datos = grafo.subgrafo_json(self.cabildo)
        self.assertEqual(len(datos["edges"]), 1)


class GrafoViewsTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta del Cabildo")

    def test_requiere_login(self):
        resp = self.client.get(reverse("ric_grafo", args=["record", self.record.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_pagina_html_carga(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_grafo", args=["record", self.record.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cytoscape")

    def test_datos_json(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_grafo_datos", args=["record", self.record.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["nodes"][0]["data"]["tipo"], "Record")
