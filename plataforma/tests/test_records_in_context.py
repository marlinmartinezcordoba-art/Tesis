"""Pruebas de la alineación del modelo de datos con RiC-CM 1.0 (ICA-EGAD, 2023):
la entidad de tipo Actividad, el vocabulario ampliado de relaciones, y la
validación de que la combinación tipo de entidad / tipo de relación tenga
sentido (RELACIONES_VALIDAS_POR_TIPO).
"""
import shutil
import tempfile
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from acceso.models import RevisionDatosPersonales as Revision
from acceso.servicios import revisar_datos_personales
from acervo import exportacion
from acervo.extraccion import extraer_texto
from acervo.models import Documento, Entidad, RelacionEntidadDocumento
from asistencia.proveedor_claude import (
    BorradorDescripcion,
    CampoPropuesto,
    EntidadPropuesta,
    ProveedorClaude,
)
from asistencia.proveedores import generar_sugerencias

MEDIA = tempfile.mkdtemp()

TEXTO = (
    "Acta de la sesión del Cabildo de Santafé, 20 de julio de 1810, en la que "
    "José Acevedo y Gómez presidió la reunión sobre el levantamiento popular."
)


@override_settings(MEDIA_ROOT=MEDIA)
class RicModeloTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        call_command("loaddata", "criterios_borrador", verbosity=0)
        self.archivista = User.objects.create_user("archivista", password="x")
        self.doc = Documento.objects.create(
            titulo="Acta", archivo=SimpleUploadedFile("acta.txt", TEXTO.encode())
        )
        extraer_texto(self.doc)

    def _borrador_con_entidades(self, entidades):
        return BorradorDescripcion(
            titulo=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion=""),
            fechas=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion=""),
            productor=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion=""),
            alcance_contenido=CampoPropuesto(valor="", evidencia="", confianza="baja", justificacion=""),
            entidades=entidades,
        )

    def _mock_cliente(self, borrador):
        respuesta = MagicMock(stop_reason="end_turn", model="claude-opus-5", parsed_output=borrador)
        cliente = MagicMock()
        cliente.beta.messages.parse.return_value = respuesta
        return cliente

    def _publicable(self):
        revisar_datos_personales(self.doc).decidir(self.archivista, Revision.Decision.PUBLICABLE, "")

    def test_no_existe_tipo_concepto(self):
        # RiC-CM no tiene una entidad "concepto"; verificamos que el modelo
        # tampoco la ofrezca como opción.
        self.assertNotIn("concepto", dict(Entidad.Tipo.choices))
        self.assertIn("actividad", dict(Entidad.Tipo.choices))

    def test_proponer_actividad_con_relacion_documenta(self):
        self._publicable()
        borrador = self._borrador_con_entidades([
            EntidadPropuesta(
                tipo="actividad", nombre="Sesión del Cabildo del 20 de julio de 1810",
                relacion="documenta", evidencia="sesión del Cabildo de Santafé", confianza="alta",
            ),
        ])
        [s] = generar_sugerencias(self.doc, ProveedorClaude(cliente=self._mock_cliente(borrador)))
        self.assertEqual(s.campo, "actividad")
        self.assertEqual(s.relacion, "documenta")
        self.assertTrue(s.evidencia_verificada)

        s.validar(self.archivista, aceptar=True)
        relacion = RelacionEntidadDocumento.objects.get(documento=self.doc)
        self.assertEqual(relacion.entidad.tipo, "actividad")
        self.assertEqual(relacion.tipo_relacion, "documenta")

    def test_combinacion_invalida_se_descarta_al_proponer(self):
        # "productor" no tiene sentido para una actividad: MAZUCA lo descarta
        # antes de crear la sugerencia, sin confiar ciegamente en el modelo.
        self._publicable()
        borrador = self._borrador_con_entidades([
            EntidadPropuesta(
                tipo="actividad", nombre="Sesión del Cabildo",
                relacion="productor", evidencia="sesión del Cabildo", confianza="alta",
            ),
        ])
        sugerencias = generar_sugerencias(self.doc, ProveedorClaude(cliente=self._mock_cliente(borrador)))
        self.assertEqual(sugerencias, [])

    def test_combinacion_invalida_se_rechaza_al_validar(self):
        # Defensa en profundidad: aunque alguien fuerce una sugerencia con una
        # combinación inválida (por ejemplo, corrigiendo el campo a mano),
        # validar() la rechaza igual.
        from asistencia.models import SugerenciaIA
        from lineamientos.models import Proceso

        s = SugerenciaIA.objects.create(
            documento=self.doc, proceso=Proceso.DESCRIPCION, campo="lugar",
            valor_propuesto="Santafé", relacion="productor",
            confianza=0.9, modelo="prueba", version_modelo="0",
        )
        with self.assertRaises(ValueError):
            s.validar(self.archivista, aceptar=True)

    def test_relacion_trata_sobre_valida_para_persona(self):
        self._publicable()
        borrador = self._borrador_con_entidades([
            EntidadPropuesta(
                tipo="persona", nombre="José Acevedo y Gómez",
                relacion="trata_sobre", evidencia="José Acevedo y Gómez", confianza="media",
            ),
        ])
        [s] = generar_sugerencias(self.doc, ProveedorClaude(cliente=self._mock_cliente(borrador)))
        s.validar(self.archivista, aceptar=True)
        relacion = RelacionEntidadDocumento.objects.get(documento=self.doc)
        self.assertEqual(relacion.tipo_relacion, "trata_sobre")

    def test_proveedor_local_no_propone_actividades(self):
        from asistencia.proveedor_local import ProveedorLocal

        sugerencias = generar_sugerencias(self.doc, ProveedorLocal())
        self.assertNotIn("actividad", {s.campo for s in sugerencias})

    def test_dublin_core_usa_el_grafo_de_entidades(self):
        # MET-04 (exportación) debe reflejar el grafo RiC construido en
        # descripción, no solo los campos planos de la ficha ISAD(G).
        productor = Entidad.objects.create(tipo="institucion", nombre="Cabildo de Santafé")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=productor, tipo_relacion="productor"
        )
        tema = Entidad.objects.create(tipo="persona", nombre="José Acevedo y Gómez")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=tema, tipo_relacion="trata_sobre"
        )
        lugar = Entidad.objects.create(tipo="lugar", nombre="Santafé")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=lugar, tipo_relacion="lugar_produccion"
        )
        actividad = Entidad.objects.create(tipo="actividad", nombre="Sesión del Cabildo")
        RelacionEntidadDocumento.objects.create(
            documento=self.doc, entidad=actividad, tipo_relacion="documenta"
        )

        xml = exportacion.dublin_core_xml(self.doc)
        self.assertIn("<dc:creator>Cabildo de Santafé</dc:creator>", xml)
        self.assertIn("<dc:subject>José Acevedo y Gómez</dc:subject>", xml)
        self.assertIn("<dc:coverage>Santafé</dc:coverage>", xml)
        self.assertIn("Documenta: Sesión del Cabildo", xml)

    def test_dublin_core_sin_entidades_no_falla(self):
        # Documento sin ninguna entidad vinculada: la exportación no debe
        # romperse, solo omitir los campos derivados del grafo.
        xml = exportacion.dublin_core_xml(self.doc)
        self.assertNotIn("dc:subject", xml)
        self.assertNotIn("dc:coverage", xml)
