"""Conformidad de lo que RICORA exporta con la ontología oficial RiC-O 1.1
(ric/ontologia/RiC-O_1-1.rdf): atributos de tipo como individuos de su
clase, una sola URI por entidad con su clase precisa, URI que se abren y
verificación en cada exportación."""

from django.test import override_settings
from django.urls import reverse
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from ric import conformidad, rdf, reglas
from ric.models import (
    Activity, CorporateBody, Date, FormaDocumental, Instantiation, Mandate, Person, Place, Position, Record,
    RecordResource, RecordSet, RelacionRiC,
)

from ._ayudas import CasoModulos

BASE = "https://ricora.test/ric/entidad/"
R = conformidad.RICO


def _relacion(rid, origen, destino):
    return RelacionRiC.objects.create(relacion_id=rid, origen=origen, destino=destino, estado=RelacionRiC.Estado.ACEPTADA)


class OntologiaTest(CasoModulos):
    def test_la_ontologia_oficial_se_carga(self):
        onto = conformidad.ontologia()
        self.assertGreater(len(onto.clases), 100)
        self.assertIn(URIRef(R + "DocumentaryFormType"), onto.clases)
        self.assertTrue(onto.propiedades[URIRef(R + "hasCreator")].de_objeto)
        self.assertFalse(onto.propiedades[URIRef(R + "name")].de_objeto)

    def test_la_matriz_rico_existe_en_la_ontologia(self):
        onto = conformidad.ontologia()
        matriz = reglas.cargar_matriz()
        for grupo in ("entidades", "relaciones", "atributos"):
            for codigo, info in matriz[grupo].items():
                uri = URIRef(info["uri_rico"].replace("rico:", R))
                existe = uri in onto.clases if grupo == "entidades" else uri in onto.propiedades
                self.assertTrue(existe, f"{codigo} {info['uri_rico']}")

    def test_detecta_texto_donde_va_una_entidad_y_propiedades_inventadas(self):
        g = Graph()
        doc = URIRef(BASE + "record/1")
        g.add((doc, RDF.type, URIRef(R + "Record")))
        g.add((doc, URIRef(R + "hasDocumentaryFormType"), Literal("acta")))
        g.add((doc, URIRef(R + "inventada"), Literal("x")))
        g.add((doc, URIRef(R + "hasCreator"), URIRef(BASE + "place/1")))
        g.add((URIRef(BASE + "place/1"), RDF.type, URIRef(R + "Place")))
        hallazgos = " | ".join(conformidad.validar(g))
        self.assertIn("debe apuntar a una entidad", hallazgos)
        self.assertIn("rico:inventada no existe", hallazgos)
        self.assertIn("no está en el rango de rico:hasCreator", hallazgos)


class _ConDatosRic(CasoModulos):
    def setUp(self):
        super().setUp()
        self.forma = FormaDocumental.objects.create(nombre="Acta")
        self.serie = RecordSet.objects.create(nombre="Actas", tipo_conjunto="serie")
        self.doc = Record.objects.create(nombre="Acta 1", idioma="Español", tipo_forma_documental="acta")
        self.doc2 = Record.objects.create(nombre="Acta 2", forma_documental=self.forma, tipo_forma_documental="acta")
        self.inst = Instantiation.objects.create(nombre="acta1.pdf", record_resource=self.doc, tipo_soporte="Digital")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo", tipo_entidad_corporativa="Concejo municipal")
        self.persona = Person.objects.create(nombre="Juan Pérez", tipo_ocupacion="Archivista")
        self.cargo = Position.objects.create(nombre="Jefe de Archivo")
        self.funcion = Activity.objects.create(nombre="Gestión documental", tipo_actividad="Función")
        self.ley = Mandate.objects.create(nombre="Ley 594 de 2000", tipo_mandato="Ley")
        self.fecha = Date.objects.create(nombre="20 de julio de 1810", valor_normalizado="1810-07-20", tipo_fecha="creación")
        self.lugar = Place.objects.create(nombre="Santafé", tipo_lugar="Ciudad")
        _relacion("R024", self.serie, self.doc)
        _relacion("R027", self.doc, self.cabildo)
        _relacion("R079", self.doc, self.persona)
        _relacion("R054", self.persona, self.cargo)
        _relacion("R056", self.cargo, self.cabildo)
        _relacion("R060", self.funcion, self.cabildo)
        _relacion("R063", self.ley, self.funcion)
        _relacion("R033", self.doc, self.funcion)
        _relacion("R080", self.fecha, self.doc)
        # una relación guardada con la clase general (RecordResource) en vez del documento
        _relacion("R027", RecordResource.objects.get(pk=self.doc2.pk), self.cabildo)


