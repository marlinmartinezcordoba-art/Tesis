"""Entidades RiC: pantalla nueva para ver TODAS las entidades ya guardadas,
de cualquier tipo del catálogo RiC-CM — antes solo se podían ver una por
una en el admin de Django, o los Record en "Registros"."""

import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from ric.models import CorporateBody, Person, Place, Record

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class EntidadesHtmlTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)
        self.client.force_login(self.archivista)

    def test_requiere_login(self):
        self.client.logout()
        resp = self.client.get(reverse("ric_entidades"))
        self.assertEqual(resp.status_code, 302)

    def test_invitado_de_consulta_puede_verla(self):
        invitado = User.objects.create_user("consulta", password="x", is_staff=False)
        self.client.force_login(invitado)
        resp = self.client.get(reverse("ric_entidades"))
        self.assertEqual(resp.status_code, 200)

    def test_sin_entidades_el_total_es_cero(self):
        resp = self.client.get(reverse("ric_entidades"))
        self.assertEqual(resp.context["total_entidades"], 0)
        self.assertContains(resp, "Todavía no hay entidades")

    def test_muestra_entidades_de_distintos_tipos_sin_filtro(self):
        Record.objects.create(nombre="Acta del Cabildo")
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        Person.objects.create(nombre="Juan Pérez")
        resp = self.client.get(reverse("ric_entidades"))
        self.assertContains(resp, "Acta del Cabildo")
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertContains(resp, "Juan Pérez")
        self.assertEqual(resp.context["total_entidades"], 3)

    def test_un_corporatebody_no_se_cuenta_tambien_como_group(self):
        # herencia multitabla: CorporateBody(Group) tiene fila también en
        # la tabla de Group — sin excluirla, "Grupo" y "Entidad corporativa"
        # contarían la misma fila dos veces.
        from ric.models import Group

        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        Group.objects.create(nombre="Junta vecinal (grupo genérico)")
        resp = self.client.get(reverse("ric_entidades"))
        catalogo = {c["nombre"]: c["total"] for c in resp.context["catalogo"]}
        self.assertEqual(catalogo["Entidad corporativa"], 1)
        self.assertEqual(catalogo["Grupo"], 1)
        self.assertEqual(resp.context["total_entidades"], 2)

    def test_filtrar_por_group_no_trae_los_corporatebody(self):
        from ric.models import Group

        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        Group.objects.create(nombre="Junta vecinal (grupo genérico)")
        resp = self.client.get(reverse("ric_entidades"), {"tipo": "group"})
        self.assertContains(resp, "Junta vecinal")
        self.assertNotContains(resp, "Cabildo de Santafé")

    def test_el_catalogo_cuenta_cada_tipo_por_separado(self):
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        Person.objects.create(nombre="Juan Pérez")
        Person.objects.create(nombre="María López")
        resp = self.client.get(reverse("ric_entidades"))
        catalogo = {c["nombre"]: c["total"] for c in resp.context["catalogo"]}
        self.assertEqual(catalogo["Persona"], 2)
        self.assertEqual(catalogo["Entidad corporativa"], 1)

    def test_filtrar_por_tipo_solo_muestra_ese_tipo(self):
        CorporateBody.objects.create(nombre="Cabildo de Santafé")
        Person.objects.create(nombre="Juan Pérez")
        resp = self.client.get(reverse("ric_entidades"), {"tipo": "person"})
        self.assertContains(resp, "Juan Pérez")
        self.assertNotContains(resp, "Cabildo de Santafé")

    def test_buscar_por_nombre_filtra_dentro_del_tipo(self):
        Person.objects.create(nombre="Juan Pérez")
        Person.objects.create(nombre="María López")
        resp = self.client.get(reverse("ric_entidades"), {"tipo": "person", "q": "Juan"})
        self.assertContains(resp, "Juan Pérez")
        self.assertNotContains(resp, "María López")

    def test_buscar_sin_filtro_de_tipo_tambien_filtra(self):
        Person.objects.create(nombre="Juan Pérez")
        Place.objects.create(nombre="Santafé de Bogotá")
        resp = self.client.get(reverse("ric_entidades"), {"q": "Bogotá"})
        self.assertContains(resp, "Santafé de Bogotá")
        self.assertNotContains(resp, "Juan Pérez")

    def test_tipo_desconocido_en_la_url_no_revienta(self):
        resp = self.client.get(reverse("ric_entidades"), {"tipo": "no-existe"})
        self.assertEqual(resp.status_code, 200)

    def test_cada_fila_enlaza_a_su_grafo_y_su_rdf(self):
        persona = Person.objects.create(nombre="Juan Pérez")
        resp = self.client.get(reverse("ric_entidades"), {"tipo": "person"})
        self.assertContains(resp, reverse("ric_grafo", args=["person", persona.pk]))
        self.assertContains(resp, reverse("ric_exportar_rdf", args=["person", persona.pk]))
