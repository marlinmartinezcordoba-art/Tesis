"""Pruebas del panel de inicio y la lista de registros: el punto de
entrada pensado para uso diario, en vez del admin de Django."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ric.models import PropuestaRiC, Record, RecordSet


class InicioTest(TestCase):
    def setUp(self):
        # is_staff=True: el único login disponible hoy es el del admin de
        # Django (AdminAuthenticationForm), que exige is_staff.
        self.archivista = User.objects.create_user("archivista", password="x", is_staff=True)

    def test_requiere_login(self):
        resp = self.client.get(reverse("ric_inicio"))
        self.assertEqual(resp.status_code, 302)

    def test_muestra_el_conteo_de_pendientes(self):
        record = Record.objects.create(nombre="Acta")
        PropuestaRiC.objects.create(
            origen=record, relacion_id="R027", entidad_tipo="E11", entidad_nombre="Cabildo",
            proveedor="falso", confianza=0.9,
        )
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_inicio"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["pendientes"], 1)
        self.assertContains(resp, "Bandeja de validación")

    def test_login_sin_next_redirige_al_inicio(self):
        resp = self.client.post(reverse("admin:login"), {
            "username": "archivista", "password": "x",
        }, follow=True)
        self.assertEqual(resp.redirect_chain[-1][0], reverse("ric_inicio"))


class RegistrosTest(TestCase):
    def setUp(self):
        self.archivista = User.objects.create_user("archivista", password="x")

    def test_requiere_login(self):
        resp = self.client.get(reverse("ric_registros"))
        self.assertEqual(resp.status_code, 302)

    def test_lista_registros_con_enlaces_al_grafo_y_rdf(self):
        fondo = RecordSet.objects.create(nombre="Fondo Independencia")
        record = Record.objects.create(nombre="Acta del Cabildo", record_set=fondo, tipo_forma_documental="acta")
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_registros"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Acta del Cabildo")
        self.assertContains(resp, "Fondo Independencia")
        self.assertContains(resp, reverse("ric_grafo", args=["record", record.pk]))
        self.assertContains(resp, reverse("ric_exportar_rdf", args=["record", record.pk]))

    def test_sin_registros_muestra_aviso(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("ric_registros"))
        self.assertContains(resp, "Todavía no hay registros")
