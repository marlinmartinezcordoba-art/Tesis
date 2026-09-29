"""F10 (Desambiguación): "detectar sola cuando una persona o entidad nueva
podría ser un duplicado de una que ya existe, y sugerirlo" — antes de
esto no existía en ningún lado; solo se podía vincular a mano cuando el
archivista mismo reconocía el duplicado por su cuenta.

UMBRAL_SIMILITUD (0.5) se calibró con `similarity()` real de PostgreSQL
contra pares conocidos (ver el docstring de ric.desambiguacion); estas
pruebas usan esos mismos pares para no depender de un número arbitrario.
"""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from ric import desambiguacion
from ric.models import CorporateBody, Person, Place, Record

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class CandidatosSimilaresTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_detecta_una_variante_de_tilde(self):
        existente = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        resultado = desambiguacion.candidatos_similares(CorporateBody, "Cabildo de Santa Fe")
        self.assertIn(existente, resultado)

    def test_detecta_un_nombre_con_apellido_agregado(self):
        existente = Person.objects.create(nombre="Juan Pérez")
        resultado = desambiguacion.candidatos_similares(Person, "Juan Pérez Gómez")
        self.assertIn(existente, resultado)

    def test_no_reporta_entidades_realmente_distintas(self):
        CorporateBody.objects.create(nombre="Cabildo de Cartagena")
        resultado = desambiguacion.candidatos_similares(CorporateBody, "Cabildo de Santafé")
        self.assertEqual(resultado, [])

    def test_no_reporta_una_coincidencia_exacta_de_nombre(self):
        # el nombre exacto ya lo maneja get_or_create() en PropuestaRiC.validar();
        # esto es solo para el caso que esa coincidencia exacta no cubre.
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        resultado = desambiguacion.candidatos_similares(CorporateBody, "Cabildo de Santafé")
        self.assertEqual(resultado, [])

    def test_nombre_vacio_no_devuelve_nada(self):
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        self.assertEqual(desambiguacion.candidatos_similares(CorporateBody, ""), [])

    def test_excluye_la_propia_entidad_por_pk(self):
        entidad = Place.objects.create(nombre="Santafé de Bogotá")
        Place.objects.create(nombre="Santa Fe de Bogotá")
        resultado = desambiguacion.candidatos_similares(Place, entidad.nombre, excluir_pk=entidad.pk)
        self.assertNotIn(entidad, resultado)


@override_settings(MEDIA_ROOT=MEDIA)
class ParesSimilaresTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_encuentra_un_par_ya_existente_sin_ninguna_propuesta_de_por_medio(self):
        a = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        b = CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        pares = desambiguacion.pares_similares(CorporateBody)
        self.assertEqual(len(pares), 1)
        self.assertEqual({pares[0][0].pk, pares[0][1].pk}, {a.pk, b.pk})

    def test_no_duplica_el_mismo_par_en_ambos_sentidos(self):
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        pares = desambiguacion.pares_similares(CorporateBody)
        self.assertEqual(len(pares), 1)

    def test_sin_duplicados_no_hay_pares(self):
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        CorporateBody.objects.create(nombre="Alcaldía de Bogotá")
        self.assertEqual(desambiguacion.pares_similares(CorporateBody), [])


@override_settings(MEDIA_ROOT=MEDIA)
class AvisoEnElAnalisisTest(TestCase):
    """El aviso debe llegar hasta la ficha del motor de análisis (M3), no
    solo existir en el módulo de desambiguación."""

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(self.archivista)

    def _propuesta(self, nombre):
        from django.contrib.contenttypes.models import ContentType

        from ric.models import PropuestaRiC

        record = Record.objects.create(nombre="Acta")
        PropuestaRiC.objects.create(
            origen_content_type=ContentType.objects.get_for_model(Record),
            origen_object_id=record.pk,
            relacion_id="R027", entidad_tipo="E11", entidad_nombre=nombre,
            proveedor="falso", version_modelo="0", confianza=0.8,
        )
        return record

    def test_avisa_cuando_el_nombre_propuesto_se_parece_a_uno_existente(self):
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        record = self._propuesta("Cabildo de Santa Fe")
        respuesta = self.client.get(reverse("analisis", args=[record.pk]))
        self.assertContains(respuesta, "Se parece a")  # F10: sugiere el posible duplicado, la persona decide
        self.assertContains(respuesta, "⚠")

    def test_no_avisa_cuando_no_hay_nada_parecido(self):
        record = self._propuesta("Cabildo de Santafé")
        respuesta = self.client.get(reverse("analisis", args=[record.pk]))
        self.assertNotContains(respuesta, "Se parece a")
        self.assertNotContains(respuesta, "Ya existe en vocabularios")


@override_settings(MEDIA_ROOT=MEDIA)
class PantallaDeDuplicadosTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.invitado = User.objects.create_user("consulta", password="x", is_staff=False)

    def test_consulta_puede_verla_pero_sin_fusionar(self):
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        self.client.force_login(self.invitado)
        respuesta = self.client.get(reverse("vocabularios_duplicados"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cabildo de Santa Fe")

    def test_lista_un_par_encontrado_con_enlace_a_las_fichas(self):
        self.client.force_login(self.archivista)
        a = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        respuesta = self.client.get(reverse("vocabularios_duplicados"))
        self.assertContains(respuesta, "Cabildo de Santafé")
        self.assertContains(respuesta, "Cabildo de Santa Fe")
        self.assertContains(respuesta, reverse("vocabulario_ficha", args=["corporatebody", a.pk]))

    def test_sin_nada_parecido_dice_que_no_hay_pares(self):
        self.client.force_login(self.archivista)
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        respuesta = self.client.get(reverse("vocabularios_duplicados"))
        self.assertContains(respuesta, "No se detectan entradas parecidas")

    def test_recordset_no_aparece_en_la_pantalla_de_duplicados(self):
        # RecordSet no es fusionable (ver ric.fusion); no debería ofrecerse
        # aquí como si lo fuera, aunque dos nombres se parezcan.
        from ric.models import RecordSet

        self.client.force_login(self.archivista)
        RecordSet.objects.create(nombre="Fondo Notarial")
        RecordSet.objects.create(nombre="Fondo Notarial ")
        respuesta = self.client.get(reverse("vocabularios_duplicados"))
        self.assertNotContains(respuesta, "Fondo Notarial")
