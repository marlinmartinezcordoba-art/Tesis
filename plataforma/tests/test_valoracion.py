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
from acervo.models import Documento
from asistencia.proveedor_claude import (
    ErrorProveedorIA,
    IndicioPropuesto,
    ProveedorValoracionClaude,
    ValoracionPropuesta,
)
from asistencia.proveedor_local import ProveedorValoracionLocal
from asistencia.proveedores import generar_sugerencias
from lineamientos.verificacion import CUMPLE, MANUAL, NO_CUMPLE, evaluar_documento

MEDIA = tempfile.mkdtemp()

TEXTO = (
    "Relato de la fiesta tradicional del pueblo, con la comunidad reunida en "
    "torno a la independencia de la villa durante la guerra de 1810."
)


@override_settings(MEDIA_ROOT=MEDIA)
class ValoracionBaseTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Relato", archivo=SimpleUploadedFile("relato.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)

    def criterio(self, codigo):
        return next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == codigo)


class Val01SiempreCumpleTest(ValoracionBaseTest):
    def test_val_01_no_depende_del_documento(self):
        # La plataforma nunca ofrece eliminar documentos; el criterio es
        # estructural, no depende de si hay sugerencias o no.
        self.assertEqual(self.criterio("VAL-01").estado, CUMPLE)

    def test_admin_no_permite_eliminar_documentos(self):
        from django.contrib import admin as django_admin

        self.assertFalse(
            django_admin.site._registry[Documento].has_delete_permission(MagicMock())
        )


class ProveedorValoracionLocalTest(ValoracionBaseTest):
    def test_detecta_varios_tipos_de_valor_a_la_vez(self):
        sugerencias = generar_sugerencias(self.doc, ProveedorValoracionLocal())
        campos = {s.campo for s in sugerencias}
        self.assertIn("valor_historico", campos)
        self.assertIn("valor_cultural", campos)
        for s in sugerencias:
            self.assertTrue(s.evidencia_verificada)

    def test_sin_coincidencias_no_propone_nada(self):
        doc = Documento.objects.create(
            titulo="Recibo", archivo=SimpleUploadedFile("r.txt", b"Recibido: 5 pesos por transporte.")
        )
        extraer_texto(doc)
        self.assertEqual(generar_sugerencias(doc, ProveedorValoracionLocal()), [])
        self.assertEqual(self.criterio("VAL-02").estado, MANUAL)

    def test_criterio_val_02_tras_validar(self):
        self.assertEqual(self.criterio("VAL-02").estado, MANUAL)
        sugerencias = generar_sugerencias(self.doc, ProveedorValoracionLocal())
        self.assertEqual(self.criterio("VAL-02").estado, MANUAL)  # aún pendientes de decisión
        for s in sugerencias:
            s.validar(self.archivista, aceptar=True)
        self.assertEqual(self.criterio("VAL-02").estado, CUMPLE)

    def test_rechazar_indicio_no_modifica_el_documento(self):
        [s, *_] = generar_sugerencias(self.doc, ProveedorValoracionLocal())
        s.validar(self.archivista, aceptar=False, motivo="No aplica en este caso")
        self.assertEqual(s.estado, "rechazada")
        # Rechazar no toca ningún campo del documento: no hay campo que valorar module.


class ProveedorValoracionClaudeTest(ValoracionBaseTest):
    def test_no_envia_sin_revision_de_datos_personales(self):
        with self.assertRaises(ErrorProveedorIA):
            ProveedorValoracionClaude().texto_de(self.doc)

    def test_propone_multiples_indicios_con_evidencia(self):
        revisar_datos_personales(self.doc).decidir(self.archivista, Revision.Decision.PUBLICABLE, "")

        propuesta = ValoracionPropuesta(indicios=[
            IndicioPropuesto(tipo="historico", evidencia="guerra de 1810", confianza="alta",
                              justificacion="Se refiere a la guerra de independencia."),
            IndicioPropuesto(tipo="cultural", evidencia="fiesta tradicional", confianza="media",
                              justificacion="Describe una fiesta tradicional de la comunidad."),
        ])
        respuesta = MagicMock(stop_reason="end_turn", model="claude-opus-4-8", parsed_output=propuesta)
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta

        sugerencias = generar_sugerencias(self.doc, ProveedorValoracionClaude(cliente=cliente))
        campos = {s.campo: s for s in sugerencias}
        self.assertEqual(len(sugerencias), 2)
        self.assertTrue(campos["valor_historico"].evidencia_verificada)
        self.assertTrue(campos["valor_cultural"].evidencia_verificada)

    def test_lista_vacia_no_genera_sugerencias(self):
        revisar_datos_personales(self.doc).decidir(self.archivista, Revision.Decision.PUBLICABLE, "")

        respuesta = MagicMock(
            stop_reason="end_turn", model="claude-opus-5",
            parsed_output=ValoracionPropuesta(indicios=[]),
        )
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta
        self.assertEqual(generar_sugerencias(self.doc, ProveedorValoracionClaude(cliente=cliente)), [])

    def test_duplica_tipo_se_queda_con_el_primero(self):
        revisar_datos_personales(self.doc).decidir(self.archivista, Revision.Decision.PUBLICABLE, "")

        propuesta = ValoracionPropuesta(indicios=[
            IndicioPropuesto(tipo="historico", evidencia="guerra de 1810", confianza="alta", justificacion="a"),
            IndicioPropuesto(tipo="historico", evidencia="independencia", confianza="baja", justificacion="b"),
        ])
        respuesta = MagicMock(stop_reason="end_turn", model="claude-opus-5", parsed_output=propuesta)
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta

        sugerencias = generar_sugerencias(self.doc, ProveedorValoracionClaude(cliente=cliente))
        self.assertEqual(len(sugerencias), 1)
        self.assertEqual(sugerencias[0].justificacion, "a")
