from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    """M8 (RF-M8-01): búsqueda en el catálogo sin distinguir tildes."""

    dependencies = [
        ("ric", "0022_modulo6_revision"),
    ]

    operations = [UnaccentExtension()]
