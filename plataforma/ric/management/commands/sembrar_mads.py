"""Siembra de M5 con los instrumentos reales del Ministerio de Ambiente y
Desarrollo Sostenible (MADS): el organigrama (62 dependencias, 49
funcionarios) y las 54 Tablas de Retención Documental oficiales V2 2022
(380 series/subseries con su retención, disposición final y tipos
documentales).

    python manage.py sembrar_mads [--usuario NOMBRE]

Idempotente: se puede correr las veces que haga falta; busca por código y
nombre y solo actualiza lo que cambió. Es lo mismo que el botón «Cargar
semilla MADS» de la pantalla de vocabularios.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from ric import instrumentos


class Command(BaseCommand):
    help = "Carga el organigrama y las TRD del MADS en el vocabulario (M5)."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", default="", help="Cuenta a la que se atribuye la carga (por defecto, el primer superusuario).")

    def handle(self, *args, **opciones):
        usuario = None
        if opciones["usuario"]:
            usuario = User.objects.filter(username=opciones["usuario"]).first()
            if usuario is None:
                self.stderr.write(f"No existe la cuenta «{opciones['usuario']}».")
                return
        usuario = usuario or User.objects.filter(is_superuser=True).order_by("pk").first()
        resumen = instrumentos.sembrar_mads(usuario)
        self.stdout.write(self.style.SUCCESS(
            "Semilla MADS cargada: "
            f"{resumen['organigrama']['creadas']} dependencias nuevas, {resumen['organigrama']['funcionarios']} funcionarios nuevos, "
            f"{resumen['trd']['series']} series leídas ({resumen['trd']['mandatos']} mandatos y {resumen['trd']['actividades']} actividades nuevas), "
            f"{resumen['trd']['formas_documentales']} formas documentales nuevas, "
            f"{resumen['organigrama']['relaciones'] + resumen['trd']['relaciones']} relaciones RiC nuevas."
        ))
