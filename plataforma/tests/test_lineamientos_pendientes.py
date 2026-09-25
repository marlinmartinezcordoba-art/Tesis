"""Pruebas de los lineamientos que se construyeron después del capítulo IV:
DES-04 (relaciones tipadas), MET-04 (exportación) y la auditoría por
muestreo (CLA-04, VAL-03).
"""
import shutil
import tempfile
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from acervo import exportacion
from acervo.extraccion import extraer_texto
from acervo.models import Documento, Entidad, RelacionEntidadDocumento
from asistencia.auditoria import (
    MuestraAuditoria,
    reporte_exactitud,
    reporte_sesgo_valoracion,
    seleccionar_muestra,
)
from asistencia.proveedor_local import ProveedorValoracionLocal
from asistencia.proveedores import Propuesta, ProveedorIA, generar_sugerencias
from lineamientos.verificacion import CUMPLE, MANUAL, evaluar_documento

MEDIA = tempfile.mkdtemp()

TEXTO = (
    "Acta de la sesión del Cabildo de Santafé, 20 de julio de 1810. "
    "José Acevedo y Gómez presidió la reunión, con la fiesta tradicional "
    "de la comunidad durante la guerra de independencia."
)


class ProveedorEntidadFalso(ProveedorIA):
    nombre = "falso-entidad"
    version = "0"

    def proponer(self, documento, texto):
        return [Propuesta(
            proceso="descripcion", campo="persona", valor="José Acevedo y Gómez",
            confianza=0.9, justificacion="j", evidencia="José Acevedo y Gómez",
            relacion="productor",
        )]


@override_settings(MEDIA_ROOT=MEDIA)
class Des04Test(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)

    def criterio(self, codigo):
        return next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == codigo)

    def test_sin_entidades_es_manual(self):
        self.assertEqual(self.criterio("DES-04").estado, MANUAL)

    def test_aceptar_crea_relacion_tipada(self):
        [s] = generar_sugerencias(self.doc, ProveedorEntidadFalso())
        s.validar(self.archivista, aceptar=True)
        relacion = RelacionEntidadDocumento.objects.get(documento=self.doc)
        self.assertEqual(relacion.tipo_relacion, "productor")
        self.assertEqual(relacion.entidad.nombre, "José Acevedo y Gómez")
        self.assertEqual(self.criterio("DES-04").estado, CUMPLE)

    def test_proveedor_local_usa_mencionado_por_defecto(self):
        from asistencia.proveedor_local import ProveedorLocal

        sugerencias = generar_sugerencias(self.doc, ProveedorLocal())
        entidad_sug = next(s for s in sugerencias if s.campo == "persona")
        self.assertEqual(entidad_sug.relacion, "mencionado")
        entidad_sug.validar(self.archivista, aceptar=True)
        relacion = RelacionEntidadDocumento.objects.get(
            documento=self.doc, entidad__nombre=entidad_sug.valor_propuesto
        )
        self.assertEqual(relacion.tipo_relacion, "mencionado")

    def test_misma_entidad_dos_relaciones_distintas_coexisten(self):
        entidad = Entidad.objects.create(tipo="persona", nombre="Prueba")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=entidad, tipo_relacion="productor"
        )
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=entidad, tipo_relacion="mencionado"
        )
        self.assertEqual(
            RelacionEntidadDocumento.objects.filter(documento=self.doc, entidad=entidad).count(), 2
        )


@override_settings(MEDIA_ROOT=MEDIA)
class Met04ExportacionTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Acta con «comillas» & símbolos",
            codigo_referencia="CO.AGN.01",
            productor="Cabildo",
            fechas="1810",
            archivo=SimpleUploadedFile("acta.txt", TEXTO.encode()),
        )

    def criterio(self, codigo):
        return next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == codigo)

    def test_dublin_core_escapa_caracteres_especiales(self):
        xml = exportacion.dublin_core_xml(self.doc)
        self.assertIn("&amp;", xml)  # el título tiene un "&" literal
        self.assertIn("<dc:creator>Cabildo</dc:creator>", xml)
        self.assertIn(self.doc.sha256, xml)

    def test_premis_incluye_fijeza_y_eventos(self):
        xml = exportacion.premis_xml(self.doc)
        self.assertIn(self.doc.sha256, xml)
        self.assertIn("<premis:eventType>ingreso</premis:eventType>", xml)

    def test_met_04_requiere_exportacion_previa(self):
        self.assertEqual(self.criterio("MET-04").estado, MANUAL)

    def test_met_04_via_vista_http(self):
        self.client.force_login(self.archivista)
        r = self.client.get(f"/documentos/{self.doc.pk}/exportar/dublin-core.xml")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/xml; charset=utf-8")
        self.assertEqual(self.criterio("MET-04").estado, CUMPLE)

    def test_exportacion_requiere_login(self):
        r = self.client.get(f"/documentos/{self.doc.pk}/exportar/premis.xml")
        self.assertEqual(r.status_code, 302)


