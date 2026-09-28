"""F05 (IA multimodal): dos correcciones encontradas al auditar el código
existente antes de seguir construyendo sobre él.

1. `generar_propuestas` usaba `record.instanciaciones.first()` sin ningún
   orden definido — con la carga masiva de F01 (varios archivos por
   Record) o un segmento de F04, cuál se le pasaba a la IA era arbitrario.
   Ahora se usa la que más texto extraído tiene.
2. `ProveedorClaude` solo enviaba el texto ya extraído por OCR, nunca la
   imagen o el PDF real — a pesar de llamarse "multimodal". Firmas,
   sellos y tablas mal leídas por el OCR eran invisibles para la IA. La
   usuaria pidió explícitamente que si la IA ve el documento real; ahora
   se le envía como bloque de imagen/documento además del texto.
"""

import shutil
import tempfile
from unittest.mock import MagicMock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import Instantiation, Record
from ric.proveedor_claude import ProveedorClaude, _contenido_visual
from ric.proveedores import ErrorProveedorIA, PropuestaCandidata, ProveedorIA, generar_propuestas

MEDIA = tempfile.mkdtemp()


class ProveedorFalso(ProveedorIA):
    nombre, version = "falso", "0"

    def __init__(self, candidatos=None):
        self._candidatos = candidatos or []
        self.llamado_con = None

    def proponer(self, record, texto, instanciacion=None):
        self.llamado_con = instanciacion
        return self._candidatos


@override_settings(MEDIA_ROOT=MEDIA)
class SeleccionDeInstanciacionTest(TestCase):
    """Con varias Instantiation en un mismo Record (carga masiva de F01),
    la IA debe usar la que más texto real tiene, no "la primera" arbitraria."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_usa_la_instanciacion_con_mas_texto(self):
        record = Record.objects.create(nombre="Expediente con varios archivos")
        corta = Instantiation.objects.create(
            nombre="Nota corta", record_resource=record,
            archivo=SimpleUploadedFile("corta.txt", b"Hola."),
        )
        extraer_texto_de_instanciacion(corta)
        larga = Instantiation.objects.create(
            nombre="Acta completa", record_resource=record,
            archivo=SimpleUploadedFile("larga.txt", ("Acta del Cabildo de Santafé. " * 20).encode()),
        )
        extraer_texto_de_instanciacion(larga)

        proveedor = ProveedorFalso()
        generar_propuestas(record, proveedor)
        self.assertEqual(proveedor.llamado_con.pk, larga.pk)

    def test_sin_ninguna_instanciacion_falla_con_mensaje_claro(self):
        record = Record.objects.create(nombre="Vacío")
        with self.assertRaises(ErrorProveedorIA):
            generar_propuestas(record, ProveedorFalso())


@override_settings(MEDIA_ROOT=MEDIA)
class ContenidoVisualTest(TestCase):
    """`_contenido_visual`: qué formatos se le envían a Claude como imagen
    o documento, y cuáles se quedan solo en texto (honesto, no se inventa
    una representación visual donde no la hay)."""

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

    def test_pdf_se_envia_como_documento(self):
        inst = self._instanciacion("acta.pdf", b"%PDF-1.4 contenido falso")
        [bloque] = _contenido_visual(inst)
        self.assertEqual(bloque["type"], "document")
        self.assertEqual(bloque["source"]["media_type"], "application/pdf")

    def test_png_se_envia_como_imagen(self):
        inst = self._instanciacion("escaneo.png", b"\x89PNG contenido falso")
        [bloque] = _contenido_visual(inst)
        self.assertEqual(bloque["type"], "image")
        self.assertEqual(bloque["source"]["media_type"], "image/png")

    def test_jpg_se_envia_como_imagen(self):
        inst = self._instanciacion("escaneo.jpg", b"\xff\xd8 contenido falso")
        [bloque] = _contenido_visual(inst)
        self.assertEqual(bloque["source"]["media_type"], "image/jpeg")

    def test_texto_plano_no_tiene_representacion_visual(self):
        inst = self._instanciacion("acta.txt", b"Texto plano.")
        self.assertEqual(_contenido_visual(inst), [])

    def test_tiff_no_soportado_por_la_api_de_vision_se_queda_en_texto(self):
        # F01 acepta .tiff para preservación, pero la API de Claude no lo
        # documenta como formato de imagen soportado: no se envía como
        # visual para no adivinar un media_type no verificado.
        inst = self._instanciacion("escaneo.tiff", b"contenido falso")
        self.assertEqual(_contenido_visual(inst), [])


@override_settings(MEDIA_ROOT=MEDIA)
class ProveedorClaudeEnviaLaImagenTest(TestCase):
    """El mensaje que de verdad se le manda a la API de Claude debe incluir
    el bloque de imagen/documento cuando existe, antes del texto."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def _cliente_falso(self):
        borrador = MagicMock(relaciones=[])
        respuesta = MagicMock(stop_reason="end_turn", model="claude-opus-5", parsed_output=borrador)
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta
        return cliente

    def test_incluye_el_bloque_de_imagen_antes_del_texto(self):
        record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Escaneo", record_resource=record,
            archivo=SimpleUploadedFile("acta.png", b"\x89PNG contenido falso"),
        )
        cliente = self._cliente_falso()
        ProveedorClaude(cliente=cliente).proponer(record, "Un texto cualquiera.", instanciacion=inst)

        contenido = cliente.beta.messages.parse.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(contenido[0]["type"], "image")
        self.assertEqual(contenido[-1]["type"], "text")
        system = cliente.beta.messages.parse.call_args.kwargs["system"]
        self.assertIn("también puedes ver la imagen", system.lower())

    def test_sin_instanciacion_no_hay_bloque_visual_ni_mencion_en_el_prompt(self):
        record = Record.objects.create(nombre="Acta")
        cliente = self._cliente_falso()
        ProveedorClaude(cliente=cliente).proponer(record, "Un texto cualquiera.")

        contenido = cliente.beta.messages.parse.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(len(contenido), 1)
        self.assertEqual(contenido[0]["type"], "text")
        system = cliente.beta.messages.parse.call_args.kwargs["system"]
        self.assertNotIn("también puedes ver la imagen", system.lower())

    def test_docx_no_produce_bloque_visual(self):
        record = Record.objects.create(nombre="Informe")
        inst = Instantiation.objects.create(
            nombre="Informe", record_resource=record,
            archivo=SimpleUploadedFile("informe.docx", b"contenido falso"),
        )
        cliente = self._cliente_falso()
        ProveedorClaude(cliente=cliente).proponer(record, "Un texto cualquiera.", instanciacion=inst)
        contenido = cliente.beta.messages.parse.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(len(contenido), 1)


