"""Lo que cualquier proveedor de IA en la nube necesita para proponer
relaciones RiC — instrucciones, esquema de salida estructurada y el filtro
de qué relaciones/tipos son válidos para un Record dado — independiente de
si quien responde es Claude, Gemini o cualquier otro.

Antes vivía dentro de `ric.proveedor_claude`; se separó al agregar un
segundo proveedor (`ric.proveedor_gemini`) para no duplicar el prompt ni el
esquema Pydantic entre los dos (y para que una corrección al prompt no
pueda quedar aplicada en uno y olvidada en el otro).
"""

from typing import Literal

from pydantic import BaseModel, Field

from . import reglas, tipos

CONFIANZA = {"alta": 0.9, "media": 0.7, "baja": 0.4}


class RelacionPropuestaRiC(BaseModel):
    relacion_id: str = Field(description="Un ID de relación de la lista de relaciones permitidas.")
    entidad_tipo: str = Field(description="Un ID de tipo de entidad de la lista de tipos permitidos para esa relación.")
    entidad_nombre: str = Field(description="Forma normalizada del nombre de la entidad.")
    evidencia: str = Field(description="Fragmento copiado literalmente del documento que respalda la propuesta.")
    confianza: Literal["alta", "media", "baja"]
    justificacion: str = Field(description="Una frase que explica el razonamiento.")


class PropuestasRecordRiC(BaseModel):
    relaciones: list[RelacionPropuestaRiC]


def relaciones_aplicables(modelo_origen):
    """{relacion_id: {"nombre":..., "tipos_destino": [ric_id, ...]}} para las
    relaciones cuyo dominio (verificado) acepta `modelo_origen`, restringidas
    a tipos de entidad "hoja" (nunca la categoría abstracta Agent/Event/Rule)."""
    matriz = reglas.cargar_matriz()
    aplicables = {}
    for rid, datos in matriz["relaciones"].items():
        try:
            modelos_dominio, modelos_rango = reglas.entidades_para(rid)
        except reglas.RelacionInvalida:
            continue
        if modelos_dominio is not None and not issubclass(modelo_origen, modelos_dominio):
            continue
        tipos_destino = []
        for ric_id in tipos.LEAF_TIPOS:
            modelo_destino = tipos.ric_id_a_modelo(ric_id)
            if modelos_rango is None or issubclass(modelo_destino, modelos_rango):
                tipos_destino.append(ric_id)
        if tipos_destino:
            aplicables[rid] = {"nombre": datos["nombre"], "tipos_destino": tipos_destino}
    return aplicables


def tabla_relaciones(aplicables):
    matriz = reglas.cargar_matriz()
    nombres_tipo = {eid: d["nombre"] for eid, d in matriz["entidades"].items()}
    lineas = []
    for rid, info in sorted(aplicables.items(), key=lambda kv: int(kv[0][1:])):
        tipos_legibles = ", ".join(f"{t} ({nombres_tipo.get(t, t)})" for t in info["tipos_destino"])
        lineas.append(f"- {rid} \"{info['nombre']}\": entidad_tipo debe ser uno de [{tipos_legibles}]")
    return "\n".join(lineas)


INSTRUCCIONES = """Eres una persona experta en archivística que aplica el modelo \
Records in Contexts (RiC-CM 1.0) a un documento de un archivo histórico colombiano. \
Identificas qué entidades (agentes, lugares, fechas, actividades...) se relacionan con \
este documento y con qué tipo de relación, EXACTAMENTE de la lista permitida que sigue. \
Una persona archivista revisará cada propuesta antes de que se escriba en el grafo.

Relaciones permitidas para este documento (usa solo estos IDs, con el entidad_tipo \
indicado para cada una):
{tabla_relaciones}

Reglas:
- No propongas una relación ni un entidad_tipo que no estén en la lista de arriba: \
si no encaja en ninguna, no la propongas.
- entidad_nombre: forma normalizada del nombre (por ejemplo, el nombre completo de \
la persona o institución, no un pronombre ni una abreviatura sin expandir).
- evidencia: copia literalmente, sin corregir ortografía, el fragmento del documento \
que respalda la propuesta. Si no hay fragmento que la respalde, no la propongas.
- No inventes una entidad de tipo "tema" o "concepto": RiC-CM no lo tiene. Si el \
documento trata sobre un tema, usa "R019 has or had subject" apuntando a la persona, \
lugar o actividad de la que trata.
- El texto puede tener errores de OCR y la marca [DATO RESERVADO]; no intentes \
reconstruir los datos reservados."""

INSTRUCCIONES_VISUAL = """

También puedes ver la imagen o el PDF original del documento, no solo su texto \
extraído por OCR. Úsalo para notar lo que el OCR suele perderse: firmas, sellos, \
membretes, tablas o zonas mal escaneadas. Si la evidencia de una propuesta viene de \
algo que solo se ve en la imagen (una firma, por ejemplo) y no aparece igual en el \
texto, dilo en la justificación — el archivista puede necesitar verificarlo a mano."""

EJEMPLOS = """

Ejemplos de decisiones ya validadas por la persona archivista en documentos parecidos \
(úsalos para aprender el patrón, pero cada propuesta debe seguir basándose en evidencia \
real de ESTE documento, no de los ejemplos):
{lista}"""
