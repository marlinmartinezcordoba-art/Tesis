from django.core.management.base import BaseCommand, CommandError

from ric.auditoria import reporte_exactitud, seleccionar_muestra


class Command(BaseCommand):
    help = (
        "Selecciona al azar una muestra de relaciones RiC ya aceptadas o "
        "modificadas, para que una persona archivista confirme si la IA "
        "acertó (T071, y fuente real de M03 en el laboratorio de evaluación)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--relacion-id", help='Por ejemplo "R027"; si se omite, de cualquier relación.')
        parser.add_argument("--tamano", type=int, default=10)
        parser.add_argument(
            "--reporte", action="store_true",
            help="En vez de seleccionar, muestra el reporte de exactitud de lo ya revisado.",
        )

    def handle(self, relacion_id, tamano, reporte, **kwargs):
        if reporte:
            r = reporte_exactitud()
            if r["total_revisadas"] == 0:
                self.stdout.write("Aún no hay muestras revisadas.")
                return
            self.stdout.write(
                f"Exactitud de relaciones RiC: {r['exactitud']} % "
                f"({r['correctas']} de {r['total_revisadas']} revisadas)."
            )
            return

        creadas = seleccionar_muestra(tamano, relacion_id=relacion_id)
        if not creadas:
            raise CommandError("No hay relaciones RiC aceptadas sin auditar todavía.")
        self.stdout.write(self.style.SUCCESS(
            f'{len(creadas)} muestra(s) seleccionada(s). Revíselas en el admin, '
            f'en "Muestras de auditoría RiC".'
        ))
