"""F08 (Validación archivista): "Aprobar, corregir, rechazar, vincular a
algo existente, fusionar o separar — la decisión siempre la toma una
persona." Al auditar contra esa descripción de la propia Matriz Maestra,
dos huecos reales:

1. `PropuestaRiC.validar()` ya soportaba `entidad_nombre_final` (corregir
   el nombre antes de aceptar), pero la bandeja de validación no tenía
   ningún campo para escribirlo — solo se podía aceptar tal cual, vincular
   a una existente, o rechazar. "Corregir" no existía en la práctica.
2. "Fusionar" (dos entidades que resultaron ser la misma cosa) no existía
   en ningún lado — ni modelo, ni vista, ni acción de admin.

"Separar" queda deliberadamente sin construir: su semántica (separar en
qué, con qué criterio) es una decisión de diseño que le corresponde a la
usuaria, no algo que se pueda inferir de la auditoría.
"""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ric.evidencia import crear_evidencia
from ric.fusion import ErrorDeFusion, fusionar_entidades
from ric.models import (
    CorporateBody,
    Instantiation,
    PropuestaRiC,
    Record,
    RecordSet,
    RelacionRiC,
    VersionRiC,
)

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class CorregirNombreEnLaBandejaTest(TestCase):
    """El campo de nombre en la bandeja debe llegar hasta `validar()`."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(self.archivista)
        self.record = Record.objects.create(nombre="Acta")
        self.propuesta = PropuestaRiC.objects.create(
            origen_content_type=ContentType.objects.get_for_model(Record),
            origen_object_id=self.record.pk,
            relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo de Santa Fe",
            proveedor="falso", version_modelo="0", confianza=0.9,
        )

    def test_aceptar_con_nombre_corregido_crea_la_entidad_con_el_nombre_correcto(self):
        respuesta = self.client.post(
            reverse("ric_decidir_propuesta", args=[self.propuesta.pk]),
            {"accion": "aceptar", "entidad_nombre_final": "Cabildo de Santafé"},
            follow=True,
        )
        self.assertContains(respuesta, "corregido de")
        entidad = CorporateBody.objects.get()
        self.assertEqual(entidad.nombre, "Cabildo de Santafé")

        self.propuesta.refresh_from_db()
        self.assertEqual(self.propuesta.estado, PropuestaRiC.Estado.MODIFICADA)

    def test_aceptar_sin_tocar_el_nombre_no_dice_corregido(self):
        respuesta = self.client.post(
            reverse("ric_decidir_propuesta", args=[self.propuesta.pk]),
            {"accion": "aceptar", "entidad_nombre_final": "Cabildo de Santa Fe"},
            follow=True,
        )
        self.assertNotContains(respuesta, "corregido de")
        entidad = CorporateBody.objects.get()
        self.assertEqual(entidad.nombre, "Cabildo de Santa Fe")

    def test_aceptar_con_el_campo_vacio_usa_el_nombre_propuesto(self):
        respuesta = self.client.post(
            reverse("ric_decidir_propuesta", args=[self.propuesta.pk]),
            {"accion": "aceptar", "entidad_nombre_final": ""},
            follow=True,
        )
        self.assertNotContains(respuesta, "corregido de")
        entidad = CorporateBody.objects.get()
        self.assertEqual(entidad.nombre, "Cabildo de Santa Fe")


@override_settings(MEDIA_ROOT=MEDIA)
class FusionarEntidadesTest(TestCase):
    """`ric.fusion.fusionar_entidades`: mueve relaciones y propuestas de la
    duplicada a la superviviente, guarda su historia y la borra."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.superviviente = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        self.duplicada = CorporateBody.objects.create(nombre="Cabildo de Santa Fe")

    def test_mueve_relaciones_donde_la_duplicada_es_destino(self):
        record = Record.objects.create(nombre="Acta")
        rel = RelacionRiC.objects.create(relacion_id="R027", origen=record, destino=self.duplicada)
        resultado = fusionar_entidades(self.duplicada, self.superviviente, usuario=self.archivista)

        rel.refresh_from_db()
        self.assertEqual(rel.destino, self.superviviente)
        self.assertEqual(resultado["relaciones_movidas"], 1)

    def test_mueve_relaciones_donde_la_duplicada_es_origen(self):
        from ric.models import Person

        persona = Person.objects.create(nombre="Alguien")
        rel = RelacionRiC.objects.create(relacion_id="R044", origen=self.duplicada, destino=persona)
        resultado = fusionar_entidades(self.duplicada, self.superviviente, usuario=self.archivista)

        rel.refresh_from_db()
        self.assertEqual(rel.origen, self.superviviente)
        self.assertEqual(resultado["relaciones_movidas"], 1)

    def test_mueve_propuestas_pendientes_con_la_duplicada_como_origen(self):
        record = Record.objects.create(nombre="Acta")
        inst = Instantiation.objects.create(
            nombre="Copia", record_resource=record,
            archivo=SimpleUploadedFile("a.txt", b"contenido"),
        )
        ev = crear_evidencia(inst, "contenido")
        propuesta = PropuestaRiC.objects.create(
            origen_content_type=ContentType.objects.get_for_model(CorporateBody),
            origen_object_id=self.duplicada.pk,
            relacion_id="R019", entidad_tipo="E15", entidad_nombre="Algo",
            proveedor="falso", version_modelo="0", confianza=0.5, evidencia=ev,
        )
        resultado = fusionar_entidades(self.duplicada, self.superviviente, usuario=self.archivista)

        propuesta.refresh_from_db()
        self.assertEqual(propuesta.origen_object_id, self.superviviente.pk)
        self.assertEqual(resultado["propuestas_movidas"], 1)

    def test_guarda_una_version_de_la_duplicada_antes_de_borrarla(self):
        duplicada_pk = self.duplicada.pk
        fusionar_entidades(self.duplicada, self.superviviente, usuario=self.archivista)

        version = VersionRiC.objects.get(
            content_type=ContentType.objects.get_for_model(CorporateBody), object_id=duplicada_pk,
        )
        self.assertEqual(version.datos_anteriores["nombre"], "Cabildo de Santa Fe")
        self.assertFalse(CorporateBody.objects.filter(pk=duplicada_pk).exists())

    def test_registra_un_evento_de_fusion_en_la_bitacora(self):
        from ric.models import EventoRiC

        fusionar_entidades(self.duplicada, self.superviviente, usuario=self.archivista)
        evento = EventoRiC.objects.get(tipo=EventoRiC.Tipo.FUSION)
        self.assertEqual(evento.detalle["superviviente_id"], self.superviviente.pk)
        self.assertIn("Cabildo de Santa Fe", evento.detalle["duplicada"])

    def test_no_se_puede_fusionar_entidades_de_distinto_tipo(self):
        record = Record.objects.create(nombre="Acta")
        with self.assertRaises(ErrorDeFusion):
            fusionar_entidades(self.duplicada, record, usuario=self.archivista)

    def test_no_se_puede_fusionar_una_entidad_consigo_misma(self):
        with self.assertRaises(ErrorDeFusion):
            fusionar_entidades(self.duplicada, self.duplicada, usuario=self.archivista)

    def test_recordset_no_es_fusionable(self):
        a = RecordSet.objects.create(nombre="Fondo A")
        b = RecordSet.objects.create(nombre="Fondo A (duplicado)")
        with self.assertRaises(ErrorDeFusion):
            fusionar_entidades(b, a, usuario=self.archivista)
        # ninguno de los dos se tocó
        self.assertTrue(RecordSet.objects.filter(pk=a.pk).exists())
        self.assertTrue(RecordSet.objects.filter(pk=b.pk).exists())


