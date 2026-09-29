"""M2 · Aplicación Celery de RICORA: el trabajador que ejecuta el
preprocesamiento (OCR, idioma, calidad y entrega al motor) fuera del
servidor web. Se configura desde settings (prefijo CELERY_)."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("ricora")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