class ExportacionConformeTest(_ConDatosRic):
    def test_todo_el_grafo_es_conforme(self):
        g = rdf.grafo_completo(BASE)
        self.assertEqual(conformidad.validar(g), [])

    def test_los_tipos_son_individuos_de_su_clase(self):
        g = rdf.grafo_completo(BASE)
        doc = URIRef(BASE + f"record/{self.doc.pk}")
        forma = g.value(doc, URIRef(R + "hasDocumentaryFormType"))
        self.assertIsInstance(forma, URIRef)
        self.assertIn((forma, RDF.type, URIRef(R + "DocumentaryFormType")), g)
        self.assertEqual(str(g.value(forma, URIRef(R + "name"))), "acta")
        idioma = g.value(doc, URIRef(R + "hasOrHadLanguage"))
        self.assertIn((idioma, RDF.type, URIRef(R + "Language")), g)
        # la forma controlada (M5) reemplaza al texto: una sola forma, la del vocabulario
        doc2 = URIRef(BASE + f"record/{self.doc2.pk}")
        self.assertEqual(list(g.objects(doc2, URIRef(R + "hasDocumentaryFormType"))), [URIRef(BASE + f"formadocumental/{self.forma.pk}")])

    def test_una_sola_uri_por_entidad_con_su_clase_precisa(self):
        g = rdf.grafo_completo(BASE)
        self.assertNotIn((URIRef(BASE + f"recordresource/{self.doc2.pk}"), None, None), g)
        self.assertIn((URIRef(BASE + f"record/{self.doc2.pk}"), URIRef(R + "hasCreator"), URIRef(BASE + f"corporatebody/{self.cabildo.pk}")), g)

    def test_comando_verificar_rico(self):
        from io import StringIO

        from django.core.management import call_command

        salida = StringIO()
        call_command("verificar_rico", stdout=salida)
        self.assertIn("Conforme con RiC-O 1.1", salida.getvalue())

    def test_la_exportacion_dice_si_es_conforme(self):
        from ric import exportacion

        g = rdf.grafo_completo(BASE)
        mensaje = exportacion.validar(g.serialize(format="turtle"), "rdf", 2)
        self.assertIn("Conforme con la ontología RiC-O 1.1", mensaje)
        malo = Graph()
        malo.add((URIRef(BASE + "record/1"), RDF.type, URIRef(R + "Record")))
        malo.add((URIRef(BASE + "record/1"), URIRef(R + "hasDocumentaryFormType"), Literal("acta")))
        self.assertIn("observación(es) de conformidad", exportacion.validar(malo.serialize(format="turtle"), "rdf", 1))


class UriQueSeAbrenTest(_ConDatosRic):
    def test_una_persona_llega_a_la_ficha_y_un_programa_recibe_rico(self):
        self.client.force_login(self.archivista)
        url = f"/ric/entidad/record/{self.doc.pk}"
        self.assertRedirects(self.client.get(url), reverse("catalogo_ficha", args=["record", self.doc.pk]), fetch_redirect_response=False)
        resp = self.client.get(url, HTTP_ACCEPT="text/turtle")
        self.assertEqual(resp["Content-Type"], "text/turtle; charset=utf-8")
        g = Graph().parse(data=resp.content.decode(), format="turtle")
        self.assertIn((URIRef(f"http://testserver{url}"), RDF.type, URIRef(R + "Record")), g)
        self.assertEqual(self.client.get(url, {"formato": "json-ld"})["Content-Type"], "application/ld+json; charset=utf-8")

    def test_la_uri_general_lleva_a_la_clase_precisa(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(f"/ric/entidad/recordresource/{self.doc2.pk}")
        self.assertRedirects(resp, reverse("catalogo_ficha", args=["record", self.doc2.pk]), fetch_redirect_response=False)

    def test_uri_de_un_tipo_y_de_la_forma_documental(self):
        self.client.force_login(self.archivista)
        resp = self.client.get("/ric/entidad/tipo/ActivityType/funcion", HTTP_ACCEPT="text/turtle")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Gestión documental", resp.content.decode())
        self.assertEqual(self.client.get("/ric/entidad/tipo/ActivityType/no-existe", HTTP_ACCEPT="text/turtle").status_code, 404)
        resp = self.client.get(f"/ric/entidad/formadocumental/{self.forma.pk}", HTTP_ACCEPT="text/turtle")
        self.assertIn("DocumentaryFormType", resp.content.decode())

    def test_sin_sesion_o_sin_permiso_no_se_ve(self):
        self.assertEqual(self.client.get(f"/ric/entidad/record/{self.doc.pk}").status_code, 302)
        self.client.force_login(self.consulta)  # el documento no está publicado
        self.assertEqual(self.client.get(f"/ric/entidad/record/{self.doc.pk}", HTTP_ACCEPT="text/turtle").status_code, 404)
