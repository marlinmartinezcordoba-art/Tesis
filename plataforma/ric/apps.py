from django.apps import AppConfig


class RicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ric"
    verbose_name = "Motor RiC"

    def ready(self):
        from .auditoria_acciones import conectar_senales

        conectar_senales()
