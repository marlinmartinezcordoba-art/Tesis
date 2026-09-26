"""Pruebas de la capa de IA multimodal del núcleo `ric` (Entregable 3,
T030-T033): el AIProvider abstracto, la verificación de evidencia y el
motor de reglas aplicados a las propuestas, y la validación humana que
convierte una PropuestaRiC en grafo real.
"""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from ric.extraccion import extraer_texto_de_instanciacion
from ric.models import CorporateBody, Instantiation, PropuestaRiC, Record, RelacionRiC
from ric.proveedor_local import ProveedorLocal
from ric.proveedores import CONFIANZA_SIN_EVIDENCIA, PropuestaCandidata, ProveedorIA, generar_propuestas

MEDIA = tempfile.mkdtemp()

TEXTO = (
    "Acta de la sesión del Cabildo de Santafé, 20 de julio de 1810, en la que "
    "José Acevedo y Gómez presidió la reunión sobre el levantamiento popular."
)


class ProveedorFalso(ProveedorIA):
    nombre = "falso"
    version = "0"

    def __init__(self, candidatos):
        self._candidatos = candidatos

    def proponer(self, record, texto):
        return self._candidatos


@override_settings(MEDIA_ROOT=MEDIA)
class GenerarPropuestasTest(TestCase):
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
        extraer_texto_de_instanciacion(self.inst)

    def test_propuesta_con_evidencia_real_queda_pendiente(self):
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia="Cabildo de Santafé", confianza=0.9, justificacion="firma el acta",
        )]
        propuestas = generar_propuestas(self.record, ProveedorFalso(candidatos))
        self.assertEqual(len(propuestas), 1)
        p = propuestas[0]
        self.assertEqual(p.estado, "pendiente")
        self.assertTrue(p.evidencia.verificada)
        self.assertEqual(p.confianza, 0.9)

    def test_propuesta_con_evidencia_inventada_baja_la_confianza_pero_no_se_descarta(self):
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia="esto no está en el texto", confianza=0.9, justificacion="x",
        )]
        [p] = generar_propuestas(self.record, ProveedorFalso(candidatos))
        self.assertFalse(p.evidencia.verificada)
        self.assertLessEqual(p.confianza, CONFIANZA_SIN_EVIDENCIA)
        self.assertEqual(p.estado, "pendiente")  # sigue pendiente: la evidencia dudosa no es motivo de rechazo automático

    def test_relacion_id_inexistente_se_rechaza_automaticamente(self):
        candidatos = [PropuestaCandidata(
            relacion_id="R043", entidad_tipo="E08", entidad_nombre="Alguien",
            evidencia="Cabildo", confianza=0.9,
        )]
        [p] = generar_propuestas(self.record, ProveedorFalso(candidatos))
        self.assertEqual(p.estado, "rechazada")
        self.assertIn("R043", p.motivo_decision)

    def test_dominio_rango_incompatible_se_rechaza_automaticamente(self):
        # R070 'is birth date of': dominio Date, no Record -> el origen no encaja.
        candidatos = [PropuestaCandidata(
            relacion_id="R070", entidad_tipo="E08", entidad_nombre="Alguien",
            evidencia="Cabildo", confianza=0.9,
        )]
        [p] = generar_propuestas(self.record, ProveedorFalso(candidatos))
        self.assertEqual(p.estado, "rechazada")

    def test_tipo_de_entidad_incompatible_con_la_relacion_se_rechaza(self):
        # R070 aplicado a una relación válida de Record (R027) pero con un
        # entidad_tipo que no es Agent (aquí, Place=E22) debe rechazarse.
        candidatos = [PropuestaCandidata(
            relacion_id="R027", entidad_tipo="E22", entidad_nombre="Santafé",
            evidencia="Santafé", confianza=0.9,
        )]
        [p] = generar_propuestas(self.record, ProveedorFalso(candidatos))
        self.assertEqual(p.estado, "rechazada")
        self.assertIn("Place", p.motivo_decision)

    def test_proveedor_local_reconoce_entidades_con_relacion_generica(self):
        propuestas = generar_propuestas(self.record, ProveedorLocal())
        tipos = {p.entidad_tipo for p in propuestas}
        # spaCy distingue persona de lugar/institución, pero no siempre acierta
        # cuál de las dos últimas es (limitación conocida, ver proveedor_local.py).
        self.assertIn("E08", tipos)  # José Acevedo y Gómez
        self.assertTrue(tipos & {"E11", "E22"})  # alguna entidad institucional o de lugar
        self.assertTrue(all(p.relacion_id == "R019" for p in propuestas))
        self.assertTrue(all(p.estado == "pendiente" for p in propuestas))


@override_settings(MEDIA_ROOT=MEDIA)
class ValidarPropuestaTest(TestCase):
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
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santafé",
            evidencia="Cabildo de Santafé", confianza=0.9, justificacion="firma el acta",
        )]
        [self.propuesta] = generar_propuestas(self.record, ProveedorFalso(candidatos))

    def test_aceptar_crea_la_entidad_y_la_relacion(self):
        self.propuesta.validar(self.archivista, aceptar=True)
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, "aceptada")

        cabildo = CorporateBody.objects.get(nombre="Cabildo de Santafé")
        rel = RelacionRiC.objects.get(relacion_id="R027", origen_object_id=self.record.pk)
        self.assertEqual(rel.destino, cabildo)
        self.assertEqual(rel.estado, "aceptada")
        self.assertEqual(rel.validado_por, self.archivista)

    def test_aceptar_con_correccion_de_nombre_queda_modificada(self):
        self.propuesta.validar(self.archivista, aceptar=True, entidad_nombre_final="El Cabildo de Santa Fe de Bogotá")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, "modificada")
        self.assertTrue(CorporateBody.objects.filter(nombre="El Cabildo de Santa Fe de Bogotá").exists())

    def test_rechazar_exige_motivo_y_no_toca_el_grafo(self):
        with self.assertRaises(ValueError):
            self.propuesta.validar(self.archivista, aceptar=False)
        self.propuesta.validar(self.archivista, aceptar=False, motivo="No es el productor, solo lo menciona")
        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, "rechazada")
        self.assertFalse(RelacionRiC.objects.filter(relacion_id="R027").exists())
        self.assertFalse(CorporateBody.objects.filter(nombre="Cabildo de Santafé").exists())

    def test_reutiliza_entidad_existente_por_nombre(self):
        existente = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        self.propuesta.validar(self.archivista, aceptar=True)
        self.assertEqual(CorporateBody.objects.filter(nombre="Cabildo de Santafé").count(), 1)
        rel = RelacionRiC.objects.get(relacion_id="R027")
        self.assertEqual(rel.destino, existente)

    def test_no_se_puede_validar_dos_veces(self):
        self.propuesta.validar(self.archivista, aceptar=True)
        with self.assertRaises(ValueError):
            self.propuesta.validar(self.archivista, aceptar=True)

    def test_requiere_usuario_autenticado(self):
        from django.contrib.auth.models import AnonymousUser

        with self.assertRaises(PermissionError):
            self.propuesta.validar(AnonymousUser(), aceptar=True)
