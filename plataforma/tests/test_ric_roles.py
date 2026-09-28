"""F16 (Seguridad): dos perfiles, pensando en un front de solo consulta
para usuarios finales (como en un SaaS) — "archivista" (is_staff, el
mismo de siempre, con panel técnico) e "invitado de consulta" (sesión
iniciada, sin is_staff): puede buscar, ver el grafo validado, consultar
SPARQL y exportar, pero no puede ingerir documentos ni validar
propuestas de IA. Se crea igual que cualquier usuario, desde el panel
técnico de Django, sin marcar la casilla "Es staff"."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import Instantiation, PropuestaRiC, Record
from ric.proveedores import PropuestaCandidata, ProveedorIA, generar_propuestas

MEDIA = tempfile.mkdtemp()
TEXTO = "Acta del Cabildo de Santafé, 20 de julio de 1810."


class ProveedorFalso(ProveedorIA):
    nombre, version = "falso", "0"

    def __init__(self, candidatos):
        self._candidatos = candidatos

    def proponer(self, record, texto, instanciacion=None):
        return self._candidatos


@override_settings(MEDIA_ROOT=MEDIA)
class InvitadoDeConsultaTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.consulta = User.objects.create_user("consulta", password="x", is_staff=False)

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

    def test_invitado_no_puede_ver_el_formulario_de_subir(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("ric_subir"), follow=True)
        self.assertContains(resp, "solo consulta")
        self.assertNotContains(resp, "Subir un documento")

    def test_invitado_no_puede_subir_un_archivo(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("ric_subir"), {
            "nombre_nuevo": "Intento de invitado",
            "archivos": [SimpleUploadedFile("otro.txt", b"contenido")],
        }, follow=True)
        self.assertContains(resp, "solo consulta")
        self.assertFalse(Record.objects.filter(nombre="Intento de invitado").exists())

    def test_invitado_no_puede_ver_la_bandeja(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("ric_bandeja"), follow=True)
        self.assertContains(resp, "solo consulta")

    def test_invitado_no_puede_decidir_una_propuesta(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(
            reverse("ric_decidir_propuesta", args=[self.propuesta.pk]),
            {"accion": "aceptar", "motivo": ""}, follow=True,
        )
        self.assertContains(resp, "solo consulta")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.PENDIENTE)

    def test_invitado_si_puede_buscar_ver_grafo_sparql_y_evaluacion(self):
        self.client.force_login(self.consulta)
        for nombre in ("ric_inicio", "ric_registros", "ric_busqueda", "ric_sparql", "ric_evaluacion", "ric_modulos"):
            resp = self.client.get(reverse(nombre))
            self.assertEqual(resp.status_code, 200, nombre)

    def test_invitado_si_puede_ver_el_archivo_original(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("ric_archivo", args=[self.propuesta.evidencia.instanciacion.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_archivista_sigue_pudiendo_subir_y_validar(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_subir"))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse("ric_bandeja"))
        self.assertEqual(resp.status_code, 200)

    def test_menu_lateral_oculta_lo_de_archivista_para_el_invitado(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("ric_inicio"))
        self.assertNotContains(resp, "Subir documento")
        self.assertNotContains(resp, "Bandeja de validación")
        self.assertNotContains(resp, "Panel técnico")

    def test_menu_lateral_muestra_todo_para_el_archivista(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_inicio"))
        self.assertContains(resp, "Subir documento")
        self.assertContains(resp, "Bandeja de validación")
        self.assertContains(resp, "Panel técnico")
