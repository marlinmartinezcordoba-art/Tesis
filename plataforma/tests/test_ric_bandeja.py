"""Pruebas de la bandeja de validación (T040): la vista que muestra a la
vez documento + evidencia + propuesta de IA + entidad/relación RiC, y las
tres decisiones posibles (aceptar, vincular, rechazar).
"""

import io
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageDraw, ImageFont

from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import CorporateBody, Instantiation, PropuestaRiC, Record, RelacionRiC
from ric.proveedores import PropuestaCandidata, ProveedorIA, generar_propuestas

MEDIA = tempfile.mkdtemp()
TEXTO = "Acta del Cabildo de Santafé, 20 de julio de 1810."
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


class ProveedorFalso(ProveedorIA):
    nombre = "falso"
    version = "0"

    def __init__(self, candidatos):
        self._candidatos = candidatos

    def proponer(self, record, texto, instanciacion=None):
        return self._candidatos


@override_settings(MEDIA_ROOT=MEDIA)
class BandejaValidacionTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=self.record,
            archivo=SimpleUploadedFile("acta.txt", TEXTO.encode()),
        )
        extraer_texto_de_instanciacion(inst)
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia="Cabildo de Santafé", confianza=0.9,
        )]
        [self.propuesta] = generar_propuestas(self.record, ProveedorFalso(candidatos))

    def test_requiere_login(self):
        resp = self.client.get(reverse("ric_bandeja"))
        self.assertEqual(resp.status_code, 302)

    def test_lista_la_propuesta_pendiente_con_su_evidencia(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_bandeja"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "R027")
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertContains(resp, "verificada en el texto")

    def test_f06_enlaza_al_documento_original(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_bandeja"))
        url_archivo = reverse("ric_archivo", args=[self.propuesta.evidencia.instanciacion.pk])
        self.assertContains(resp, url_archivo)
        self.assertContains(resp, "ver el documento original")

    def test_aceptar_crea_la_relacion_y_ya_no_aparece_pendiente(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(
            reverse("ric_decidir_propuesta", args=[self.propuesta.pk]),
            {"accion": "aceptar", "motivo": ""},
            follow=True,
        )
        self.assertContains(resp, "aceptada")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.ACEPTADA)
        self.assertTrue(RelacionRiC.objects.filter(relacion_id="R027").exists())

        resp = self.client.get(reverse("ric_bandeja"))
        self.assertEqual(resp.context["total"], 0)

    def test_rechazar_sin_motivo_no_se_procesa(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(
            reverse("ric_decidir_propuesta", args=[self.propuesta.pk]),
            {"accion": "rechazar", "motivo": ""},
            follow=True,
        )
        self.assertContains(resp, "Indique el motivo")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.PENDIENTE)

    def test_rechazar_con_motivo_la_marca_rechazada(self):
        self.client.force_login(self.archivista)
        self.client.post(
            reverse("ric_decidir_propuesta", args=[self.propuesta.pk]),
            {"accion": "rechazar", "motivo": "No corresponde a este documento."},
        )
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.RECHAZADA)
        self.assertEqual(self.propuesta.motivo_decision, "No corresponde a este documento.")

    def test_vincular_a_entidad_existente_no_duplica(self):
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_bandeja"))
        self.assertContains(resp, "Cabildo de Santa Fe")  # aparece como candidata para vincular

        self.client.post(
            reverse("ric_decidir_propuesta", args=[self.propuesta.pk]),
            {"accion": "vincular", "entidad_existente": cabildo.pk, "motivo": ""},
        )
        self.assertEqual(CorporateBody.objects.count(), 1)
        rel = RelacionRiC.objects.get(relacion_id="R027")
        self.assertEqual(rel.destino, cabildo)


@override_settings(MEDIA_ROOT=MEDIA)
class ResaltadoVisualDeEvidenciaTest(TestCase):
    """F06: cuando el documento es una imagen escaneada y la evidencia
    tiene coordenadas de OCR (F02), la bandeja debe poder dibujar el
    recuadro sobre la imagen real — no solo citar el texto."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)

    def test_imagen_escaneada_con_posicion_activa_el_resaltado(self):
        record = Record.objects.create(nombre="Acta escaneada")
        contenido = _imagen_con_texto(["Acta del Cabildo de Santafe"])
        inst = Instantiation.objects.create(
            nombre="Copia escaneada", record_resource=record,
            archivo=SimpleUploadedFile("acta.png", contenido),
        )
        extraer_texto_de_instanciacion(inst)
        primera_palabra = inst.paginas.get(numero=1).cajas_ocr[0]["texto"]

        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia=primera_palabra, confianza=0.9,
        )]
        [propuesta] = generar_propuestas(record, ProveedorFalso(candidatos))
        self.assertIsNotNone(propuesta.evidencia.posicion)

        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_bandeja"))
        self.assertContains(resp, "evidencia-visual")
        self.assertContains(resp, f'data-x="{propuesta.evidencia.posicion["izquierda"]}"')

    def test_texto_plano_no_activa_el_resaltado(self):
        record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("acta.txt", TEXTO.encode()),
        )
        extraer_texto_de_instanciacion(inst)
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia="Cabildo de Santafé", confianza=0.9,
        )]
        generar_propuestas(record, ProveedorFalso(candidatos))

        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_bandeja"))
        # la clase existe siempre en el CSS de la página; lo que no debe
        # aparecer es el bloque en sí (marcado por el atributo data-x).
        self.assertNotContains(resp, "data-x=")
