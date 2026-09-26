"""Pruebas de la bitácora con cadena de hash (T043) y de "vincular" una
propuesta a una entidad ya existente en vez de crear una posible duplicada.
"""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import CorporateBody, EventoRiC, Instantiation, Record, RelacionRiC, verificar_cadena
from ric.proveedores import PropuestaCandidata, ProveedorIA, generar_propuestas

MEDIA = tempfile.mkdtemp()
TEXTO = "Acta del Cabildo de Santafé, 20 de julio de 1810."


class ProveedorFalso(ProveedorIA):
    nombre = "falso"
    version = "0"

    def __init__(self, candidatos):
        self._candidatos = candidatos

    def proponer(self, record, texto):
        return self._candidatos


@override_settings(MEDIA_ROOT=MEDIA)
class BitacoraTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta")
        self.inst = Instantiation.objects.create(
            nombre="Copia", record_resource=self.record,
            archivo=SimpleUploadedFile("acta.txt", TEXTO.encode()),
        )

    def test_extraer_texto_registra_un_evento(self):
        extraer_texto_de_instanciacion(self.inst, agente=self.archivista)
        self.assertEqual(self.inst.eventos.count(), 1)
        evento = self.inst.eventos.first()
        self.assertEqual(evento.tipo, EventoRiC.Tipo.EXTRACCION)
        self.assertEqual(evento.agente, "archivista")

    def test_cadena_intacta_tras_extraccion_y_propuesta_y_validacion(self):
        extraer_texto_de_instanciacion(self.inst)
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia="Cabildo de Santafé", confianza=0.9,
        )]
        [propuesta] = generar_propuestas(self.record, ProveedorFalso(candidatos))
        propuesta.validar(self.archivista, aceptar=True)

        self.assertEqual(self.inst.eventos.count(), 3)  # extracción, propuesta, validación
        intacta, roto = verificar_cadena(self.inst)
        self.assertTrue(intacta, roto)

    def test_alterar_un_evento_rompe_la_cadena(self):
        extraer_texto_de_instanciacion(self.inst)
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia="Cabildo de Santafé", confianza=0.9,
        )]
        generar_propuestas(self.record, ProveedorFalso(candidatos))

        evento = self.inst.eventos.first()
        evento.detalle = {"manipulado": True}
        evento.save()

        intacta, roto = verificar_cadena(self.inst)
        self.assertFalse(intacta)
        self.assertEqual(roto.pk, evento.pk)

    def test_evento_sin_instanciacion_no_rompe_nada(self):
        # Una PropuestaRiC sin evidencia (evidencia=None) no tiene instanciación
        # que anclar; el evento se registra igual, sin cadena.
        from ric.models import EventoRiC as Evt
        from ric.models import registrar_evento

        evento = registrar_evento(None, Evt.Tipo.VALIDACION, agente="sistema", detalle={})
        self.assertIsNone(evento.instanciacion)
        self.assertEqual(evento.hash_anterior, "0" * 64)


@override_settings(MEDIA_ROOT=MEDIA)
class VincularEntidadExistenteTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")
        self.record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=self.record,
            archivo=SimpleUploadedFile("acta.txt", TEXTO.encode()),
        )
        extraer_texto_de_instanciacion(inst)
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santa Fe",  # forma alterna del nombre
            evidencia="Cabildo de Santafé", confianza=0.9,
        )]
        [self.propuesta] = generar_propuestas(self.record, ProveedorFalso(candidatos))

    def test_vincular_a_entidad_existente_no_crea_duplicado(self):
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")  # ya existía, con otra grafía
        self.propuesta.validar(self.archivista, aceptar=True, entidad_existente=cabildo)

        self.assertEqual(CorporateBody.objects.count(), 1)  # no se creó "Cabildo de Santa Fe"
        rel = RelacionRiC.objects.get(relacion_id="R027")
        self.assertEqual(rel.destino, cabildo)
        self.assertEqual(rel.estado, "modificada")  # se vinculó a algo distinto de lo propuesto

    def test_vincular_a_entidad_de_tipo_incorrecto_falla(self):
        from ric.models import Person

        persona = Person.objects.create(nombre="Alguien")
        with self.assertRaises(ValueError):
            self.propuesta.validar(self.archivista, aceptar=True, entidad_existente=persona)
