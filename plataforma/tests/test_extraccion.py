import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image, ImageDraw, ImageFont

from acervo.extraccion import FormatoNoSoportado, extraer_texto
from acervo.models import Documento, EventoPreservacion, verificar_cadena
from lineamientos.verificacion import CUMPLE, MANUAL, NO_CUMPLE, evaluar_documento

MEDIA = tempfile.mkdtemp()
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
TEXTO = "Acta del Cabildo de Santafe 1810"


def imagen_con_texto(texto=TEXTO):
    img = Image.new("RGB", (1400, 200), "white")
    ImageDraw.Draw(img).text((40, 60), texto, fill="black", font=ImageFont.truetype(FUENTE, 56))
    return img


def a_bytes(img, formato):
    buf = io.BytesIO()
    img.save(buf, format=formato)
    return buf.getvalue()


def pdf_con_texto(texto):
    """PDF mínimo de una página con capa de texto."""
    flujo = f"BT /F1 24 Tf 72 700 Td ({texto}) Tj ET".encode()
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida, posiciones = b"%PDF-1.4\n", []
    for i, obj in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
    return salida


@override_settings(MEDIA_ROOT=MEDIA)
class ExtraccionTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)

    def documento(self, nombre, contenido):
        return Documento.objects.create(titulo=nombre, archivo=SimpleUploadedFile(nombre, contenido))

    def met_03(self, doc):
        return next(r for r in evaluar_documento(doc) if r.criterio.codigo == "MET-03")

    def test_ocr_de_imagen_registra_herramienta_y_confianza(self):
        doc = self.documento("acta.png", a_bytes(imagen_con_texto(), "PNG"))
        self.assertEqual(self.met_03(doc).estado, MANUAL)
        texto, detalle = extraer_texto(doc)
        self.assertIn("Cabildo", texto)
        self.assertIn("1810", texto)
        self.assertEqual(detalle["metodo"], "ocr")
        self.assertIn("Tesseract", detalle["herramienta"])
        self.assertGreaterEqual(detalle["confianza_ocr"], 75)
        doc.refresh_from_db()
        self.assertIn("Cabildo", doc.texto_extraido)
        self.assertTrue(doc.eventos.filter(tipo=EventoPreservacion.Tipo.EXTRACCION).exists())
        self.assertTrue(verificar_cadena(doc)[0])
        self.assertEqual(self.met_03(doc).estado, CUMPLE)

    def test_pdf_escaneado_pasa_por_ocr(self):
        doc = self.documento("escaneado.pdf", a_bytes(imagen_con_texto(), "PDF"))
        texto, detalle = extraer_texto(doc)
        self.assertIn("Cabildo", texto)
        self.assertEqual(detalle["paginas_ocr"], 1)

    def test_pdf_con_capa_de_texto_no_usa_ocr(self):
        doc = self.documento("digital.pdf", pdf_con_texto(TEXTO))
        texto, detalle = extraer_texto(doc)
        self.assertIn("Cabildo", texto)
        self.assertEqual(detalle["metodo"], "lectura_directa")
        self.assertEqual(self.met_03(doc).estado, CUMPLE)

    def test_texto_plano_en_latin1(self):
        doc = self.documento("nota.txt", "Informe de la Real Audiencia, año 1795".encode("latin-1"))
        texto, _ = extraer_texto(doc)
        self.assertIn("año 1795", texto)

    def test_ocr_de_baja_confianza_exige_revision(self):
        doc = self.documento("acta.png", a_bytes(imagen_con_texto(), "PNG"))
        extraer_texto(doc)
        evento = doc.eventos.get(tipo=EventoPreservacion.Tipo.EXTRACCION)
        evento.detalle["confianza_ocr"] = 40.0
        evento.save()
        self.assertEqual(self.met_03(doc).estado, NO_CUMPLE)

    def test_formato_no_soportado(self):
        doc = self.documento("audio.mp3", b"ID3")
        with self.assertRaises(FormatoNoSoportado):
            extraer_texto(doc)
