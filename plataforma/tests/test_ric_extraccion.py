"""Pruebas de extracción de texto por página y verificación de evidencia
en el núcleo `ric` (ver Entregable 3: T021 del backlog)."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric.evidencia import crear_evidencia, localizar_fragmento
from ric.extraccion import FormatoNoSoportado, extraer_texto_de_instanciacion
from ric.models import CorporateBody, Record

MEDIA = tempfile.mkdtemp()

TEXTO = "Acta del Cabildo de Santafé, 20 de julio de 1810."


@override_settings(MEDIA_ROOT=MEDIA)
class ExtraccionPorPaginaTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def instanciacion(self, nombre="acta.txt", contenido=None):
        acta = Record.objects.create(nombre="Acta")
        from ric.models import Instantiation

        inst = Instantiation.objects.create(
            nombre="Copia digital", record_resource=acta,
            archivo=SimpleUploadedFile(nombre, (contenido or TEXTO).encode()),
        )
        inst.calcular_y_guardar_hash()
        inst.save()
        return inst

    def test_texto_plano_crea_una_pagina(self):
        inst = self.instanciacion()
        texto, detalle = extraer_texto_de_instanciacion(inst)
        self.assertIn("Cabildo", texto)
        self.assertEqual(detalle["paginas"], 1)
        self.assertEqual(inst.paginas.count(), 1)
        self.assertEqual(inst.paginas.first().numero, 1)
        self.assertIn("Cabildo", inst.paginas.first().texto)

    def test_texto_extraido_propiedad_une_todas_las_paginas(self):
        inst = self.instanciacion()
        extraer_texto_de_instanciacion(inst)
        self.assertIn("Cabildo", inst.texto_extraido)

    def test_reextraer_reemplaza_las_paginas_anteriores(self):
        inst = self.instanciacion()
        extraer_texto_de_instanciacion(inst)
        self.assertEqual(inst.paginas.count(), 1)
        extraer_texto_de_instanciacion(inst)  # segunda vez: no debe duplicar
        self.assertEqual(inst.paginas.count(), 1)

    def test_formato_no_soportado(self):
        inst = self.instanciacion(nombre="audio.mp3", contenido="ID3")
        with self.assertRaises(FormatoNoSoportado):
            extraer_texto_de_instanciacion(inst)


@override_settings(MEDIA_ROOT=MEDIA)
class EvidenciaVerificadaTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        acta = Record.objects.create(nombre="Acta")
        from ric.models import Instantiation

        self.inst = Instantiation.objects.create(
            nombre="Copia", record_resource=acta,
            archivo=SimpleUploadedFile("acta.txt", TEXTO.encode()),
        )
        extraer_texto_de_instanciacion(self.inst)

    def test_localizar_fragmento_existente(self):
        self.assertEqual(localizar_fragmento(self.inst, "Cabildo de Santafé"), 1)

    def test_localizar_fragmento_inexistente(self):
        self.assertIsNone(localizar_fragmento(self.inst, "un fragmento que no está"))

    def test_crear_evidencia_verificada(self):
        ev = crear_evidencia(self.inst, "20 de julio de 1810")
        self.assertTrue(ev.verificada)
        self.assertEqual(ev.pagina, 1)

    def test_crear_evidencia_no_verificada(self):
        ev = crear_evidencia(self.inst, "esto no aparece en el documento")
        self.assertFalse(ev.verificada)
        self.assertIsNone(ev.pagina)

    def test_evidencia_ignora_mayusculas_y_espacios(self):
        ev = crear_evidencia(self.inst, "  CABILDO   de santafé  ")
        self.assertTrue(ev.verificada)
