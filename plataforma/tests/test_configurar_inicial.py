"""Comando `configurar_inicial`: superusuario y proveedor Gemini desde el
entorno del servidor (lo que el despliegue escribe en .env a partir de los
secretos de GitHub), sin consola ni SSH."""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from ric.models import ProveedorIAConfig


def _correr(**entorno):
    salida = StringIO()
    with patch.dict("os.environ", entorno, clear=False):
        for clave in ("RICORA_ADMIN_USER", "RICORA_ADMIN_PASSWORD", "GEMINI_API_KEY"):
            if clave not in entorno:
                import os

                os.environ.pop(clave, None)
        call_command("configurar_inicial", stdout=salida)
    return salida.getvalue()


class ConfigurarInicialTest(TestCase):
    def test_sin_variables_no_toca_nada(self):
        salida = _correr()
        self.assertIn("no se toca", salida)
        self.assertFalse(User.objects.exists())
        self.assertFalse(ProveedorIAConfig.objects.exists())

    def test_crea_y_luego_restablece_el_superusuario(self):
        _correr(RICORA_ADMIN_USER="marlin", RICORA_ADMIN_PASSWORD="ClaveInicial2026")
        marlin = User.objects.get(username="marlin")
        self.assertTrue(marlin.is_superuser and marlin.is_staff)
        self.assertTrue(marlin.check_password("ClaveInicial2026"))
        _correr(RICORA_ADMIN_USER="marlin", RICORA_ADMIN_PASSWORD="OtraClave2027")
        self.assertEqual(User.objects.filter(username="marlin").count(), 1)
        self.assertTrue(User.objects.get(username="marlin").check_password("OtraClave2027"))

    def test_registra_y_activa_gemini_si_la_conexion_funciona(self):
        with patch("ric.proveedores.probar_conexion", return_value=(True, "Conexión correcta con Gemini")):
            salida = _correr(GEMINI_API_KEY="AIza-prueba")
        self.assertIn("activado como fuente", salida)
        config = ProveedorIAConfig.objects.get()
        self.assertTrue(config.activo)
        self.assertEqual(config.clave_api, "AIza-prueba")
        self.assertNotIn("AIza-prueba", salida)

    def test_no_activa_si_la_conexion_falla_y_no_pisa_un_proveedor_activo(self):
        with patch("ric.proveedores.probar_conexion", return_value=(False, "La clave de API de Gemini no es válida.")):
            salida = _correr(GEMINI_API_KEY="mala")
        self.assertIn("NO activado", salida)
        self.assertFalse(ProveedorIAConfig.objects.get().activo)
        ProveedorIAConfig.objects.create(proveedor="claude", activo=True, prueba_exitosa=True)
        salida = _correr(GEMINI_API_KEY="otra")
        self.assertIn("ya hay un proveedor de IA activo", salida)
        self.assertEqual(ProveedorIAConfig.objects.filter(activo=True).count(), 1)
