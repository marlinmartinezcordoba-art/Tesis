"""Retira los datos de prueba que dejó el desarrollo en la base (nombres con
marcas como «(F10)», «(dash)», «(demo)» o «Acta de verificación F01»).

Regla del proyecto: nada se elimina de forma irreversible. Se marcan como
eliminados (borrado lógico), con su motivo, y quedan en Administración →
Eliminados, desde donde se pueden restaurar. Sus relaciones siguen el mismo
camino. Corre una sola vez."""

import re

from django.db import migrations
from django.utils import timezone

MARCA = re.compile(
    r"\((F\d{2}|dash|dashboard|demo[^)]*|verificaci[oó]n[^)]*|prueba[^)]*)\)\s*$"
    r"|^Acta de verificaci[oó]n( visual)? F\d{2}$"
    r"|^Motor de análisis RICORA · (demo|falso) ",
    re.IGNORECASE,
)
MOTIVO = "Dato de prueba del desarrollo retirado al dejar la plataforma solo con información real."
# Tablas concretas de más alto nivel (herencia multitabla): marcar ahí marca
# también a sus subtipos, que comparten la fila.
MODELOS = {
    "RecordResource": ("recordresource", "recordset", "record", "recordpart"),
    "Agent": ("agent", "person", "group", "family", "corporatebody", "position", "mechanism"),
    "Event": ("event", "activity"),
    "Rule": ("rule", "mandate"),
    "Date": ("date",),
    "Place": ("place",),
    "Instantiation": ("instantiation",),
    "FormaDocumental": (),
}


def retirar(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    RelacionRiC = apps.get_model("ric", "RelacionRiC")
    ahora = timezone.now()
    retirados = []
    for nombre in MODELOS:
        modelo = apps.get_model("ric", nombre)
        ids = [o.pk for o in modelo.objects.filter(eliminado=False) if MARCA.search(o.nombre or "")]
        if ids:
            modelo.objects.filter(pk__in=ids).update(eliminado=True, eliminado_en=ahora, motivo_eliminacion=MOTIVO)
            retirados.append((nombre, ids))
    for nombre, ids in retirados:
        # la relación apunta al subtipo concreto (Person, Record...): solo los tipos de esa misma tabla
        for ct in ContentType.objects.filter(app_label="ric", model__in=MODELOS[nombre]):
            RelacionRiC.objects.filter(eliminado=False, origen_content_type=ct, origen_object_id__in=ids).update(
                eliminado=True, eliminado_en=ahora, motivo_eliminacion=MOTIVO)
            RelacionRiC.objects.filter(eliminado=False, destino_content_type=ct, destino_object_id__in=ids).update(
                eliminado=True, eliminado_en=ahora, motivo_eliminacion=MOTIVO)


class Migration(migrations.Migration):

    dependencies = [
        ("ric", "0025_etiquetas_sin_codigos"),
    ]

    operations = [migrations.RunPython(retirar, migrations.RunPython.noop)]
