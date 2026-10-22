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
FALTANTES: dict[str, tuple[str, str]] = {
    "R026": ("especializada", "Procedencia orgánica: el sistema escribe hasCreator (R027) y hasAccumulator (R028), "
                              "subpropiedades de hasOrganicProvenance; RiC-O pide usar la general solo si no cabe "
                              "una más específica."),
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
