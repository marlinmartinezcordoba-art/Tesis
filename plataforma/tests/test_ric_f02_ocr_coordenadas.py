"""F02 (OCR): además de extraer texto y asociarlo a su página, el sistema
debe guardar las coordenadas (bbox) de cada palabra reconocida y, a partir
de ellas, la caja delimitadora del fragmento citado como evidencia — así
una propuesta de IA puede señalarse literalmente sobre la imagen del
documento, no solo por número de página.

Antes de esto, `pytesseract.image_to_data` ya calculaba esas coordenadas
pero se descartaban: solo se guardaban el texto y la confianza."""

import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image, ImageDraw, ImageFont

from ric.evidencia import crear_evidencia, localizar_posicion
from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import Instantiation, Record

MEDIA = tempfile.mkdtemp()
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _imagen_con_texto(lineas, ancho=700, alto_linea=50):
    img = Image.new("L", (ancho, alto_linea * len(lineas) + 20), color=255)
    dibujo = ImageDraw.Draw(img)
    fuente = ImageFont.truetype(FUENTE, 28)
    for i, linea in enumerate(lineas):
        dibujo.text((15, 10 + i * alto_linea), linea, fill=0, font=fuente)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=MEDIA)
class CoordenadasOCRTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.record = Record.objects.create(nombre="Acta escaneada")
        contenido = _imagen_con_texto(["Acta del Cabildo de Santafe", "Fecha 20 de julio de 1810"])
        self.inst = Instantiation.objects.create(
            nombre="Copia escaneada", record_resource=self.record,
            archivo=SimpleUploadedFile("acta_escaneada.png", contenido),
        )
        extraer_texto_de_instanciacion(self.inst)
        self.pagina = self.inst.paginas.get(numero=1)

    def test_la_pagina_ocr_guarda_cajas_por_palabra(self):
        self.assertTrue(self.pagina.uso_ocr)
        self.assertTrue(self.pagina.cajas_ocr, "debería haber al menos una palabra georreferenciada")
        for caja in self.pagina.cajas_ocr:
            for clave in ("texto", "izquierda", "arriba", "ancho", "alto", "confianza"):
                self.assertIn(clave, caja)

    def test_localizar_posicion_de_una_palabra_reconocida(self):
        primera_palabra = self.pagina.cajas_ocr[0]["texto"]
        posicion = localizar_posicion(self.pagina, primera_palabra)
        self.assertIsNotNone(posicion)
        for clave in ("izquierda", "arriba", "ancho", "alto"):
            self.assertIn(clave, posicion)
        self.assertGreater(posicion["ancho"], 0)
        self.assertGreater(posicion["alto"], 0)

    def test_localizar_posicion_de_fragmento_inexistente_es_none(self):
        self.assertIsNone(localizar_posicion(self.pagina, "palabras que no están en la imagen"))

    def test_crear_evidencia_calcula_la_posicion_automaticamente(self):
        primera_palabra = self.pagina.cajas_ocr[0]["texto"]
        ev = crear_evidencia(self.inst, primera_palabra)
        self.assertTrue(ev.verificada)
        self.assertIsNotNone(ev.posicion)
        self.assertIn("izquierda", ev.posicion)

    def test_crear_evidencia_respeta_una_posicion_explicita(self):
        primera_palabra = self.pagina.cajas_ocr[0]["texto"]
        manual = {"izquierda": 1, "arriba": 2, "ancho": 3, "alto": 4}
        ev = crear_evidencia(self.inst, primera_palabra, posicion=manual)
        self.assertEqual(ev.posicion, manual)


@override_settings(MEDIA_ROOT=MEDIA)
class SinCoordenadasEnTextoPlanoTest(TestCase):
    """F02 es honesto: un archivo de texto plano (o la capa de texto de un
    PDF) no tiene coordenadas porque no hay imagen sobre la cual medirlas —
    no se inventan coordenadas donde no las hay."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_pagina_de_texto_plano_no_tiene_cajas_ocr(self):
        record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("acta.txt", "Acta del Cabildo de Santafe".encode()),
        )
        extraer_texto_de_instanciacion(inst)
        pagina = inst.paginas.get(numero=1)
        self.assertFalse(pagina.uso_ocr)
        self.assertIsNone(pagina.cajas_ocr)

    def test_evidencia_sobre_texto_plano_no_tiene_posicion(self):
        record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("acta.txt", "Acta del Cabildo de Santafe".encode()),
        )
        extraer_texto_de_instanciacion(inst)
        ev = crear_evidencia(inst, "Cabildo de Santafe")
        self.assertTrue(ev.verificada)
        self.assertIsNone(ev.posicion)
