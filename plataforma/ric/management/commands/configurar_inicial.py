"""Configuración inicial del servidor a partir de variables de entorno,
pensada para correr en cada arranque del contenedor (docker-entrypoint):

- RICORA_ADMIN_USER / RICORA_ADMIN_PASSWORD: crea la cuenta superusuario
  si no existe, o restablece su contraseña si ya existe. Así la usuaria
  recupera el acceso desde los secretos de GitHub, sin consola ni SSH.
- GEMINI_API_KEY: si hay clave y todavía no hay ningún proveedor de IA
  activo, registra Gemini (M11) con esa clave, prueba la conexión y lo
  activa si la prueba pasa. Idempotente: no duplica ni pisa un proveedor
  que ya esté activo.

Nunca imprime las claves."""

import os

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from ric import proveedores
from ric.models import ProveedorIAConfig


class Command(BaseCommand):
    help = "Crea/restablece el superusuario y activa Gemini a partir de variables de entorno."

    def handle(self, *args, **opciones):
        self._superusuario()
        self._gemini()

    def _superusuario(self):
        usuario = os.environ.get("RICORA_ADMIN_USER", "").strip()
        clave = os.environ.get("RICORA_ADMIN_PASSWORD", "")
        if not usuario or not clave:
            self.stdout.write("Superusuario: sin RICORA_ADMIN_USER/PASSWORD en el entorno; no se toca.")
            return
        cuenta, creada = User.objects.get_or_create(username=usuario, defaults={"is_staff": True, "is_superuser": True, "is_active": True})
        cuenta.is_staff = cuenta.is_superuser = cuenta.is_active = True
        cuenta.set_password(clave)
        cuenta.save()
        self.stdout.write(f"Superusuario «{usuario}» {'creado' if creada else 'actualizado'} (contraseña restablecida).")

    def _gemini(self):
        clave = os.environ.get("GEMINI_API_KEY", "").strip()
        if not clave:
            self.stdout.write("Gemini: sin GEMINI_API_KEY en el entorno; no se toca.")
            return
        if ProveedorIAConfig.objects.filter(activo=True).exists():
            self.stdout.write("Gemini: ya hay un proveedor de IA activo; no se cambia.")
            return
        modelo = settings.MAZUCA_MODELO_IA_GEMINI
        config, creado = ProveedorIAConfig.objects.get_or_create(
            proveedor=ProveedorIAConfig.Proveedor.GEMINI, modelo=modelo, defaults={"clave_api": clave},
        )
        if not creado and config.clave_api != clave:
            config.clave_api = clave
        exitosa, mensaje = proveedores.probar_conexion(config)
        config.prueba_exitosa = exitosa
        config.mensaje_prueba = mensaje
        config.ultima_prueba = timezone.now()
        config.activo = exitosa
        config.save()
        self.stdout.write(f"Gemini ({modelo}): {mensaje} {'→ activado como fuente del motor.' if exitosa else '→ NO activado.'}")
