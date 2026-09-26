"""Pruebas del aprendizaje asistido simple (Fase 6, T060-T061): que
`ejemplos_validados` solo cuente decisiones humanas reales, que la
recuperación por similitud funcione, y que ProveedorClaude de verdad
inyecte los ejemplos recuperados en el prompt (RAG sin fine-tuning)."""

import shutil
import tempfile
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric import aprendizaje
from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import CorporateBody, Instantiation, PropuestaRiC, Record
from ric.proveedor_claude import ProveedorClaude
from ric.proveedores import PropuestaCandidata, ProveedorIA, generar_propuestas

MEDIA = tempfile.mkdtemp()


class ProveedorFalso(ProveedorIA):
    nombre, version = "falso", "0"

    def __init__(self, candidatos):
        self._candidatos = candidatos

    def proponer(self, record, texto):
        return self._candidatos


@override_settings(MEDIA_ROOT=MEDIA)
class EjemplosValidadosTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=self.record,
            archivo=SimpleUploadedFile("acta.txt", "Reunión del Cabildo de Santafé el 20 de julio de 1810.".encode()),
        )
        extraer_texto_de_instanciacion(inst)
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia="Cabildo de Santafé", confianza=0.9,
        )]
        [self.propuesta] = generar_propuestas(self.record, ProveedorFalso(candidatos))

    def test_propuesta_pendiente_no_es_un_ejemplo_todavia(self):
        self.assertEqual(list(aprendizaje.ejemplos_validados()), [])

    def test_propuesta_aceptada_por_una_persona_si_es_un_ejemplo(self):
        self.propuesta.validar(self.archivista, aceptar=True)
        self.assertEqual(list(aprendizaje.ejemplos_validados()), [self.propuesta])

    def test_propuesta_rechazada_por_una_persona_no_cuenta_por_defecto(self):
        self.propuesta.validar(self.archivista, aceptar=False, motivo="No aplica.")
        self.assertEqual(list(aprendizaje.ejemplos_validados()), [])

    def test_auto_rechazo_del_motor_de_reglas_nunca_es_un_ejemplo(self):
        # una propuesta con un entidad_tipo que no encaja en R027 (Agent) se
        # auto-rechaza en generar_propuestas, sin que ninguna persona decida
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E18", entidad_nombre="20 de julio de 1810",
            evidencia="20 de julio de 1810", confianza=0.9,
        )]
        [auto_rechazada] = generar_propuestas(self.record, ProveedorFalso(candidatos))
        self.assertEqual(auto_rechazada.estado, PropuestaRiC.Estado.RECHAZADA)
        self.assertIsNone(auto_rechazada.validado_por)
        self.assertEqual(list(aprendizaje.ejemplos_validados()), [])


@override_settings(MEDIA_ROOT=MEDIA)
class EjemplosSimilaresTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=self.record,
            archivo=SimpleUploadedFile("acta.txt", "Reunión del Cabildo de Santafé el 20 de julio de 1810.".encode()),
        )
        extraer_texto_de_instanciacion(inst)
        [self.propuesta] = generar_propuestas(self.record, ProveedorFalso([
            PropuestaCandidata(relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
                                evidencia="Cabildo de Santafé", confianza=0.9),
        ]))
        self.propuesta.validar(self.archivista, aceptar=True)

    def test_encuentra_ejemplo_por_similitud_de_texto(self):
        resultados = aprendizaje.ejemplos_similares("Acuerdo del Cabildo sobre la independencia")
        self.assertEqual(resultados, [self.propuesta])

    def test_sin_coincidencia_no_devuelve_nada(self):
        self.assertEqual(aprendizaje.ejemplos_similares("dinosaurios en la luna"), [])

    def test_filtra_por_tipo_de_origen(self):
        self.assertEqual(aprendizaje.ejemplos_similares("Cabildo", origen_modelo=Record), [self.propuesta])
        self.assertEqual(aprendizaje.ejemplos_similares("Cabildo", origen_modelo=CorporateBody), [])

    def test_formatear_ejemplos_incluye_fragmento_y_decision(self):
        texto = aprendizaje.formatear_ejemplos([self.propuesta])
        self.assertIn("Cabildo de Santafé", texto)
        self.assertIn("R027", texto)
        self.assertIn("aceptada tal cual", texto)


@override_settings(MEDIA_ROOT=MEDIA)
class ProveedorClaudeInyectaEjemplosTest(TestCase):
    """RAG de T061: el system prompt de verdad incluye los ejemplos
    recuperados, o los omite cuando no hay ninguno relevante."""

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

    def test_sin_ejemplos_previos_no_hay_seccion_de_ejemplos(self):
        record = Record.objects.create(nombre="Acta nueva")
        cliente = self._cliente_falso()
        ProveedorClaude(cliente=cliente).proponer(record, "Un texto cualquiera.")
        system = cliente.beta.messages.parse.call_args.kwargs["system"]
        self.assertNotIn("Ejemplos de decisiones ya validadas", system)

    def test_con_un_ejemplo_previo_similar_lo_inyecta_en_el_prompt(self):
        archivista = User.objects.create_user("archivista", password="x")
        anterior = Record.objects.create(nombre="Acta anterior")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=anterior,
            archivo=SimpleUploadedFile("a.txt", "Reunión del Cabildo de Santafé el 20 de julio de 1810.".encode()),
        )
        extraer_texto_de_instanciacion(inst)
        [propuesta] = generar_propuestas(anterior, ProveedorFalso([
            PropuestaCandidata(relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
                                evidencia="Cabildo de Santafé", confianza=0.9),
        ]))
        propuesta.validar(archivista, aceptar=True)

        nuevo = Record.objects.create(nombre="Acta nueva")
        cliente = self._cliente_falso()
        ProveedorClaude(cliente=cliente).proponer(nuevo, "El Cabildo de Santafé se reunió de nuevo.")
        system = cliente.beta.messages.parse.call_args.kwargs["system"]
        self.assertIn("Ejemplos de decisiones ya validadas", system)
        self.assertIn("Cabildo de Santafé", system)
        self.assertIn("R027", system)
