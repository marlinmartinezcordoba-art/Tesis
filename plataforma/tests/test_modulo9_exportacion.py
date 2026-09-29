"""Módulo 9 · Exportación e interoperabilidad (historia de usuario 9):
documentos precargados desde el catálogo (RF-M9-02), archivo válido en
RiC-O, JSON-LD o CSV verificado antes de entregarlo (RF-M9-01), generación
en la cola con avance y registro de formato, alcance y quién la pidió
(RF-M9-03), con huella, auditoría e historial de cada documento."""

import csv
import io
import json
from unittest.mock import patch

from django.urls import reverse
from rdflib import Graph
from rdflib.namespace import RDF

from ric import exportacion, rdf
from ric.models import EventoRiC, Exportacion, Instantiation, RegistroAuditoria

from ._ayudas import CasoModulos, candidato


class ExportacionTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.record, self.inst = self.documento(nombre="Acta del Cabildo")
        [p] = self.proponer(self.record, candidato())
        p.validar(self.archivista, aceptar=True)
        self.otro, _ = self.documento(nombre="Oficio 12", archivo="oficio.txt", texto="Oficio del Cabildo de Santafé.")
        self.client.force_login(self.archivista)

    def _exportar(self, formato, *records):
        resp = self.client.post(reverse("exportar"), {"formato": formato, "doc": [r.pk for r in (records or (self.record,))]})
        return Exportacion.objects.latest("pk"), resp

    def test_precarga_desde_el_catalogo(self):
        resp = self.client.get(reverse("exportar"), {"doc": [self.record.pk]})
        self.assertContains(resp, f'value="{self.record.pk}" checked> Acta del Cabildo <small>(desde el catálogo)</small>')
        self.assertContains(resp, "1 precargado(s) desde el catálogo")

    def test_rdf_valido_verificado_con_huella(self):
        exp, resp = self._exportar("rdf", self.record, self.otro)
        self.assertRedirects(resp, f"/exportar/?listo={exp.pk}", fetch_redirect_response=False)
        self.assertEqual(exp.estado, Exportacion.Estado.LISTA)
        self.assertIn("Conforme con la ontología RiC-O 1.1", exp.mensaje)
        g = Graph().parse(data=exp.archivo.open("rb").read().decode(), format="turtle")
        self.assertGreaterEqual(len(set(g.subjects(RDF.type, rdf.RICO.Record))), 2)
        self.assertTrue(list(g.triples((None, rdf.RICO.hasCreator, None))))
        self.assertEqual(len(exp.sha256), 64)
        self.assertGreater(exp.tamano_bytes, 0)

    def test_json_ld_valido_y_legible_con_contexto(self):
        exp, _ = self._exportar("json-ld")
        texto = exp.archivo.open("rb").read().decode()
        datos = json.loads(texto)
        self.assertEqual(datos["@context"]["rico"], str(rdf.RICO))
        self.assertIn("rico:hasCreator", texto)
        self.assertTrue(len(Graph().parse(data=texto, format="json-ld")) > 0)

    def test_csv_tabular_con_revision_y_bom_para_excel(self):
        exp, _ = self._exportar("csv", self.record, self.otro)
        crudo = exp.archivo.open("rb").read().decode("utf-8")
        self.assertTrue(crudo.startswith("﻿"))
        filas = list(csv.reader(io.StringIO(crudo.lstrip("﻿"))))
        self.assertEqual(filas[0], exportacion.COLUMNAS_CSV)
        self.assertIn("Pendiente de revisión", crudo)
        self.assertIn("sin relaciones validadas", crudo)  # el oficio sin relaciones también aparece
        self.assertIn("Archivo verificado: CSV", exp.mensaje)

    def test_registro_con_formato_alcance_y_quien(self):
        exp, _ = self._exportar("csv", self.record, self.otro)
        self.assertEqual(exp.usuario, self.archivista)
        self.assertEqual(exp.alcance, "2 documento(s): Acta del Cabildo, Oficio 12")
        resp = self.client.get(reverse("exportar"))
        self.assertContains(resp, "2 documento(s): Acta del Cabildo, Oficio 12")
        self.assertContains(resp, "CSV (tabular)")
        self.assertContains(resp, "archivista")

    def test_queda_en_auditoria_y_en_el_historial_de_cada_documento(self):
        exp, _ = self._exportar("rdf")
        self.assertTrue(RegistroAuditoria.objects.filter(accion="exportar", usuario=self.archivista, detalle__exportacion=exp.pk).exists())
        self.assertTrue(EventoRiC.objects.filter(instanciacion=self.inst, tipo=EventoRiC.Tipo.EXPORTACION, detalle__exportacion=exp.pk).exists())

    def test_avance_y_descarga(self):
        exp, _ = self._exportar("rdf")
        estado = self.client.get(reverse("exportar_estado", args=[exp.pk])).json()
        self.assertEqual((estado["estado"], estado["progreso"]), ("lista", 100))
        self.assertEqual(estado["descargar"], reverse("exportar_descargar", args=[exp.pk]))
        resp = self.client.get(reverse("exportar_descargar", args=[exp.pk]))
        self.assertEqual(resp["Content-Type"], "text/turtle; charset=utf-8")

    def test_en_curso_no_se_descarga_y_muestra_la_barra(self):
        exp = exportacion.solicitar([self.record], "rdf", self.archivista)
        resp = self.client.get(reverse("exportar"), {"listo": exp.pk})
        self.assertContains(resp, "Generando la exportación")
        self.assertContains(resp, 'id="exp-barra"')
        resp = self.client.get(reverse("exportar_descargar", args=[exp.pk]), follow=True)
        self.assertContains(resp, "todavía no está lista")

    def test_archivo_invalido_no_se_entrega(self):
        with patch("ric.exportacion._csv_lote", return_value="encabezado,roto\n"):
            exp, _ = self._exportar("csv")
        exp.refresh_from_db()
        self.assertEqual(exp.estado, Exportacion.Estado.ERROR)
        self.assertIn("No se generó la exportación", exp.mensaje)
        self.assertFalse(exp.archivo)

    def test_sin_cola_disponible_se_genera_igual(self):
        with patch("ric.tasks.generar_exportacion.delay", side_effect=ConnectionError("redis caído")):
            exp, _ = self._exportar("rdf")
        exp.refresh_from_db()
        self.assertEqual(exp.estado, Exportacion.Estado.LISTA)

    def test_consulta_solo_exporta_lo_visible_y_solo_ve_sus_exportaciones(self):
        self.record.publicado = True
        self.record.save()
        ajena, _ = self._exportar("rdf")
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("exportar"), {"formato": "csv", "doc": [self.record.pk, self.otro.pk]})
        exp = Exportacion.objects.latest("pk")
        self.assertEqual(exp.documentos, [self.record.pk])  # el oficio sin publicar se descarta
        self.assertEqual(self.client.get(reverse("exportar_descargar", args=[ajena.pk])).status_code, 404)
        Instantiation.objects.filter(pk=self.inst.pk).update(condicion_acceso=Instantiation.CondicionAcceso.RESERVADO)
        resp = self.client.post(reverse("exportar"), {"formato": "csv", "doc": [self.record.pk]}, follow=True)
        self.assertContains(resp, "Seleccione al menos un documento")
