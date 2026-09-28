"""F05 (IA multimodal) con Gemini: la usuaria decidió que el proveedor de
IA en la nube que se usa activamente es Gemini, no Claude. `ProveedorGemini`
implementa el mismo contrato (`ProveedorIA.proponer`) y comparte el prompt
y el esquema de salida (`ric.ia_prompt`) con `ProveedorClaude` — estas
pruebas espejan `test_ric_f05_multimodal.py` para el nuevo proveedor.
"""

import shutil
import tempfile
from unittest.mock import MagicMock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from google.genai import types as genai_types

from ric.models import Instantiation, Record
from ric.proveedor_gemini import ProveedorGemini, _contenido_visual

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class ContenidoVisualGeminiTest(TestCase):
    """Mismo alcance honesto que `ric.proveedor_claude._contenido_visual`:
    solo imagen o PDF, nunca se inventa una representación visual."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def _instanciacion(self, nombre, contenido=b"contenido"):
        record = Record.objects.create(nombre=f"Registro de {nombre}")
        return Instantiation.objects.create(
            nombre=nombre, record_resource=record,
            archivo=SimpleUploadedFile(nombre, contenido),
        )

    def test_ninguna_instanciacion_no_produce_contenido_visual(self):
        self.assertEqual(_contenido_visual(None), [])

    def test_pdf_se_envia_como_parte_binaria(self):
        inst = self._instanciacion("acta.pdf", b"%PDF-1.4 contenido falso")
        [parte] = _contenido_visual(inst)
        self.assertEqual(parte.inline_data.mime_type, "application/pdf")

    def test_png_se_envia_como_imagen(self):
        inst = self._instanciacion("escaneo.png", b"\x89PNG contenido falso")
        [parte] = _contenido_visual(inst)
        self.assertEqual(parte.inline_data.mime_type, "image/png")

    def test_jpg_se_envia_como_imagen(self):
        inst = self._instanciacion("escaneo.jpg", b"\xff\xd8 contenido falso")
        [parte] = _contenido_visual(inst)
        self.assertEqual(parte.inline_data.mime_type, "image/jpeg")

    def test_texto_plano_no_tiene_representacion_visual(self):
        inst = self._instanciacion("acta.txt", b"Texto plano.")
        self.assertEqual(_contenido_visual(inst), [])

    def test_tiff_no_soportado_se_queda_en_texto(self):
        inst = self._instanciacion("escaneo.tiff", b"contenido falso")
        self.assertEqual(_contenido_visual(inst), [])


@override_settings(MEDIA_ROOT=MEDIA)
class ProveedorGeminiEnviaLaImagenTest(TestCase):
    """El mensaje que de verdad se le manda a la API de Gemini debe incluir
    la parte de imagen/documento cuando existe, antes del texto."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def _cliente_falso(self):
        candidato = MagicMock(finish_reason=genai_types.FinishReason.STOP)
        respuesta = MagicMock(
            candidates=[candidato], model_version="gemini-2.5-pro",
            parsed=MagicMock(relaciones=[]),
        )
        cliente = MagicMock()
        cliente.models.generate_content.return_value = respuesta
        return cliente

    def test_incluye_la_parte_de_imagen_antes_del_texto(self):
        record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Escaneo", record_resource=record,
            archivo=SimpleUploadedFile("acta.png", b"\x89PNG contenido falso"),
        )
        cliente = self._cliente_falso()
        ProveedorGemini(cliente=cliente).proponer(record, "Un texto cualquiera.", instanciacion=inst)

        llamada = cliente.models.generate_content.call_args.kwargs
        partes = llamada["contents"][0].parts
        self.assertIsNotNone(partes[0].inline_data)
        self.assertIsNotNone(partes[-1].text)
        self.assertIn("también puedes ver la imagen", llamada["config"].system_instruction.lower())

    def test_sin_instanciacion_no_hay_parte_visual_ni_mencion_en_el_prompt(self):
        record = Record.objects.create(nombre="Acta")
        cliente = self._cliente_falso()
        ProveedorGemini(cliente=cliente).proponer(record, "Un texto cualquiera.")

        llamada = cliente.models.generate_content.call_args.kwargs
        partes = llamada["contents"][0].parts
        self.assertEqual(len(partes), 1)
        self.assertIsNotNone(partes[0].text)
        self.assertNotIn("también puedes ver la imagen", llamada["config"].system_instruction.lower())

    def test_docx_no_produce_parte_visual(self):
        record = Record.objects.create(nombre="Informe")
        inst = Instantiation.objects.create(
            nombre="Informe", record_resource=record,
            archivo=SimpleUploadedFile("informe.docx", b"contenido falso"),
        )
        cliente = self._cliente_falso()
        ProveedorGemini(cliente=cliente).proponer(record, "Un texto cualquiera.", instanciacion=inst)
        partes = cliente.models.generate_content.call_args.kwargs["contents"][0].parts
        self.assertEqual(len(partes), 1)

    def test_usa_el_esquema_estructurado_de_ia_prompt(self):
        from ric.ia_prompt import PropuestasRecordRiC

        record = Record.objects.create(nombre="Acta")
        cliente = self._cliente_falso()
        ProveedorGemini(cliente=cliente).proponer(record, "Un texto cualquiera.")
        config = cliente.models.generate_content.call_args.kwargs["config"]
        self.assertIs(config.response_schema, PropuestasRecordRiC)
        self.assertEqual(config.response_mime_type, "application/json")


