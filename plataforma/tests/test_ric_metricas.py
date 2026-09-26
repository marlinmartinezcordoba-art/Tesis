"""Pruebas del laboratorio de evaluación (T070): que las métricas
calculables devuelvan números reales, y que las que todavía no se pueden
calcular queden explícitamente marcadas como pendientes (nunca inventadas)."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ric import metricas
from ric.auditoria import MuestraRiC
from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import CorporateBody, Evidencia, Instantiation, PropuestaRiC, Record, RelacionRiC
from ric.proveedores import PropuestaCandidata, ProveedorIA, generar_propuestas

MEDIA = tempfile.mkdtemp()


class ProveedorFalso(ProveedorIA):
    nombre, version = "falso", "0"

    def __init__(self, candidatos):
        self._candidatos = candidatos

    def proponer(self, record, texto):
        return self._candidatos


def _por_codigo(lista):
    return {m["codigo"]: m for m in lista}


class MetricasSinDatosTest(TestCase):
    def test_todas_las_pendientes_traen_una_nota(self):
        resultado = _por_codigo(metricas.calcular_metricas())
        for codigo in ("M01", "M02", "M03", "M07", "M08", "M09", "M12", "M13", "M14"):
            self.assertIsNone(resultado[codigo]["valor"], codigo)
            self.assertTrue(resultado[codigo]["nota"], codigo)

    def test_catorce_metricas_con_los_codigos_esperados(self):
        resultado = _por_codigo(metricas.calcular_metricas())
        self.assertEqual(set(resultado), {f"M{i:02d}" for i in range(1, 15)})

    def test_sin_propuestas_las_tasas_operativas_son_none(self):
        resultado = _por_codigo(metricas.calcular_metricas())
        for codigo in ("M04", "M05", "M06", "M10", "M11"):
            self.assertIsNone(resultado[codigo]["valor"], codigo)


@override_settings(MEDIA_ROOT=MEDIA)
class MetricasOperativasTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta")
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        self.inst = Instantiation.objects.create(
            nombre="Copia", record_resource=self.record,
            archivo=SimpleUploadedFile("a.txt", "Reunión del Cabildo de Santafé el 20 de julio de 1810.".encode()),
        )
        extraer_texto_de_instanciacion(self.inst)
        evidencia = Evidencia.objects.create(instanciacion=self.inst, fragmento="Cabildo de Santafé", verificada=True)
        self.p1 = PropuestaRiC.objects.create(
            origen=self.record, relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            proveedor="falso", confianza=0.9, evidencia=evidencia,
        )
        self.p2 = PropuestaRiC.objects.create(
            origen=self.record, relacion_id="R027", entidad_tipo="E11", entidad_nombre="Otro",
            proveedor="falso", confianza=0.5, evidencia=evidencia,
        )

    def test_m04_m05_m06_suman_uno_sobre_lo_decidido(self):
        self.p1.validar(self.archivista, aceptar=True)
        self.p2.validar(self.archivista, aceptar=False, motivo="no aplica")
        resultado = _por_codigo(metricas.calcular_metricas())
        self.assertEqual(resultado["M04"]["valor"], 0.5)
        self.assertEqual(resultado["M06"]["valor"], 0.5)
        self.assertEqual(resultado["M05"]["valor"], 0.0)

    def test_m10_trazabilidad_cuenta_propuestas_con_evidencia(self):
        resultado = _por_codigo(metricas.calcular_metricas())
        self.assertEqual(resultado["M10"]["valor"], 1.0)  # ambas tienen evidencia

    def test_m11_consistencia_cuenta_auto_rechazos_del_motor(self):
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E18", entidad_nombre="20 de julio de 1810",
            evidencia="20 de julio de 1810", confianza=0.9,
        )]
        [auto_rechazada] = generar_propuestas(self.record, ProveedorFalso(candidatos))
        self.assertEqual(auto_rechazada.estado, PropuestaRiC.Estado.RECHAZADA)

        self.p1.validar(self.archivista, aceptar=True)
        resultado = _por_codigo(metricas.calcular_metricas())
        # 1 materializada de 2 evaluadas por el motor (1 materializada + 1 auto-rechazada)
        self.assertEqual(resultado["M11"]["valor"], 0.5)

    def test_m03_usa_la_auditoria_por_muestreo_cuando_hay_datos(self):
        self.p1.validar(self.archivista, aceptar=True)
        rel = RelacionRiC.objects.get(relacion_id="R027", origen_object_id=self.record.pk)
        muestra = MuestraRiC.objects.create(relacion=rel)
        muestra.revisar(self.archivista, MuestraRiC.Resultado.CORRECTA)

        resultado = _por_codigo(metricas.calcular_metricas())
        self.assertEqual(resultado["M03"]["valor"], 1.0)
        self.assertIsNone(resultado["M03"]["nota"])


class EvaluacionViewTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")

    def test_requiere_login(self):
        resp = self.client.get(reverse("ric_evaluacion"))
        self.assertEqual(resp.status_code, 302)

    def test_pagina_html_muestra_las_metricas(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_evaluacion"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "M01")
        self.assertContains(resp, "M11")

    def test_datos_json_devuelve_m01_a_m11_como_minimo(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_evaluacion_datos"))
        self.assertEqual(resp.status_code, 200)
        codigos = {m["codigo"] for m in resp.json()["metricas"]}
        for i in range(1, 12):
            self.assertIn(f"M{i:02d}", codigos)
