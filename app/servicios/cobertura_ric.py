"""
Cobertura de RiC-CM 1.0, medida desde el mapeo que la exportación usa de verdad.

Un código de RiC-CM (atributo RiC-Axx o relación RiC-Rxxx) está cubierto si
el sistema escribe al menos uno de los términos de RiC-O 1.1 que lo
implementan (el OWL oficial cita el código de cada término) o su inversa.
La fuente es app/servicios/ric_o.py, no una búsqueda de texto: un código
«reservado» (en el catálogo pero sin exportar) no cuenta.

Lo que no está cubierto se declara en FALTANTES con su prioridad y su motivo
(documentacion/brechas-ric-lineamiento-completo.md); la prueba
tests/test_cobertura_ric.py falla si aparece uno sin declarar o si la
cobertura baja.
"""

import re
from functools import lru_cache

from app.servicios import ric_o

# Desde la cobertura total solo queda R026, cubierta por una relación más
# específica («especializada»), como pide la nota de uso de RiC-O: escribir la
# general además sería contrario a ella. Un código nuevo sin cubrir debe
# declararse aquí con su prioridad y su motivo.
FALTANTES: dict[str, tuple[str, str]] = {}

# RiC-CM 1.0 numera 86 relaciones (R001 a R086); RiC-O 1.1 implementa 85: ningún término del OWL
# oficial cita RiC-R043. Sin propiedad en RiC-O no hay cómo escribirla sin salir de la ontología
# (el control de conformidad rechaza predicados ajenos), así que se declara aquí y no se inventa.
NO_IMPLEMENTADAS_EN_RICO = {
    "R043": "RiC-O 1.1 no tiene ninguna clase ni propiedad que cite RiC-R043.",
}

# Relaciones del catálogo que no se guardan como fila: la exportación las escribe desde datos que
# el sistema ya tiene (fechas de existencia, fechas extremas y predominantes, original y copia,
# TRD expresada en su documento…), con la propiedad de apoyo indicada. La prueba exige que la
# propiedad de apoyo sea la del catálogo (o su inversa): una sola fuente para el nombre.
ESCRITAS_AL_EXPORTAR = {
    "is_beginning_date_of": "inicio",  # R069: existencia o periodo (hasBeginningDate)
    "is_end_date_of": "fin",  # R071 (hasEndDate)
    "is_birth_date_of": "nacimiento",  # R070: existencia de una persona
    "is_death_date_of": "muerte",  # R072
    "is_or_was_creation_date_of_all_members_of": "fechas_extremas",  # R081: fechas extremas de una agrupación
    "is_or_was_creation_date_of_some_members_of": "fechas_algunos",  # R082: la fecha de cada documento en su conjunto
    "is_or_was_creation_date_of_most_members_of": "fechas_mayoria",  # R083: fechas predominantes
    "is_date_of_occurrence_of": "ocurrio",  # R084: fecha de un hito
    "is_within": "fecha_dentro_de",  # R085: fecha del documento dentro de las de su conjunto
    "intersects": "fecha_se_cruza",  # R086: o que se cruza con ellas
    "is_original_of": "original_de",  # R010: desde cada «es copia de» entre documentos
    "is_or_was_expressed_by": "expresada_en",  # R064: la TRD aplicada y su documento
    "describes_or_described": "describe",  # R021: el CCD y la TRD describen el fondo
    "results_or_resulted_in": "resultado",  # R061: la copia que resultó de digitalizar o migrar
    "has_or_had_subevent": "subevento",  # R006: junto a hasDirectSubevent
    "precedes_in_time": "precede_en_el_tiempo",  # R009: hitos sucesivos de un agente
    "is_functionally_equivalent_to": "equivalente",  # R035: el archivo migrado y su original
    "is_instantiation_associated_with_instantiation": "instanciacion_asociada",  # R034
    "is_or_was_enforced_by": "vigilada_por",  # R066: el ente que vigila la TRD
}

# Clases y propiedades que la exportación escribe sin pasar por un diccionario
# del mapeo (las fechas y los tipos de apoyo que solo se usan como rango).
_DIRECTOS = {"Language", "PlaceType", "PlaceName", "AgentName", "Identifier", "IdentifierType", "LegalStatus",
             "RecordSetType", "RuleType", "MandateType", "CarrierType", "DateType", "hasCreationDate",
             "isAssociatedWithDate", "hasBeginningDate", "hasEndDate"}


def usados() -> set[str]:
    """Nombres locales de RiC-O que el sistema escribe."""
    salida = set(_DIRECTOS)
    for p in (*ric_o.PROPIEDADES.values(), *ric_o.ACCION_TECNICA.values()):
        salida |= {p.rico, p.inversa} - {None}
    for nombre, _, rango in ric_o.APOYO.values():
        salida |= {nombre, rango}
    salida |= {nombre for nombre, _ in ric_o.ATRIBUTOS.values()}
    salida |= set(ric_o.RELACION_NARIA.values())
    for clases in (ric_o.CLASE_NIVEL, ric_o.CLASE_AGENTE, ric_o.CLASE_VOCABULARIO, ric_o.CLASE_NODO):
        salida |= set(clases.values())
    return salida


@lru_cache(maxsize=1)
def _codigos() -> dict[str, set[str]]:
    """Código de RiC-CM → términos de RiC-O que lo implementan, más sus inversas (según el OWL)."""
    from rdflib import OWL

    g = ric_o._owl()
    inversa = {}
    for a, b in g.subject_objects(OWL.inverseOf):
        inversa[str(a)] = str(b)
        inversa[str(b)] = str(a)
    salida: dict[str, set[str]] = {}
    for s, _, o in g:
        if str(s).startswith(ric_o.RICO):
            for c in re.findall(r"RiC-([AR]\d+)", str(o)):
                salida.setdefault(c, set()).update(
                    x[len(ric_o.RICO):] for x in (str(s), inversa.get(str(s))) if x)
    return salida


def medir() -> dict:
    """{atributos: {cubiertos, total}, relaciones: {…}, por_codigo: {código: [términos usados]}, faltantes: […]}."""
    u = usados()
    por_codigo = {c: sorted(t & u) for c, t in sorted(_codigos().items())}
    salida = {"por_codigo": por_codigo}
    for clave, letra in (("atributos", "A"), ("relaciones", "R")):
        codigos = [c for c in por_codigo if c.startswith(letra)]
        cubiertos = [c for c in codigos if por_codigo[c]]
        especializados = [c for c in codigos if not por_codigo[c] and FALTANTES.get(c, ("",))[0] == "especializada"]
        salida[clave] = {"cubiertos": len(cubiertos), "por_especializacion": len(especializados), "total": len(codigos)}
    salida["faltantes"] = [{"codigo": f"RiC-{c}", "prioridad": FALTANTES.get(c, ("sin declarar", ""))[0],
                            "motivo": FALTANTES.get(c, ("", "Sin motivo declarado."))[1]}
                           for c, t in por_codigo.items() if not t]
    return salida
