"""M5 · Vocabularios y autoridades (/vocabularios): RF-M5-01 a RF-M5-04."""

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from ric.models import CorporateBody, FormaDocumental, Group, Person, Place, Record, RelacionRiC, VersionRiC

from ._ayudas import CasoModulos, candidato


class VocabulariosTest(CasoModulos):
    def setUp(self):
        super().setUp()
        self.cabildo = CorporateBody.objects.create(nombre="Cabildo de Santafé", creado_por=self.archivista)
        Person.objects.create(nombre="José Acevedo y Gómez")
        Place.objects.create(nombre="Bogotá")
        Record.objects.create(nombre="Acta")

    def test_todos_los_roles_pueden_consultar(self):
        for usuario in (self.consulta, self.revisor, self.archivista):
            self.client.force_login(usuario)
            resp = self.client.get(reverse("vocabularios"))
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "Cabildo de Santafé")

    def test_catalogo_unico_sin_documentos_y_con_formas_documentales(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("vocabularios"))
        self.assertNotContains(resp, ">Acta<")  # los documentos van al catálogo, no a autoridades
        self.assertContains(resp, "Formas documentales")
        self.assertContains(resp, "Entidades corporativas <strong>1</strong>")
        self.assertContains(resp, "creado_por".replace("creado_por", "archivista"))  # RF-M5-04 en la tabla

    def test_un_corporatebody_no_se_cuenta_tambien_como_grupo(self):
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("vocabularios"), {"tipo": "group"})
        self.assertNotContains(resp, "Cabildo de Santafé")
        self.assertEqual(Group.objects.count(), 1)  # herencia multitabla: la fila existe, pero no es "propia"

    def test_buscar_una_entrada_existente_antes_de_crear(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabularios"), {"q": "cabildo"})
        self.assertContains(resp, "Cabildo de Santafé")
        self.assertNotContains(resp, "José Acevedo")

    def test_crear_forma_documental_con_serie_trd(self):
        self.client.force_login(self.archivista)
        resp = self.client.post(reverse("vocabularios"), {"nombre": "Acta", "definicion": "Registro de una reunión", "serie_trd": "100.02 Actas"}, follow=True)
        self.assertContains(resp, "creada")
        forma = FormaDocumental.objects.get(nombre="Acta")
        self.assertEqual(forma.serie_trd, "100.02 Actas")  # RF-M5-03
        self.assertEqual(forma.creado_por, self.archivista)
        resp = self.client.post(reverse("vocabularios"), {"nombre": "Acta"}, follow=True)
        self.assertContains(resp, "ya existía")  # RF-M5-02
        self.assertEqual(FormaDocumental.objects.count(), 1)

    def test_consulta_no_crea_entradas(self):
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("vocabularios"), {"nombre": "Acta"}, follow=True)
        self.assertContains(resp, "Solo una cuenta archivista")
        self.assertFalse(FormaDocumental.objects.exists())

    def test_ficha_muestra_trazabilidad_y_permite_editar_con_registro(self):
        self.client.force_login(self.archivista)
        url = reverse("vocabulario_ficha", args=["corporatebody", self.cabildo.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "Trazabilidad de la entrada")
        self.assertContains(resp, "archivista")
        resp = self.client.post(url, {"nombre": "Cabildo de Santafé", "identificador": "CO-CAB-01", "descripcion_general": "", "serie_trd": "200.01"}, follow=True)
        self.assertContains(resp, "actualizada")
        self.cabildo.refresh_from_db()
        self.assertEqual(self.cabildo.serie_trd, "200.01")
        self.assertEqual(self.cabildo.modificado_por, self.archivista)  # RF-M5-04
        self.assertTrue(VersionRiC.objects.filter(content_type=ContentType.objects.get_for_model(CorporateBody), object_id=self.cabildo.pk).exists())

    def test_ficha_lista_documentos_y_relaciones_validadas(self):
        record, inst = self.documento(nombre="Acta del 20 de julio")
        [p] = self.proponer(record, candidato())
        p.validar(self.archivista, aceptar=True)
        self.client.force_login(self.consulta)
        resp = self.client.get(reverse("vocabulario_ficha", args=["corporatebody", self.cabildo.pk]))
        self.assertContains(resp, "Acta del 20 de julio")
        self.assertContains(resp, "has creator")

    def test_duplicados_y_fusion_desde_la_ficha(self):
        duplicada = CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        record = Record.objects.create(nombre="Otra acta")
        RelacionRiC.objects.create(relacion_id="R027", origen=record, destino=duplicada)
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("vocabularios_duplicados"))
        self.assertContains(resp, "Cabildo de Santa Fe")
        resp = self.client.get(reverse("vocabulario_ficha", args=["corporatebody", self.cabildo.pk]))
        self.assertContains(resp, "Fusionar en esta")
        resp = self.client.post(reverse("vocabulario_fusionar", args=["corporatebody", self.cabildo.pk]), {"duplicada": duplicada.pk}, follow=True)
        self.assertContains(resp, "fusionada en")
        self.assertFalse(CorporateBody.objects.filter(pk=duplicada.pk).exists())
        self.assertEqual(RelacionRiC.objects.get(relacion_id="R027").destino, self.cabildo)

    def test_consulta_no_fusiona(self):
        duplicada = CorporateBody.objects.create(nombre="Cabildo de Santa Fe")
        self.client.force_login(self.consulta)
        resp = self.client.post(reverse("vocabulario_fusionar", args=["corporatebody", self.cabildo.pk]), {"duplicada": duplicada.pk}, follow=True)
        self.assertContains(resp, "requiere el rol archivista")
        self.assertTrue(CorporateBody.objects.filter(pk=duplicada.pk).exists())
