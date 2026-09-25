from django.core.management.base import BaseCommand, CommandError

from asistencia.auditoria import reporte_exactitud, reporte_sesgo_valoracion, seleccionar_muestra


class Command(BaseCommand):
    help = (
        "Selecciona al azar una muestra de sugerencias aceptadas de clasificación "
        "o valoración, para que una persona archivista confirme si la IA acertó "
        "(lineamientos CLA-04 y VAL-03)."
    )

    def add_arguments(self, parser):
        parser.add_argument("proceso", choices=["clasificacion", "valoracion"])
        parser.add_argument("--tamano", type=int, default=10)
        parser.add_argument(
            "--reporte", action="store_true",
            help="En vez de seleccionar, muestra el reporte de exactitud de lo ya revisado.",
        )

    def handle(self, proceso, tamano, reporte, **kwargs):
        if reporte:
            r = reporte_exactitud(proceso)
            if r["total_revisadas"] == 0:
                self.stdout.write("Aún no hay muestras revisadas para este proceso.")
                return
            self.stdout.write(
                f"Exactitud de {proceso}: {r['exactitud']} % "
                f"({r['correctas']} de {r['total_revisadas']} revisadas)."
            )
            if proceso == "valoracion":
                self.stdout.write("\nDesglose por tipo de valor (VAL-03, sesgo):")
                for campo, datos in reporte_sesgo_valoracion().items():
                    if datos["total_revisadas"]:
                        self.stdout.write(f"  {campo}: {datos['exactitud']} % "
                                           f"({datos['correctas']}/{datos['total_revisadas']})")
                    else:
                        self.stdout.write(f"  {campo}: sin muestras revisadas todavía.")
            return

        creadas = seleccionar_muestra(proceso, tamano)
        if not creadas:
            raise CommandError(
                f"No hay sugerencias aceptadas de «{proceso}» sin auditar todavía."
            )
        self.stdout.write(self.style.SUCCESS(
            f"{len(creadas)} muestra(s) seleccionada(s). Revíselas en el admin, "
            f'en "Muestras de auditoría".'
        ))
