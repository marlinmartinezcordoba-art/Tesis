"""Un solo lugar donde vive la correspondencia ID-RiC-CM -> modelo Django.

`ric.reglas` la usa para el motor de reglas; los proveedores de IA la usan
para saber qué modelo instanciar cuando una propuesta se acepta.
"""

from django.apps import apps


def _modelo(nombre):
    return apps.get_model("ric", nombre)


# ID oficial de RiC-CM 1.0 -> modelo Django. Solo las entidades que el
# sistema puede instanciar (RecordResource y sus subtipos concretos entran
# por ingesta, no por propuesta de IA; por eso no están en LEAF_TIPOS más
# abajo, aunque sí están aquí para el motor de reglas).
RIC_ID_A_MODELO_NOMBRE = {
    "E02": "RecordResource", "E03": "RecordSet", "E04": "Record", "E05": "RecordPart",
    "E06": "Instantiation", "E07": "Agent", "E08": "Person", "E09": "Group",
    "E10": "Family", "E11": "CorporateBody", "E12": "Position", "E13": "Mechanism",
    "E14": "Event", "E15": "Activity", "E16": "Rule", "E17": "Mandate",
    "E18": "Date", "E22": "Place",
}

# Nombre oficial en inglés (tal como aparece en RiC-CM-1.0.pdf) -> mismo modelo.
NOMBRE_CM_A_MODELO_NOMBRE = {
    "Record Resource": "RecordResource", "Record Set": "RecordSet", "Record": "Record",
    "Record Part": "RecordPart", "Instantiation": "Instantiation", "Agent": "Agent",
    "Person": "Person", "Group": "Group", "Family": "Family", "Corporate Body": "CorporateBody",
    "Position": "Position", "Mechanism": "Mechanism", "Event": "Event", "Activity": "Activity",
    "Rule": "Rule", "Mandate": "Mandate", "Date": "Date", "Place": "Place",
}

# Tipos "hoja" que una IA puede proponer como entidad nueva: subtipos
# concretos y específicos, nunca la categoría abstracta (por ejemplo,
# propone "Person" o "CorporateBody", nunca el genérico "Agent").
LEAF_TIPOS = ["E08", "E09", "E10", "E11", "E12", "E13", "E15", "E17", "E18", "E22"]


def ric_id_a_modelo(ric_id):
    nombre = RIC_ID_A_MODELO_NOMBRE.get(ric_id)
    return _modelo(nombre) if nombre else None


def nombre_cm_a_modelo(nombre_cm):
    nombre = NOMBRE_CM_A_MODELO_NOMBRE.get(nombre_cm.strip())
    return _modelo(nombre) if nombre else None
