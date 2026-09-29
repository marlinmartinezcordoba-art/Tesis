"""Verifica que todo el grafo RiC de la plataforma sea conforme con la
ontología oficial RiC-O 1.1 (clases y propiedades existentes, objeto/dato,
dominio y rango). Sale con código 1 si hay hallazgos.

    python manage.py verificar_rico [--base https://mi-dominio/ric/entidad/]"""

from django.core.management.base import BaseCommand

from ric import conformidad, rdf


class Command(BaseCommand):
    help = "Verifica la conformidad del grafo RiC completo con RiC-O 1.1."

    def add_arguments(self, parser):
        parser.add_argument("--base", default="https://ricora.local/ric/entidad/")

    def handle(self, *args, base, **opciones):
        g = rdf.grafo_completo(base)
        hallazgos = conformidad.validar(g, maximo=10_000)
        if not hallazgos:
            self.stdout.write(self.style.SUCCESS(f"Conforme con RiC-O 1.1: {len(g)} tripleta(s) revisadas, 0 hallazgos."))
            return
        for h in hallazgos[:50]:
            self.stdout.write(f"  · {h}")
        self.stdout.write(self.style.ERROR(f"{len(hallazgos)} hallazgo(s) de conformidad en {len(g)} tripleta(s)."))
        raise SystemExit(1)
