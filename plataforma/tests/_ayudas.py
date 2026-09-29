"""Piezas comunes a las pruebas de los módulos M1-M11: usuarios por rol,
un documento con texto ya extraído y un proveedor de IA falso que devuelve
lo que se le indique (sin red, sin claves)."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric import roles
from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import Instantiation, Record
from ric.proveedores import PropuestaCandidata, ProveedorIA, generar_propuestas

TEXTO = (
    "Acta de la sesión del Cabildo de Santafé, 20 de julio de 1810, en la que "
    "José Acevedo y Gómez presidió la reunión sobre el levantamiento popular en Bogotá."
)


class ProveedorFalso(ProveedorIA):
    nombre, version = "falso", "0"

    def __init__(self, candidatos=None, advertencias=None, forma_documental=None):
        self._candidatos = candidatos or []
        self.advertencias = advertencias or []
        self.forma_documental = forma_documental

    def proponer(self, record, texto, instanciacion=None):
        return self._candidatos


def candidato(**cambios):
    base = dict(
        relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
        evidencia="Cabildo de Santafé", confianza=0.9, justificacion="firma el acta",
    )
    base.update(cambios)
    return PropuestaCandidata(**base)


class CasoModulos(TestCase):
    """TestCase con MEDIA_ROOT temporal y los cuatro usuarios de RF-M11-01."""

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    def setUp(self):
        self.superusuario = User.objects.create_superuser("marlin", password="claveSegura123")
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.revisor = User.objects.create_user("revisor", password="x")
        roles.asignar_rol(self.revisor, roles.REVISOR)
        self.consulta = User.objects.create_user("consulta", password="x")

    def documento(self, nombre="Acta", texto=TEXTO, archivo="acta.txt"):
        record = Record.objects.create(nombre=nombre)
        inst = Instantiation.objects.create(
            nombre=archivo, record_resource=record, archivo=SimpleUploadedFile(archivo, texto.encode()),
        )
        extraer_texto_de_instanciacion(inst)
        return record, inst

    def proponer(self, record, *candidatos):
        return generar_propuestas(record, ProveedorFalso(list(candidatos)))
