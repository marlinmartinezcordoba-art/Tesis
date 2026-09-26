"""Pruebas del endpoint SPARQL controlado (T051): solo lectura, sobre el
grafo ya validado, con las URIs de RiC-O verificadas."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ric import sparql
from ric.models import CorporateBody, Record, RelacionRiC

BASE = "https://mazuca.test/ric/entidad/"


class EjecutarSparqlTest(TestCase):
    def setUp(self):
        self.record = Record.objects.create(nombre="Acta del Cabildo")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )

    def test_select_devuelve_las_filas_esperadas(self):
        resultado = sparql.ejecutar(
            "PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\n"
            "SELECT ?nombre WHERE { ?s rico:name ?nombre }",
            BASE,
        )
        nombres = {fila["nombre"]["value"] for fila in resultado["results"]["bindings"]}
        self.assertEqual(nombres, {"Acta del Cabildo", "Cabildo de Santafé"})

    def test_ask_devuelve_booleano(self):
        resultado = sparql.ejecutar(
            "PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>\n"
            "ASK { ?s a rico:CorporateBody }",
            BASE,
        )
        self.assertEqual(resultado, {"head": {}, "boolean": True})

    def test_sintaxis_invalida_lanza_error_sparql(self):
        with self.assertRaises(sparql.ErrorSparql):
            sparql.ejecutar("SELECT ?s WHERE { ?s ?p", BASE)

    def test_insert_no_se_puede_ejecutar(self):
        with self.assertRaises(sparql.ErrorSparql):
            sparql.ejecutar("INSERT DATA { <urn:x> <urn:y> <urn:z> }", BASE)


class SparqlEndpointViewTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta del Cabildo")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )

    def test_requiere_login(self):
        resp = self.client.post(reverse("ric_sparql_endpoint"), {"query": "SELECT * WHERE {?s ?p ?o}"})
        self.assertEqual(resp.status_code, 302)

    def test_get_no_permitido(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_sparql_endpoint"))
        self.assertEqual(resp.status_code, 405)

    def test_consulta_de_ejemplo_devuelve_resultados_correctos(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ric_sparql_endpoint"), {
            "query": "PREFIX rico: <https://www.ica.org/standards/RiC/ontology#> "
                     "SELECT ?nombre WHERE { ?s rico:name ?nombre }",
        })
        self.assertEqual(resp.status_code, 200)
        datos = resp.json()
        nombres = {fila["nombre"]["value"] for fila in datos["results"]["bindings"]}
        self.assertEqual(nombres, {"Acta del Cabildo", "Cabildo de Santafé"})

    def test_consulta_vacia_400(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ric_sparql_endpoint"), {"query": ""})
        self.assertEqual(resp.status_code, 400)

    def test_consulta_invalida_400_con_mensaje(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("ric_sparql_endpoint"), {"query": "no es sparql"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_pagina_html_carga(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_sparql"))
        self.assertEqual(resp.status_code, 200)
