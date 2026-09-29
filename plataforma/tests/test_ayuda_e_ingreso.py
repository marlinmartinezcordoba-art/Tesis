"""Ayuda en cada pantalla (ícono de ambulancia), pantalla de ingreso y retiro
(reversible) de los datos de prueba que dejó el desarrollo."""

import importlib

from django.apps import apps
from django.urls import reverse

from ric import ayuda
from ric.models import Person

from ._ayudas import CasoModulos


class AyudaTest(CasoModulos):
    def test_cada_pantalla_principal_tiene_su_ayuda(self):
        self.client.force_login(self.archivista)
        for nombre in ("inicio", "ingesta", "analisis_lista", "revision_lista", "catalogo", "panel", "vocabularios"):
            resp = self.client.get(reverse(nombre))
            self.assertContains(resp, 'id="abrir-ayuda"', msg_prefix=nombre)
            self.assertContains(resp, f'<h2 id="ayuda-titulo">{ayuda.guia_de(nombre)["titulo"]}</h2>', msg_prefix=nombre)

    def test_ayuda_con_ambulancia_y_sin_guia_aparte(self):
        self.client.force_login(self.archivista)
        resp = self.client.get(reverse("revision_lista"))
        self.assertContains(resp, 'aria-label="Ayuda: cómo se usa esta pantalla"')
        self.assertContains(resp, "<svg")
        self.assertNotContains(resp, "Guía de uso")
        self.assertNotContains(resp, "guía completa")
        self.assertEqual(self.client.get("/ayuda/").status_code, 404)

    def test_guias_bien_formadas(self):
        claves = [g["clave"] for g in ayuda.GUIAS]
        self.assertEqual(len(claves), len(set(claves)))
        for g in ayuda.GUIAS:
            self.assertTrue(g["para_que"] and g["pasos"], g["clave"])
        self.assertEqual(ayuda.guia_de("admin_parametros")["clave"], "admin_usuarios")

    def test_pantallas_sin_codigos_de_desarrollo(self):
        self.client.force_login(self.archivista)
        for nombre in ("inicio", "ingesta", "analisis_lista", "revision_lista", "panel", "exportar"):
            html = self.client.get(reverse(nombre)).content.decode()
            for residuo in ("RF-M", "(CC-0", "Laboratorio de métricas", "(M2)", "(M6)"):
                self.assertNotIn(residuo, html, f"{nombre}: {residuo}")


class IngresoTest(CasoModulos):
    def test_ingreso_presenta_la_plataforma(self):
        resp = self.client.get(reverse("ric_login"))
        self.assertContains(resp, "descrita en contexto")
        self.assertContains(resp, 'id="ver-clave"')
        self.assertContains(resp, "RiC-CM 1.0 y RiC-O 1.1")

    def test_error_de_credenciales_se_muestra(self):
        resp = self.client.post(reverse("ric_login"), {"username": "nadie", "password": "mal"})
        self.assertContains(resp, "Usuario o contraseña incorrectos")


class RetiroDatosPruebaTest(CasoModulos):
    def test_retira_con_borrado_logico_y_respeta_lo_real(self):
        prueba = Person.objects.create(nombre="María Rodríguez (F10)")
        real = Person.objects.create(nombre="María Rodríguez")
        mig = importlib.import_module("ric.migrations.0026_retirar_datos_de_prueba")
        mig.retirar(apps, None)
        prueba = Person.todos.get(pk=prueba.pk); real = Person.todos.get(pk=real.pk)
        self.assertTrue(prueba.eliminado)
        self.assertIn("Dato de prueba", prueba.motivo_eliminacion)
        self.assertFalse(real.eliminado)
        self.assertFalse(Person.objects.filter(pk=prueba.pk).exists())  # fuera de las listas, recuperable desde Eliminados