@override_settings(MEDIA_ROOT=MEDIA)
class ProveedorClaudeErroresTest(TestCase):
    """Cada excepción de la SDK de Anthropic debe llegar a la persona
    archivista como un ErrorProveedorIA en español, no como una traza
    técnica — antes esto no tenía ninguna prueba dedicada."""

    def _proveedor(self, side_effect):
        cliente = MagicMock()
        cliente.beta.messages.parse.side_effect = side_effect
        return ProveedorClaude(cliente=cliente)

    def _record(self):
        return Record.objects.create(nombre="Acta")

    def test_error_de_autenticacion(self):
        import anthropic

        from ric.proveedor_claude import ErrorProveedorIA

        error = anthropic.AuthenticationError(
            message="bad key", response=MagicMock(status_code=401), body=None,
        )
        with self.assertRaises(ErrorProveedorIA):
            self._proveedor(error).proponer(self._record(), "texto")

    def test_error_de_limite_de_uso(self):
        import anthropic

        from ric.proveedor_claude import ErrorProveedorIA

        error = anthropic.RateLimitError(message="slow down", response=MagicMock(status_code=429), body=None)
        with self.assertRaises(ErrorProveedorIA):
            self._proveedor(error).proponer(self._record(), "texto")

    def test_error_de_conexion(self):
        import anthropic

        from ric.proveedor_claude import ErrorProveedorIA

        error = anthropic.APIConnectionError(message="no network", request=MagicMock())
        with self.assertRaises(ErrorProveedorIA):
            self._proveedor(error).proponer(self._record(), "texto")

    def test_respuesta_rechazada_por_seguridad(self):
        from ric.proveedor_claude import ErrorProveedorIA

        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = MagicMock(stop_reason="refusal")
        with self.assertRaises(ErrorProveedorIA):
            ProveedorClaude(cliente=cliente).proponer(self._record(), "texto")

    def test_respuesta_incompleta_por_limite_de_tokens(self):
        from ric.proveedor_claude import ErrorProveedorIA

        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = MagicMock(stop_reason="max_tokens", parsed_output=None)
        with self.assertRaises(ErrorProveedorIA):
            ProveedorClaude(cliente=cliente).proponer(self._record(), "texto")