@override_settings(MEDIA_ROOT=MEDIA)
class FusionarDesdeElAdminTest(TestCase):
    """La acción de dos pasos en el admin (elegir cuál sobrevive, luego
    fusionar), igual que "delete_selected" de Django."""

    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="x")
        self.client.force_login(self.admin)
        self.superviviente = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        self.duplicada = CorporateBody.objects.create(nombre="Cabildo de Santa Fe")

    def test_seleccionar_menos_de_dos_no_fusiona_nada(self):
        respuesta = self.client.post(reverse("admin:ric_corporatebody_changelist"), {
            "action": "fusionar_en_otra",
            "_selected_action": [self.superviviente.pk],
        }, follow=True)
        self.assertContains(respuesta, "al menos dos")
        self.assertTrue(CorporateBody.objects.filter(pk=self.duplicada.pk).exists())

    def test_primer_paso_muestra_la_pagina_para_elegir_cual_sobrevive(self):
        respuesta = self.client.post(reverse("admin:ric_corporatebody_changelist"), {
            "action": "fusionar_en_otra",
            "_selected_action": [self.superviviente.pk, self.duplicada.pk],
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cabildo de Santafé")
        self.assertContains(respuesta, "Cabildo de Santa Fe")
        self.assertContains(respuesta, 'name="superviviente"')

    def test_segundo_paso_fusiona_de_verdad(self):
        respuesta = self.client.post(reverse("admin:ric_corporatebody_changelist"), {
            "action": "fusionar_en_otra",
            "_selected_action": [self.superviviente.pk, self.duplicada.pk],
            "confirmar_fusion": "1",
            "superviviente": self.superviviente.pk,
        }, follow=True)
        self.assertContains(respuesta, "Fusionada")
        self.assertFalse(CorporateBody.objects.filter(pk=self.duplicada.pk).exists())
        self.assertTrue(CorporateBody.objects.filter(pk=self.superviviente.pk).exists())

    def test_recordset_no_ofrece_la_accion_de_fusionar(self):
        RecordSet.objects.create(nombre="Fondo A")
        RecordSet.objects.create(nombre="Fondo A (duplicado)")
        respuesta = self.client.get(reverse("admin:ric_recordset_changelist"))
        self.assertNotContains(respuesta, "fusionar_en_otra")