@override_settings(MEDIA_ROOT=MEDIA)
class AuditoriaMuestreoTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.docs = []
        for i in range(3):
            doc = Documento.objects.create(
                titulo=f"Doc {i}",
                archivo=SimpleUploadedFile(f"d{i}.txt", TEXTO.encode()),
            )
            extraer_texto(doc)
            sugerencias = generar_sugerencias(doc, ProveedorValoracionLocal())
            for s in sugerencias:
                s.validar(self.archivista, aceptar=True)
            self.docs.append(doc)

    def test_seleccionar_muestra_solo_toma_aceptadas_no_auditadas(self):
        from asistencia.models import SugerenciaIA

        total_aceptadas = SugerenciaIA.objects.filter(
            proceso="valoracion", estado__in=["aceptada", "modificada"]
        ).count()
        self.assertGreaterEqual(total_aceptadas, 3)  # cada doc aporta al menos un indicio

        creadas = seleccionar_muestra("valoracion", tamano=100)
        self.assertEqual(len(creadas), total_aceptadas)
        # una segunda vez no hay nada nuevo que auditar
        self.assertEqual(seleccionar_muestra("valoracion", tamano=100), [])

    def test_revisar_incorrecta_exige_observacion(self):
        [m] = seleccionar_muestra("valoracion", tamano=1)
        with self.assertRaises(ValueError):
            m.revisar(self.archivista, MuestraAuditoria.Resultado.INCORRECTA)
        m.revisar(self.archivista, MuestraAuditoria.Resultado.INCORRECTA, "No era histórico")
        self.assertEqual(m.resultado, "incorrecta")

    def test_reporte_exactitud(self):
        muestras = seleccionar_muestra("valoracion", tamano=3)
        muestras[0].revisar(self.archivista, MuestraAuditoria.Resultado.CORRECTA)
        muestras[1].revisar(self.archivista, MuestraAuditoria.Resultado.CORRECTA)
        muestras[2].revisar(self.archivista, MuestraAuditoria.Resultado.INCORRECTA, "error")
        r = reporte_exactitud("valoracion")
        self.assertEqual(r["total_revisadas"], 3)
        self.assertEqual(r["correctas"], 2)
        self.assertAlmostEqual(r["exactitud"], 66.7, places=1)

    def test_reporte_sesgo_por_tipo_de_valor(self):
        for m in seleccionar_muestra("valoracion", tamano=3):
            m.revisar(self.archivista, MuestraAuditoria.Resultado.CORRECTA)
        reporte = reporte_sesgo_valoracion()
        self.assertIn("valor_historico", reporte)
        total = sum(v["total_revisadas"] for v in reporte.values())
        self.assertEqual(total, 3)

    def test_comando_de_gestion_selecciona_y_reporta(self):
        call_command("auditoria_muestra", "valoracion", "--tamano", "2")
        self.assertEqual(MuestraAuditoria.objects.count(), 2)
        with self.assertRaises(CommandError):
            call_command("auditoria_muestra", "clasificacion", "--tamano", "5")

    def test_admin_exige_motivo_para_incorrecta(self):
        [m] = seleccionar_muestra("valoracion", tamano=1)
        admin_user = User.objects.create_superuser("admin", password="x")
        self.client.force_login(admin_user)
        url = f"/admin/asistencia/muestraauditoria/{m.pk}/change/"
        r = self.client.post(url, {"resultado": "incorrecta", "observacion": ""})
        self.assertContains(r, "Explique en qué se equivocó")
        r = self.client.post(url, {"resultado": "correcta", "observacion": ""})
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertEqual(m.revisado_por, admin_user)
