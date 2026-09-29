"""Pruebas de la proyección RDF del grafo validado (T050): que use las
URIs de RiC-O 1.1 verificadas, que solo incluya relaciones ya validadas,
y que el endpoint HTTP sirva el archivo con el content-type correcto.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rdflib import RDF, Graph, Literal, URIRef

from ric import rdf
from ric.models import CorporateBody, Record, RelacionRiC

BASE = "https://mazuca.test/ric/entidad/"


class GrafoDeEntidadTest(TestCase):
    def setUp(self):
        self.record = Record.objects.create(nombre="Acta del Cabildo")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")

    def test_entidad_sin_relaciones_solo_tiene_su_propio_tipo_y_nombre(self):
        g = rdf.grafo_de_entidad(self.record, BASE)
        sujeto = URIRef(f"{BASE}record/{self.record.pk}")
        self.assertIn((sujeto, RDF.type, rdf.RICO.Record), g)
        self.assertIn((sujeto, rdf.RICO.name, Literal("Acta del Cabildo")), g)

    def test_solo_incluye_relaciones_ya_validadas(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.PENDIENTE,
        )
        g = rdf.grafo_de_entidad(self.record, BASE)
        sujeto_record = URIRef(f"{BASE}record/{self.record.pk}")
        sujeto_cabildo = URIRef(f"{BASE}corporatebody/{self.cabildo.pk}")
        self.assertNotIn((sujeto_record, rdf.RICO.hasCreator, sujeto_cabildo), g)

    def test_incluye_relacion_aceptada_con_la_uri_rico_verificada(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )
        g = rdf.grafo_de_entidad(self.record, BASE)
        sujeto_record = URIRef(f"{BASE}record/{self.record.pk}")
        sujeto_cabildo = URIRef(f"{BASE}corporatebody/{self.cabildo.pk}")
        self.assertIn((sujeto_record, rdf.RICO.hasCreator, sujeto_cabildo), g)
        self.assertIn((sujeto_cabildo, RDF.type, rdf.RICO.CorporateBody), g)

    def test_grafo_completo_incluye_relaciones_modificadas(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.MODIFICADA,
        )
        g = rdf.grafo_completo(BASE)
        self.assertEqual(len(list(g.subjects(RDF.type, rdf.RICO.CorporateBody))), 1)

    def test_serializa_a_turtle_sin_errores(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )
        g = rdf.grafo_de_entidad(self.record, BASE)
        texto = g.serialize(format="turtle")
        self.assertIn("hasCreator", texto)
        # se puede volver a parsear: es Turtle válido
        Graph().parse(data=texto, format="turtle")


class InversaDeLaRelacionTest(TestCase):
    """F09 (motor de reglas: dominio/rango + inversas): la matriz verificada
    trae la propiedad inversa de RiC-O de cada relación, pero antes de esto
    nunca se usaba — quien consultara "¿de qué es creador este Cabildo?"
    (el lado inverso de R027) no encontraba nada en el RDF exportado."""

    def setUp(self):
        self.record = Record.objects.create(nombre="Acta del Cabildo")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")

    def test_incluye_el_triple_inverso_de_una_relacion_aceptada(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )
        g = rdf.grafo_de_entidad(self.record, BASE)
        sujeto_record = URIRef(f"{BASE}record/{self.record.pk}")
        sujeto_cabildo = URIRef(f"{BASE}corporatebody/{self.cabildo.pk}")
        # R027 "has creator" -> inversa "is creator of"
        self.assertIn((sujeto_cabildo, rdf.RICO.isCreatorOf, sujeto_record), g)

    def test_no_incluye_la_inversa_de_una_relacion_pendiente(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.PENDIENTE,
        )
        g = rdf.grafo_de_entidad(self.record, BASE)
        sujeto_record = URIRef(f"{BASE}record/{self.record.pk}")
        sujeto_cabildo = URIRef(f"{BASE}corporatebody/{self.cabildo.pk}")
        self.assertNotIn((sujeto_cabildo, rdf.RICO.isCreatorOf, sujeto_record), g)

    def test_relacion_sin_inversa_documentada_no_falla(self):
        # R001 "is related to" es simétrica: la matriz no le documenta una
        # inversa distinta. No debe reventar, solo no agregar nada extra.
        from ric.models import Person

        persona = Person.objects.create(nombre="Alguien")
        RelacionRiC.objects.create(
            relacion_id="R001", origen=self.record, destino=persona,
            estado=RelacionRiC.Estado.ACEPTADA,
        )
        g = rdf.grafo_de_entidad(self.record, BASE)
        sujeto_record = URIRef(f"{BASE}record/{self.record.pk}")
        sujeto_persona = URIRef(f"{BASE}person/{persona.pk}")
        self.assertIn((sujeto_record, rdf.RICO.isRelatedTo, sujeto_persona), g)

    def test_grafo_completo_tambien_incluye_la_inversa(self):
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.MODIFICADA,
        )
        g = rdf.grafo_completo(BASE)
        sujeto_record = URIRef(f"{BASE}record/{self.record.pk}")
        sujeto_cabildo = URIRef(f"{BASE}corporatebody/{self.cabildo.pk}")
        self.assertIn((sujeto_cabildo, rdf.RICO.isCreatorOf, sujeto_record), g)


class EntidadesSinRelacionesEnElGrafoCompletoTest(TestCase):
    """F12 (auditoría): una entidad ya guardada (por ingesta o creada a
    mano) debe aparecer en el RDF completo / SPARQL desde que existe, no
    solo cuando ya tiene alguna relación validada. Antes de esto,
    grafo_completo() solo recorría RelacionRiC, así que un Record recién
    ingerido sin ninguna propuesta todavía validada era invisible."""

    def test_un_record_sin_ninguna_relacion_aparece_igual(self):
        from ric.models import Person

        aislado = Record.objects.create(nombre="Acta sin relaciones todavía")
        Person.objects.create(nombre="Alguien sin relaciones todavía")
        g = rdf.grafo_completo(BASE)
        sujeto = URIRef(f"{BASE}record/{aislado.pk}")
        self.assertIn((sujeto, RDF.type, rdf.RICO.Record), g)
        self.assertIn((sujeto, rdf.RICO.name, Literal("Acta sin relaciones todavía")), g)

    def test_un_corporatebody_no_aparece_tambien_como_group(self):
        # herencia multitabla: CorporateBody(Group) tiene fila también en
        # la tabla de Group — sin excluirla, aparecería dos veces, una con
        # el tipo RDF correcto (CorporateBody) y otra con el equivocado
        # (Group, heredado por accidente del recorrido "por tipo").
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé (aislado)")
        g = rdf.grafo_completo(BASE)
        sujeto = URIRef(f"{BASE}corporatebody/{cabildo.pk}")
        self.assertIn((sujeto, RDF.type, rdf.RICO.CorporateBody), g)
        self.assertNotIn((sujeto, RDF.type, rdf.RICO.Group), g)

    def test_una_entidad_sin_relaciones_no_esta_en_el_grafo_de_otra_entidad(self):
        # grafo_de_entidad() sigue siendo "el vecindario a un salto" — no
        # debe traer entidades sueltas que no tengan nada que ver.
        entidad = Record.objects.create(nombre="Acta principal")
        Record.objects.create(nombre="Acta completamente aparte")
        g = rdf.grafo_de_entidad(entidad, BASE)
        self.assertEqual(len(list(g.subjects(RDF.type, rdf.RICO.Record))), 1)


class ExportarRdfViewTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta del Cabildo")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        RelacionRiC.objects.create(
            relacion_id="R027", origen=self.record, destino=self.cabildo,
            estado=RelacionRiC.Estado.ACEPTADA,
        )

    def test_requiere_login(self):
        resp = self.client.get(reverse("ric_exportar_rdf", args=["record", self.record.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_sirve_turtle_por_defecto(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_exportar_rdf", args=["record", self.record.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/turtle; charset=utf-8")
        self.assertIn(b"hasCreator", resp.content)

    def test_sirve_rdf_xml_si_se_pide(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_exportar_rdf", args=["record", self.record.pk]), {"formato": "xml"})
        self.assertEqual(resp["Content-Type"], "application/rdf+xml; charset=utf-8")

    def test_tipo_desconocido_404(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_exportar_rdf", args=["noexiste", 1]))
        self.assertEqual(resp.status_code, 404)

    def test_grafo_completo_sirve_turtle(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_exportar_rdf_completo"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"hasCreator", resp.content)
