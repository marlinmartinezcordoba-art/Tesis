"""F07 (Motor RiC) — versionado (RF-016): "cada entidad/relación conserva
historial de cambios". Antes de esta auditoría el requisito estaba en la
Matriz Maestra pero no existía en ningún lado del código: guardar cambios
sobre una entidad ya existente simplemente sobrescribía sus valores
anteriores sin dejar rastro.
"""

import shutil
import tempfile

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings

from ric.models import CorporateBody, Person, Record, RelacionRiC, VersionRiC

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class VersionadoDeEntidadesTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_crear_una_entidad_no_genera_ninguna_version(self):
        Record.objects.create(nombre="Acta")
        self.assertEqual(VersionRiC.objects.count(), 0)

    def test_editar_una_entidad_guarda_como_estaba_antes(self):
        acta = Record.objects.create(nombre="Acta original", descripcion_general="borrador")
        acta.nombre = "Acta del 20 de julio de 1810"
        acta.descripcion_general = "versión final"
        acta.save()

        self.assertEqual(VersionRiC.objects.count(), 1)
        version = VersionRiC.objects.get()
        self.assertEqual(version.content_type, ContentType.objects.get_for_model(Record))
        self.assertEqual(version.object_id, acta.pk)
        self.assertEqual(version.datos_anteriores["nombre"], "Acta original")
        self.assertEqual(version.datos_anteriores["descripcion_general"], "borrador")

        acta.refresh_from_db()
        self.assertEqual(acta.nombre, "Acta del 20 de julio de 1810")

    def test_varias_ediciones_seguidas_dejan_varias_versiones_en_orden(self):
        acta = Record.objects.create(nombre="v1")
        acta.nombre = "v2"
        acta.save()
        acta.nombre = "v3"
        acta.save()

        versiones = list(VersionRiC.objects.filter(object_id=acta.pk).order_by("fecha"))
        self.assertEqual(len(versiones), 2)
        self.assertEqual(versiones[0].datos_anteriores["nombre"], "v1")
        self.assertEqual(versiones[1].datos_anteriores["nombre"], "v2")

    def test_captura_campos_heredados_por_herencia_multitabla(self):
        # CorporateBody -> Group -> Agent -> Thing: nombre/identificador viven
        # en Thing (abstracto), pero deben quedar igual en la fotografía.
        cabildo = CorporateBody.objects.create(nombre="Cabildo", identificador="AG-001")
        cabildo.identificador = "AG-002"
        cabildo.save()

        version = VersionRiC.objects.get()
        self.assertEqual(version.content_type, ContentType.objects.get_for_model(CorporateBody))
        self.assertEqual(version.datos_anteriores["identificador"], "AG-001")
        self.assertEqual(version.datos_anteriores["nombre"], "Cabildo")

    def test_no_versiona_campos_de_relacion(self):
        serie = Record.objects.create(nombre="Serie")
        serie.nombre = "Serie renombrada"
        serie.save()
        version = VersionRiC.objects.get()
        self.assertNotIn("record_set", version.datos_anteriores)
        self.assertNotIn("record_set_id", version.datos_anteriores)


@override_settings(MEDIA_ROOT=MEDIA)
class VersionadoDeRelacionesTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_crear_una_relacion_no_genera_ninguna_version(self):
        acta = Record.objects.create(nombre="Acta")
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        RelacionRiC.objects.create(relacion_id="R027", origen=acta, destino=cabildo)
        self.assertEqual(VersionRiC.objects.count(), 0)

    def test_editar_una_relacion_guarda_como_estaba_antes(self):
        acta = Record.objects.create(nombre="Acta")
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        rel = RelacionRiC.objects.create(relacion_id="R027", origen=acta, destino=cabildo)

        rel.estado = RelacionRiC.Estado.ACEPTADA
        rel.save()

        version = VersionRiC.objects.get()
        self.assertEqual(version.content_type, ContentType.objects.get_for_model(RelacionRiC))
        self.assertEqual(version.object_id, rel.pk)
        self.assertEqual(version.datos_anteriores["estado"], "pendiente")
        self.assertEqual(version.datos_anteriores["relacion_id"], "R027")

        rel.refresh_from_db()
        self.assertEqual(rel.estado, RelacionRiC.Estado.ACEPTADA)

    def test_editar_una_relacion_invalida_no_guarda_version_falsa(self):
        # full_clean() se ejecuta ANTES de super().save(): si la edición
        # deja la relación inválida, no debe quedar una VersionRiC de un
        # cambio que en realidad nunca se guardó.
        from django.core.exceptions import ValidationError

        from ric.models import Date

        acta = Record.objects.create(nombre="Acta")
        cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé")
        rel = RelacionRiC.objects.create(relacion_id="R027", origen=acta, destino=cabildo)

        fecha = Date.objects.create(nombre="1810")
        rel.destino = fecha
        with self.assertRaises(ValidationError):
            rel.save()

        self.assertEqual(VersionRiC.objects.count(), 0)


class AdminVersionRiCTest(TestCase):
    def test_el_historial_es_de_solo_lectura(self):
        from django.contrib.auth.models import User

        from ric.admin import VersionRiCAdmin

        admin_instance = VersionRiCAdmin(VersionRiC, None)
        self.assertFalse(admin_instance.has_add_permission(None))
        self.assertFalse(admin_instance.has_change_permission(None))
        self.assertFalse(admin_instance.has_delete_permission(None))
