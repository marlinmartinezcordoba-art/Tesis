from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ric", "0004_eventoric"),
    ]

    operations = [
        TrigramExtension(),
    ]
