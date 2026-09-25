import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from acceso.models import RevisionDatosPersonales as Revision
from acceso.servicios import revisar_datos_personales
from acervo.extraccion import extraer_texto
from acervo.models import Documento, Entidad
from asistencia.proveedor_claude import (
    BorradorDescripcion,
    CampoPropuesto,
    EntidadPropuesta,
    ErrorProveedorIA,
    ProveedorClaude,
)
from asistencia.proveedor_local import ProveedorLocal
from asistencia.proveedores import (
    Propuesta,
    ProveedorIA,
    evidencia_en_texto,
    generar_sugerencias,
)
from lineamientos.verificacion import CUMPLE, MANUAL, NO_CUMPLE, evaluar_documento

MEDIA = tempfile.mkdtemp()

TEXTO = (
    "Acta del Cabildo de Santafé, 20 de julio de 1810. "
    "Se reunió José Acevedo y Gómez con los vecinos de la ciudad de Santafé "
    "para tratar los asuntos de la Real Audiencia."
)


class EvidenciaTest(TestCase):
    def test_evidencia_presente_ignora_mayusculas_y_espacios(self):
        self.assertTrue(evidencia_en_texto("cabildo   DE Santafé", TEXTO))

    def test_evidencia_ausente(self):
        self.assertFalse(evidencia_en_texto("un dato inventado", TEXTO))

    def test_evidencia_vacia_no_cuenta(self):
        self.assertFalse(evidencia_en_texto("", TEXTO))


class ProveedorFalso(ProveedorIA):
    nombre = "falso"
    version = "0"

    def proponer(self, documento, texto):
        return [
            Propuesta("descripcion", "fechas", "1810", 0.9, "Justificación", evidencia="1810"),
            Propuesta("descripcion", "productor", "Un dato inventado", 0.9, "Justificación",
                       evidencia="dato que no está en el texto"),
        ]


@override_settings(MEDIA_ROOT=MEDIA)
class GenerarSugerenciasTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)

    def test_evidencia_verificada_baja_confianza_si_no_se_encuentra(self):
        [s1, s2] = generar_sugerencias(self.doc, ProveedorFalso())
        self.assertTrue(s1.evidencia_verificada)
        self.assertEqual(s1.confianza, 0.9)
        self.assertFalse(s2.evidencia_verificada)
        self.assertLessEqual(s2.confianza, 0.3)
        self.assertIn("⚠", s2.justificacion)

    def test_criterio_des03(self):
        resultado = lambda: next(r for r in evaluar_documento(self.doc) if r.criterio.codigo == "DES-03")
        self.assertEqual(resultado().estado, MANUAL)
        generar_sugerencias(self.doc, ProveedorFalso())
        self.assertEqual(resultado().estado, CUMPLE)  # nada aceptado todavía


@override_settings(MEDIA_ROOT=MEDIA)
class ProveedorClaudeTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)

    def test_no_envia_sin_revision_de_datos_personales(self):
        with self.assertRaises(ErrorProveedorIA):
            ProveedorClaude().texto_de(self.doc)

    def test_no_envia_documento_restringido(self):
        archivista = User.objects.create_user("a", password="x")
        r = revisar_datos_personales(self.doc)
        r.decidir(archivista, Revision.Decision.RESTRINGIDO, "Prueba")
        with self.assertRaises(ErrorProveedorIA):
            ProveedorClaude().texto_de(self.doc)

    def test_envia_texto_anonimizado_si_se_decidio_anonimizar(self):
        archivista = User.objects.create_user("a", password="x")
        r = revisar_datos_personales(self.doc)
        r.decidir(archivista, Revision.Decision.ANONIMIZAR, "Prueba")
        self.doc.refresh_from_db()
        self.assertEqual(ProveedorClaude().texto_de(self.doc), self.doc.texto_publico)

    def test_envia_texto_original_si_es_publicable(self):
        archivista = User.objects.create_user("a", password="x")
        r = revisar_datos_personales(self.doc)
        r.decidir(archivista, Revision.Decision.PUBLICABLE, "")
        self.assertEqual(ProveedorClaude().texto_de(self.doc), self.doc.texto_extraido)

    def test_proponer_usa_respuesta_estructurada_y_registra_modelo_servido(self):
        archivista = User.objects.create_user("b", password="x")
        r = revisar_datos_personales(self.doc)
        r.decidir(archivista, Revision.Decision.PUBLICABLE, "")

        borrador = BorradorDescripcion(
            titulo=CampoPropuesto(valor="[Acta del Cabildo]", evidencia="Acta del Cabildo",
                                    confianza="alta", justificacion="Encabezado del documento."),
            fechas=CampoPropuesto(valor="1810", evidencia="1810", confianza="alta", justificacion="Fecha explícita."),
            productor=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion="No se determina."),
            alcance_contenido=CampoPropuesto(valor="Reunión del Cabildo.", evidencia="Se reunió",
                                               confianza="media", justificacion="Resumen."),
            entidades=[
                EntidadPropuesta(tipo="persona", nombre="José Acevedo y Gómez", relacion="productor",
                                   evidencia="José Acevedo y Gómez", confianza="alta"),
            ],
        )
        respuesta = MagicMock(stop_reason="end_turn", model="claude-opus-4-8", parsed_output=borrador)
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta

        proveedor = ProveedorClaude(cliente=cliente, modelo="claude-opus-5")
        sugerencias = generar_sugerencias(self.doc, proveedor)

        campos = {s.campo: s for s in sugerencias}
        self.assertEqual(campos["titulo"].valor_propuesto, "[Acta del Cabildo]")
        self.assertTrue(campos["titulo"].evidencia_verificada)
        self.assertNotIn("productor", campos)  # valor vacío: no se propone
        self.assertEqual(campos["persona"].valor_propuesto, "José Acevedo y Gómez")
        self.assertEqual(proveedor.version, "claude-opus-4-8")  # modelo que sirvió, no el pedido

        _, kwargs = cliente.beta.messages.parse.call_args
        self.assertEqual(kwargs["output_format"], BorradorDescripcion)
        self.assertEqual(kwargs["fallbacks"], "default")

    def test_refusal_levanta_error_claro(self):
        respuesta = MagicMock(stop_reason="refusal")
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta
        with self.assertRaises(ErrorProveedorIA):
            ProveedorClaude(cliente=cliente).proponer(self.doc, TEXTO)


@override_settings(MEDIA_ROOT=MEDIA)
class ProveedorLocalTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)

    def test_reconoce_entidades_y_fechas_sin_conexion(self):
        sugerencias = generar_sugerencias(self.doc, ProveedorLocal())
        campos = {s.campo for s in sugerencias}
        self.assertIn("fechas", campos)
        self.assertTrue(campos & {"persona", "lugar", "institucion"})
        for s in sugerencias:
            self.assertTrue(s.evidencia_verificada)  # spaCy solo cita texto que ya está ahí

    def test_aceptar_entidad_la_vincula_al_documento(self):
        archivista = User.objects.create_user("a", password="x")
        sugerencias = generar_sugerencias(self.doc, ProveedorLocal())
        entidad_sug = next(s for s in sugerencias if s.campo in {"persona", "lugar", "institucion"})
        entidad_sug.validar(archivista, aceptar=True)
        self.assertTrue(Entidad.objects.filter(
            tipo=entidad_sug.campo, nombre=entidad_sug.valor_propuesto, documentos=self.doc
        ).exists())
