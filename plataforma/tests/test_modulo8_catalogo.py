"""Módulo 8 · Catálogo y consulta (historia de usuario 8): búsqueda por
texto libre y filtro de clase combinados (RF-M8-01), sin distinguir tildes
y por nombres alternativos; de la entidad a sus documentos y del documento
a sus entidades (RF-M8-02/03); y sobre todo RF-M8-04: el rol consulta no ve
nada que solo aparezca en documentos sin publicar o reservados — ni en el
catálogo, ni en sugerencias, fichas, grafo, RDF, SPARQL o vocabularios."""

import json

from django.urls import reverse

from ric.models import Instantiation, Person, RecordSet

from ._ayudas import CasoModulos, candidato


class CatalogoTest(CasoModulos):
    def setUp(self):
        super().setUp()
        # Documento publicado y abierto, con una persona
        self.publico, _ = self.documento(nombre="Acta pública", archivo="publica.txt",
                                         texto="Acta firmada por José Acevedo y Gómez en Bogotá, 1810.")
        [p] = self.proponer(self.publico, candidato(entidad_nombre="José Acevedo y Gómez", entidad_tipo="E08", evidencia="José Acevedo y Gómez"))
        p.validar(self.archivista, aceptar=True)
        self.persona_publica = Person.objects.get(nombre="José Acevedo y Gómez")
        self.persona_publica.nombres_alternativos = "J. Acevedo"
        self.persona_publica.save()
        self.publico.publicado = True
        self.publico.save()
        # Documento publicado pero RESERVADO, con otra persona que solo aparece ahí
        self.reservado, inst = self.documento(nombre="Historia clínica reservada", archivo="reservado.txt",
                                              texto="Paciente Camilo Torres Tenorio, diagnóstico reservado.")
        [p2] = self.proponer(self.reservado, candidato(entidad_nombre="Camilo Torres Tenorio", entidad_tipo="E08", evidencia="Camilo Torres Tenorio"))
        p2.validar(self.archivista, aceptar=True)
        self.persona_oculta = Person.objects.get(nombre="Camilo Torres Tenorio")
        self.reservado.publicado = True
        self.reservado.save()
        Instantiation.objects.filter(pk=inst.pk).update(condicion_acceso=Instantiation.CondicionAcceso.RESERVADO)

    # --- RF-M8-01 ---------------------------------------------------------
    def test_texto_libre_y_clase_combinados(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("catalogo"), {"q": "Acevedo", "clase": "agente"})
        self.assertContains(resp, "José Acevedo y Gómez")
        self.assertNotContains(resp, "Acta pública</a>")  # la clase «agente» excluye documentos
        resp = self.client.get(reverse("catalogo"), {"q": "Acevedo", "clase": "documento"})
        self.assertContains(resp, "Acta pública")
        self.assertNotContains(resp, "◉ ")  # ninguna tarjeta de entidad

    def test_busqueda_sin_tildes_y_por_nombre_alternativo(self):
        self.client.force_login(self.archivista)
        self.assertContains(self.client.get(reverse("catalogo"), {"q": "jose acevedo"}), "José Acevedo y Gómez")
        self.assertContains(self.client.get(reverse("catalogo"), {"q": "J. Acevedo", "clase": "agente"}), "José Acevedo y Gómez")
        sugerencias = self.client.get(reverse("catalogo_sugerencias"), {"q": "gomez"}).json()["sugerencias"]
        self.assertIn("José Acevedo y Gómez", sugerencias)

    def test_paginacion(self):
        for i in range(30):
            Person.objects.create(nombre=f"Persona de prueba {i:02d}")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("catalogo"), {"clase": "agente"})
        self.assertContains(resp, "página 1 de 2")
        self.assertContains(resp, "clase=agente&pagina=2")

    # --- RF-M8-02 / 03 ----------------------------------------------------
    def test_de_la_entidad_a_sus_documentos_y_del_documento_a_sus_entidades(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("catalogo_ficha", args=["person", self.persona_publica.pk]))
        self.assertContains(resp, reverse("catalogo_ficha", args=["record", self.publico.pk]))
        resp = self.client.get(reverse("catalogo_ficha", args=["record", self.publico.pk]))
        self.assertContains(resp, reverse("catalogo_ficha", args=["person", self.persona_publica.pk]))
        self.assertContains(resp, "Ver en grafo")

    # --- RF-M8-04: rol consulta ------------------------------------------
    def test_consulta_no_ve_lo_reservado_en_el_catalogo_ni_en_sugerencias(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("catalogo"), {"q": "Torres"})
        self.assertNotContains(resp, "Camilo Torres Tenorio")
        self.assertNotContains(resp, "Historia clínica reservada")
        resp = self.client.get(reverse("catalogo"), {"clase": "agente"})
        self.assertContains(resp, "José Acevedo y Gómez")
        self.assertNotContains(resp, "Camilo Torres Tenorio")
        self.assertEqual(self.client.get(reverse("catalogo_sugerencias"), {"q": "Camilo"}).json()["sugerencias"], [])

    def test_consulta_no_abre_la_ficha_de_lo_reservado(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("catalogo_ficha", args=["person", self.persona_oculta.pk]), follow=True)
        self.assertContains(resp, "no está disponible para consulta")
        resp = self.client.get(reverse("catalogo_ficha", args=["record", self.reservado.pk]), follow=True)
        self.assertContains(resp, "no está disponible para consulta")

    def test_consulta_no_ve_lo_reservado_en_grafo_ni_rdf(self):
        self.client.force_login(self.consulta)
        self.assertEqual(self.client.get(reverse("ric_grafo", args=["person", self.persona_oculta.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("ric_grafo_datos", args=["record", self.reservado.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("ric_exportar_rdf", args=["record", self.reservado.pk])).status_code, 404)
        completo = self.client.get(reverse("ric_exportar_rdf_completo")).content.decode()
        self.assertIn("José Acevedo y Gómez", completo)
        self.assertNotIn("Camilo Torres Tenorio", completo)
        self.assertNotIn("Historia clínica reservada", completo)
        datos = self.client.get(reverse("ric_grafo_datos", args=["person", self.persona_publica.pk])).json()
        etiquetas = json.dumps(datos, ensure_ascii=False)
        self.assertNotIn("Historia clínica reservada", etiquetas)

    def test_consulta_no_ve_lo_reservado_por_sparql(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("ric_sparql_endpoint"), {"query": "SELECT ?o WHERE { ?s ?p ?o }"})
        texto = json.dumps(resp.json(), ensure_ascii=False)
        self.assertIn("José Acevedo y Gómez", texto)
        self.assertNotIn("Camilo Torres Tenorio", texto)

    def test_consulta_no_ve_lo_reservado_en_vocabularios(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("vocabularios"), {"tipo": "person"})
        self.assertContains(resp, "José Acevedo y Gómez")
        self.assertNotContains(resp, "Camilo Torres Tenorio")
        resp = self.client.get(reverse("vocabulario_ficha", args=["person", self.persona_oculta.pk]), follow=True)
        self.assertContains(resp, "no está disponible para consulta")

    def test_expediente_sin_documentos_visibles_no_se_ve_y_el_visible_no_lista_lo_oculto(self):
        exp_oculto = RecordSet.objects.create(nombre="Expediente de Camilo Torres", tipo_conjunto=RecordSet.Tipo.EXPEDIENTE)
        self.reservado.record_set = exp_oculto
        self.reservado.save()
        exp_visible = RecordSet.objects.create(nombre="Actas 1810", tipo_conjunto=RecordSet.Tipo.EXPEDIENTE)
        self.publico.record_set = exp_visible
        self.publico.save()
        borrador, _ = self.documento(nombre="Borrador sin publicar", archivo="borrador.txt", texto="Borrador interno.")
        borrador.record_set = exp_visible
        borrador.save()
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("catalogo_ficha", args=["recordset", exp_oculto.pk]), follow=True)
        self.assertContains(resp, "no está disponible para consulta")
        resp = self.client.get(reverse("catalogo_ficha", args=["recordset", exp_visible.pk]))
        self.assertContains(resp, "Acta pública")
        self.assertNotContains(resp, "Borrador sin publicar")

    def test_archivista_ve_todo(self):
        self.client.force_login(self.archivista)
        self.assertContains(self.client.get(reverse("catalogo"), {"q": "Torres"}), "Camilo Torres Tenorio")
        self.assertEqual(self.client.get(reverse("ric_grafo", args=["person", self.persona_oculta.pk])).status_code, 200)
