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

# Prioridad: «B» conviene con el fondo real; «C» no aplica o vale poco por ahora;
# «especializada» está cubierta por una relación más específica, como pide la
# nota de uso de RiC-O (escribir la general además sería contrario a ella).
FALTANTES: dict[str, tuple[str, str]] = {
    "A10": ("B", "Tipo de contenido (texto, imagen, mapa): falta el vocabulario."),
    "A12": ("B", "Tipo de entidad (orden nacional o territorial, sector): falta el campo."),
    "A15": ("C", "Grupo demográfico: dato sensible (Ley 1581); solo con finalidad y consentimiento."),
    "A18": ("B", "Tipo de evento para los hitos: falta el vocabulario."),
    "A20": ("B", "Tipo de familia: archivos familiares."),
    "A30": ("B", "Tipo de ocupación de los agentes: falta el vocabulario."),
    "A33": ("B", "Técnica de producción (manuscrito, mecanografiado, impreso): falta el campo."),
    "R004": ("B", "Componentes de una instanciación (correo y adjuntos)."),
    "R006": ("B", "Subevento general: se usa la sub-actividad directa (hasDirectSubevent)."),
    "R009": ("B", "Precede en el tiempo sin secuencia archivística."),
    "R010": ("C", "Original y copia como dos documentos: el original físico es una instanciación (CM-04)."),
    "R012": ("C", "Copia como otro documento: mismo motivo que R010."),
    "R017": ("B", "Descendencia: genealogías de archivos familiares."),
    "R020": ("B", "Materia principal frente a las secundarias del tesauro."),
    "R026": ("especializada", "Procedencia orgánica: el sistema escribe hasCreator (R027) y hasAccumulator (R028), "
                              "subpropiedades de hasOrganicProvenance; RiC-O pide usar la general solo si no cabe "
                              "una más específica."),
    "R029": ("C", "Receptor: se cubre con el destinatario (R032)."),
    "R030": ("C", "Coleccionista: el fondo no tiene colecciones facticias de un coleccionista identificado."),
    "R034": ("B", "Instanciaciones asociadas entre sí."),
    "R035": ("C", "Equivalencia funcional entre entidades: no la pide la TRD."),
    "R036": ("B", "Autoridad sobre (adscripción o vinculación de una entidad)."),
    "R037": ("C", "Propietario: la custodia se registra con hasOrHadHolder."),
    "R038": ("C", "Gestor: sin caso en el fondo."),
    "R040": ("B", "Titular de derechos de autor (Ley 23 de 1982)."),
    "R041": ("C", "Control entre agentes: se cubre con la subordinación (R045)."),
    "R046": ("C", "Relación laboral: la cubren el cargo y la membresía en archivos institucionales."),
    "R050": ("C", "Conoce de: archivos personales."),
    "R051": ("C", "Conoce a: archivos personales."),
    "R052": ("C", "Correspondiente: lo cubren el remitente y el destinatario."),
    "R053": ("C", "Maestro y alumno: archivos personales."),
    "R058": ("B", "Participante de un evento o de un comité."),
    "R066": ("B", "Quién vigila la regla (el AGN o el consejo departamental sobre la TRD)."),
    "R070": ("B", "Fecha de nacimiento: hoy la existencia sale como fechas de inicio y fin."),
    "R072": ("B", "Fecha de muerte: mismo motivo que R070."),
    "R073": ("C", "Fecha de modificación de un documento histórico: el sistema no la registra."),
    "R076": ("C", "Jurisdicción: el lugar de actuación usa isOrWasLocationOf (R075)."),
    "R077": ("C", "Lugares adyacentes: sin uso en la descripción institucional."),
    "R078": ("C", "Lugares superpuestos: sin uso en la descripción institucional."),
    "R082": ("B", "Fechas de creación de algunos miembros (fechas predominantes del FUID)."),
    "R083": ("B", "Fechas de creación de la mayoría de los miembros (fechas predominantes)."),
    "R084": ("B", "Fecha en que ocurrió un evento."),
    "R085": ("C", "Fecha dentro de otra: EDTF ya expresa intervalos e incertidumbre."),
    "R086": ("C", "Fechas que se cruzan: mismo motivo que R085."),
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
