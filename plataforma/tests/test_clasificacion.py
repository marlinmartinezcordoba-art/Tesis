import shutil
import tempfile
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from acceso.models import RevisionDatosPersonales as Revision
from acceso.servicios import revisar_datos_personales
from acervo.extraccion import extraer_texto
from acervo.models import Documento, UnidadClasificacion
from asistencia.proveedor_claude import (
    ClasificacionPropuesta,
    ErrorProveedorIA,
    ProveedorClasificacionClaude,
)
from asistencia.proveedor_local import ErrorProveedorIA as ErrorProveedorIALocal
from asistencia.proveedor_local import ProveedorClasificacionLocal
from asistencia.proveedores import generar_sugerencias
from lineamientos.verificacion import CUMPLE, MANUAL, NO_CUMPLE, evaluar_documento

MEDIA = tempfile.mkdtemp()

TEXTO = (
    "Acta de la sesión del Cabildo de Santafé, 20 de julio de 1810. "
    "Se reunieron los vecinos para tratar los asuntos del común."
)


@override_settings(MEDIA_ROOT=MEDIA)
class ClasificacionBaseTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        call_command("loaddata", "cuadro_demo", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)
        self.serie_actas = UnidadClasificacion.objects.get(codigo="F.01.S02.SE01")

    def criterio(self, codigo):
        return next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == codigo)


class ProveedorClasificacionLocalTest(ClasificacionBaseTest):
    def test_propone_la_serie_con_mas_palabras_clave(self):
        [s] = generar_sugerencias(self.doc, ProveedorClasificacionLocal())
        self.assertEqual(s.proceso, "clasificacion")
        self.assertEqual(s.valor_propuesto, self.serie_actas.codigo)
        self.assertTrue(s.evidencia_verificada)

    def test_sin_coincidencias_no_propone_nada(self):
        doc = Documento.objects.create(
            titulo="Sin relación", archivo=SimpleUploadedFile("x.txt", b"Texto sin relacion alguna con series")
        )
        extraer_texto(doc)
        self.assertEqual(generar_sugerencias(doc, ProveedorClasificacionLocal()), [])

    def test_sin_cuadro_cargado_lanza_error(self):
        UnidadClasificacion.objects.filter(tipo__in=["serie", "subserie"]).delete()
        with self.assertRaises(ErrorProveedorIALocal):
            ProveedorClasificacionLocal().proponer(self.doc, TEXTO)

    def test_aceptar_vincula_la_unidad_y_queda_en_bitacora(self):
        [s] = generar_sugerencias(self.doc, ProveedorClasificacionLocal())
        self.assertEqual(self.criterio("CLA-03").estado, NO_CUMPLE)  # pendiente
        s.validar(self.archivista, aceptar=True)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.unidad_clasificacion, self.serie_actas)
        self.assertEqual(self.criterio("CLA-03").estado, CUMPLE)

    def test_rechazar_no_vincula_nada(self):
        [s] = generar_sugerencias(self.doc, ProveedorClasificacionLocal())
        s.validar(self.archivista, aceptar=False, motivo="No corresponde")
        self.doc.refresh_from_db()
        self.assertIsNone(self.doc.unidad_clasificacion)

    def test_codigo_inexistente_al_validar_falla_con_claridad(self):
        [s] = generar_sugerencias(self.doc, ProveedorClasificacionLocal())
        with self.assertRaises(ValueError):
            s.validar(self.archivista, aceptar=True, valor_final="CODIGO-QUE-NO-EXISTE")


class ProveedorClasificacionClaudeTest(ClasificacionBaseTest):
    def test_no_envia_sin_revision_de_datos_personales(self):
        with self.assertRaises(ErrorProveedorIA):
            ProveedorClasificacionClaude().texto_de(self.doc)

    def test_propone_serie_valida_de_la_lista(self):
        revisar_datos_personales(self.doc).decidir(self.archivista, Revision.Decision.PUBLICABLE, "")

        propuesta = ClasificacionPropuesta(
            codigo_unidad=self.serie_actas.codigo,
            evidencia="Acta de la sesión del Cabildo",
            confianza="alta",
            justificacion="El documento es un acta de cabildo.",
        )
        respuesta = MagicMock(stop_reason="end_turn", model="claude-opus-5", parsed_output=propuesta)
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta

        [s] = generar_sugerencias(self.doc, ProveedorClasificacionClaude(cliente=cliente))
        self.assertEqual(s.valor_propuesto, self.serie_actas.codigo)
        self.assertTrue(s.evidencia_verificada)
        self.assertEqual(s.proceso, "clasificacion")

    def test_codigo_inventado_se_descarta(self):
        revisar_datos_personales(self.doc).decidir(self.archivista, Revision.Decision.PUBLICABLE, "")

        propuesta = ClasificacionPropuesta(
            codigo_unidad="CODIGO-INVENTADO", evidencia="algo", confianza="alta", justificacion="x",
        )
        respuesta = MagicMock(stop_reason="end_turn", model="claude-opus-5", parsed_output=propuesta)
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta

        self.assertEqual(generar_sugerencias(self.doc, ProveedorClasificacionClaude(cliente=cliente)), [])

    def test_sin_cuadro_cargado_lanza_error(self):
        UnidadClasificacion.objects.filter(tipo__in=["serie", "subserie"]).delete()
        revisar_datos_personales(self.doc).decidir(self.archivista, Revision.Decision.PUBLICABLE, "")
        with self.assertRaises(ErrorProveedorIA):
            ProveedorClasificacionClaude(cliente=MagicMock()).proponer(self.doc, TEXTO)
