"""Especificación funcional v5 · alineación con RiC-CM 1.0: el motor de
análisis como Mecanismo (E13) trazable, nombres alternativos y fecha de
expedición desde el motor, y las categorías amplias de relación."""

import datetime

from django.urls import reverse

from ric import grafo, ia_prompt
from ric.models import Mechanism, Person, PropuestaRiC, Mandate

from ._ayudas import CasoModulos, ProveedorFalso, candidato


class MecanismoTest(CasoModulos):
    def test_cada_propuesta_queda_ligada_al_motor_como_agente_e13(self):
        record, _ = self.documento()
        propuestas = self.proponer(record, candidato())
        mecanismo = Mechanism.objects.get(identificador="motor:falso:0")
        self.assertEqual(propuestas[0].mecanismo, mecanismo)
        self.assertIn("Proveedor de IA «falso»", mecanismo.caracteristicas_tecnicas)
        # una segunda corrida con la misma versión reutiliza el mecanismo
        self.proponer(record, candidato(entidad_nombre="Otro"))
        self.assertEqual(Mechanism.objects.count(), 1)
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("analisis", args=[record.pk]))
        self.assertContains(resp, reverse("vocabulario_ficha", args=["mechanism", mecanismo.pk]))
        resp = self.client.get(reverse("vocabularios"), {"tipo": "mechanism"})
        self.assertContains(resp, "Motor de análisis RICORA · falso 0")


class DatosExtraTest(CasoModulos):
    def test_nombres_alternativos_y_fecha_de_expedicion_llegan_a_la_entidad(self):
        record, _ = self.documento()
        [p1] = self.proponer(record, candidato(
            entidad_tipo="E08", entidad_nombre="José Acevedo y Gómez", evidencia="José Acevedo y Gómez",
            datos_extra={"rol_en_el_documento": "firmante", "nombres_alternativos": ["J. Acevedo", "el tribuno del pueblo"]},
        ))
        p1.validar(self.archivista, aceptar=True)
        persona = Person.objects.get(nombre="José Acevedo y Gómez")
        self.assertEqual(persona.nombres_alternativos.splitlines(), ["J. Acevedo", "el tribuno del pueblo"])
        record2, _ = self.documento(nombre="Acta con norma", texto="Acta del Cabildo, conforme a la Ley 594 de 2000.", archivo="norma.txt")
        [p2] = self.proponer(record2, candidato(
            relacion_id="R062", entidad_tipo="E17", entidad_nombre="Ley 594 de 2000", evidencia="Ley 594 de 2000",
            datos_extra={"tipo_norma": "externa", "fecha_expedicion": "2000-07-14"},
        ))
        p2.validar(self.archivista, aceptar=True)
        ley = Mandate.objects.get(nombre="Ley 594 de 2000")
        self.assertEqual(ley.fecha_expedicion, datetime.date(2000, 7, 14))
        self.assertEqual(ley.tipo_mandato, "externa")

    def test_el_prompt_explica_cuando_usar_cargo_y_pide_alternativos(self):
        record, _ = self.documento()
        instrucciones = ia_prompt.construir_instrucciones(record, "texto")
        self.assertIn("Usa E12 cargo solo cuando", instrucciones)
        self.assertIn("nombres_alternativos", instrucciones)
        self.assertIn("Nunca propongas E13 mecanismo", instrucciones)


class RdfNombresTest(CasoModulos):
    def test_nombres_alternativos_como_rico_name(self):
        from rdflib import Namespace, URIRef

        from ric import rdf as rdf_ric

        persona = Person.objects.create(nombre="José Acevedo y Gómez", nombres_alternativos="J. Acevedo\nel tribuno del pueblo")
        g = rdf_ric.grafo_de_entidad(persona, "https://ricora.example/")
        RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")
        nombres = list(g.objects(None, RICO.hasOrHadName))
        self.assertEqual(len(nombres), 2)
        valores = {str(g.value(n, RICO.textualValue)) for n in nombres}
        self.assertEqual(valores, {"J. Acevedo", "el tribuno del pueblo"})
        self.assertTrue(all((n, None, RICO.Name) in g for n in nombres))


class CategoriasTest(CasoModulos):
    def test_categorias_amplias_de_la_especificacion(self):
        self.assertEqual(grafo.categoria_relacion("R027"), "procedencia")
        self.assertEqual(grafo.categoria_relacion("R039"), "custodia")  # is or was holder of
        self.assertEqual(grafo.categoria_relacion("R080"), "temporal")
        self.assertEqual(grafo.categoria_relacion("R024"), "inclusion")
        self.assertEqual(grafo.categoria_relacion("R075"), "espacial")  # is or was location of
        self.assertEqual(grafo.categoria_relacion("R076"), "espacial")  # jurisdiction
        self.assertEqual(grafo.categoria_relacion("R035"), "identidad")  # functionally equivalent
        self.assertEqual(grafo.categoria_relacion("R019"), "asociacion")
        self.assertEqual(set(grafo.CATEGORIAS), {"procedencia", "custodia", "temporal", "inclusion", "espacial", "identidad", "asociacion"})