@override_settings(MEDIA_ROOT=MEDIA)
class ProveedorGeminiErroresTest(TestCase):
    """Cada excepción de la SDK de Gemini debe llegar a la persona
    archivista como un ErrorProveedorIA en español, no como una traza
    técnica."""

    def _proveedor(self, side_effect):
        cliente = MagicMock()
        cliente.models.generate_content.side_effect = side_effect
        return ProveedorGemini(cliente=cliente)

    def _record(self):
        return Record.objects.create(nombre="Acta")

    def test_error_de_autenticacion(self):
        from google.genai import errors as genai_errors

        from ric.proveedor_gemini import ErrorProveedorIA

        error = genai_errors.ClientError(401, {"message": "bad key"})
        with self.assertRaises(ErrorProveedorIA):
            self._proveedor(error).proponer(self._record(), "texto")

    def test_error_de_limite_de_uso(self):
        from google.genai import errors as genai_errors

        from ric.proveedor_gemini import ErrorProveedorIA

        error = genai_errors.ClientError(429, {"message": "slow down"})
        with self.assertRaises(ErrorProveedorIA):
            self._proveedor(error).proponer(self._record(), "texto")

    def test_error_de_servidor(self):
        from google.genai import errors as genai_errors

        from ric.proveedor_gemini import ErrorProveedorIA

        error = genai_errors.ServerError(503, {"message": "unavailable"})
        with self.assertRaises(ErrorProveedorIA):
            self._proveedor(error).proponer(self._record(), "texto")

    def test_error_de_conexion(self):
        import httpx

        from ric.proveedor_gemini import ErrorProveedorIA

        error = httpx.ConnectError("no network")
        with self.assertRaises(ErrorProveedorIA):
            self._proveedor(error).proponer(self._record(), "texto")

    def test_respuesta_rechazada_por_seguridad(self):
        from ric.proveedor_gemini import ErrorProveedorIA

        cliente = MagicMock()
        candidato = MagicMock(finish_reason=genai_types.FinishReason.PROHIBITED_CONTENT)
        cliente.models.generate_content.return_value = MagicMock(candidates=[candidato])
        with self.assertRaises(ErrorProveedorIA):
            ProveedorGemini(cliente=cliente).proponer(self._record(), "texto")

    def test_respuesta_incompleta_por_limite_de_tokens(self):
        from ric.proveedor_gemini import ErrorProveedorIA

        cliente = MagicMock()
        candidato = MagicMock(finish_reason=genai_types.FinishReason.MAX_TOKENS)
        cliente.models.generate_content.return_value = MagicMock(candidates=[candidato], parsed=None)
        with self.assertRaises(ErrorProveedorIA):
            ProveedorGemini(cliente=cliente).proponer(self._record(), "texto")

    def test_respuesta_sin_texto_estructurado_valido(self):
        from ric.proveedor_gemini import ErrorProveedorIA

        cliente = MagicMock()
        candidato = MagicMock(finish_reason=genai_types.FinishReason.STOP)
        cliente.models.generate_content.return_value = MagicMock(
            candidates=[candidato], parsed=None, model_version="gemini-2.5-pro",
        )
        with self.assertRaises(ErrorProveedorIA):
            ProveedorGemini(cliente=cliente).proponer(self._record(), "texto")
