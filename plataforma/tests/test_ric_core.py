"""Pruebas del núcleo RiC-native (app `ric`): jerarquías de entidades reales
(no un solo campo `tipo`) y el motor de reglas que valida cada RelacionRiC
contra ric/fixtures/ric_matrix.json (verificado contra RiC-CM 1.0 / RiC-O 1.1).
"""

import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric import reglas
from ric.models import (
    Activity,
    CorporateBody,
    Date,
    Evidencia,
    Instantiation,
    Person,
    Place,
    Record,
    RecordPart,
    RecordSet,
    RelacionRiC,
)

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class JerarquiaEntidadesTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_record_set_record_part_forman_una_jerarquia(self):
        fondo = RecordSet.objects.create(nombre="Fondo Gobierno Colonial", tipo_conjunto="fondo")
        serie = RecordSet.objects.create(nombre="Actas de Cabildo", tipo_conjunto="serie", padre=fondo)
        acta = Record.objects.create(nombre="Acta del 20 de julio de 1810", record_set=serie)
        firma = RecordPart.objects.create(nombre="Firma del escribano", record_padre=acta)

        self.assertEqual(serie.padre, fondo)
        self.assertIn(serie, fondo.hijos.all())
        self.assertEqual(acta.record_set, serie)
        self.assertIn(firma, acta.partes.all())

    def test_instantiation_pertenece_a_un_record(self):
        acta = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia digital del acta", record_resource=acta,
            archivo=SimpleUploadedFile("acta.txt", b"contenido"),
        )
        inst.calcular_y_guardar_hash()
        inst.save()
        self.assertEqual(inst.record_resource_id, acta.pk)
        self.assertTrue(inst.sha256)
        self.assertIn(inst, acta.instanciaciones.all())

    def test_corporate_body_es_tambien_group_y_agent(self):
        from ric.models import Agent, Group

        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        self.assertIsInstance(cabildo, Group)
        self.assertIsInstance(cabildo, Agent)
        self.assertEqual(Group.objects.filter(pk=cabildo.pk).count(), 1)
        self.assertEqual(Agent.objects.filter(pk=cabildo.pk).count(), 1)


class MotorDeReglasTest(TestCase):
    def test_r043_no_existe_en_la_matriz_verificada(self):
        with self.assertRaises(reglas.RelacionInvalida):
            reglas.entidades_para("R043")

    def test_r001_is_related_to_acepta_cualquier_par_de_entidades(self):
        # dominio y rango = Thing (comodín): no debe lanzar nada.
        cabildo = CorporateBody.objects.create(nombre="Cabildo")
        lugar = Place.objects.create(nombre="Santafé")
        reglas.validar_relacion("R001", cabildo, lugar)  # no debe lanzar

    def test_r027_has_creator_exige_agent_como_destino(self):
        acta = Record.objects.create(nombre="Acta")
        fecha = Date.objects.create(nombre="1810", expresion="20 de julio de 1810")
        with self.assertRaises(reglas.RelacionInvalida):
            reglas.validar_relacion("R027", acta, fecha)  # destino debería ser Agent, no Date

    def test_r027_has_creator_acepta_record_resource_a_agent(self):
        acta = Record.objects.create(nombre="Acta")
        cabildo = CorporateBody.objects.create(nombre="Cabildo")
        reglas.validar_relacion("R027", acta, cabildo)  # no debe lanzar

    def test_info_relacion_trae_uri_rico_verificada(self):
        info = reglas.info_relacion("R027")
        self.assertEqual(info["uri_rico"], "rico:hasCreator")


@override_settings(MEDIA_ROOT=MEDIA)
class RelacionRiCTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_guardar_relacion_valida(self):
        acta = Record.objects.create(nombre="Acta")
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        rel = RelacionRiC(relacion_id="R027", origen=acta, destino=cabildo)
        rel.save()
        self.assertEqual(rel.estado, "pendiente")

    def test_guardar_relacion_invalida_lanza_validationerror(self):
        acta = Record.objects.create(nombre="Acta")
        fecha = Date.objects.create(nombre="1810")
        rel = RelacionRiC(relacion_id="R027", origen=acta, destino=fecha)
        with self.assertRaises(ValidationError):
            rel.save()
        self.assertIsNone(rel.pk)

    def test_relacion_id_inexistente_lanza_validationerror(self):
        acta = Record.objects.create(nombre="Acta")
        cabildo = CorporateBody.objects.create(nombre="Cabildo")
        rel = RelacionRiC(relacion_id="R043", origen=acta, destino=cabildo)
        with self.assertRaises(ValidationError):
            rel.save()

    def test_record_set_productor_via_relacion_r027(self):
        serie = RecordSet.objects.create(nombre="Actas de Cabildo", tipo_conjunto="serie")
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        RelacionRiC.objects.create(relacion_id="R027", origen=serie, destino=cabildo)
        rel = serie.productor()
        self.assertIsNotNone(rel)
        self.assertEqual(rel.destino, cabildo)

    def test_relacion_con_evidencia(self):
        acta = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=acta, archivo=SimpleUploadedFile("a.txt", b"El Cabildo de Santafe...")
        )
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        ev = Evidencia.objects.create(instanciacion=inst, fragmento="El Cabildo de Santafe", verificada=True)
        rel = RelacionRiC.objects.create(relacion_id="R027", origen=acta, destino=cabildo, evidencia=ev)
        self.assertEqual(rel.evidencia, ev)
        self.assertIn(rel, ev.relaciones.all())

    def test_r070_is_birth_date_of_exige_person_no_corporate_body(self):
        fecha = Date.objects.create(nombre="1780", expresion="24 de julio de 1780")
        persona = Person.objects.create(nombre="Simón Bolívar")
        rel = RelacionRiC(relacion_id="R070", origen=fecha, destino=persona)
        rel.save()  # no debe lanzar: Person es válido

        cabildo = CorporateBody.objects.create(nombre="Cabildo")
        rel2 = RelacionRiC(relacion_id="R070", origen=fecha, destino=cabildo)
        with self.assertRaises(ValidationError):
            rel2.save()

    def test_r060_activity_is_or_was_performed_by_agent(self):
        actividad = Activity.objects.create(nombre="Sesión del Cabildo")
        cabildo = CorporateBody.objects.create(nombre="Cabildo")
        rel = RelacionRiC.objects.create(relacion_id="R060", origen=actividad, destino=cabildo)
        self.assertEqual(rel.relacion_id, "R060")
