"""Proveedor de IA en la nube para el núcleo RiC: propone relaciones entre un
Record y entidades (nuevas o existentes) usando Claude con salida
estructurada.

Reglas que aplica (mismas que `asistencia.proveedor_claude`, adaptadas al
grafo RiC verificado):
- Solo se le ofrecen a Claude los IDs de relación y de tipo de entidad que
  el motor de reglas (`ric.reglas`, construido sobre RiC-CM 1.0 / RiC-O 1.1
  verificados) sabe que son válidos para un Record — no puede inventar un
  ID que no exista.
- Evidencia: cada propuesta debe citar el fragmento literal que la
  respalda; `ric.proveedores.generar_propuestas` la verifica contra el
  texto real, no confía en la palabra de Claude.
- Aun así, todo vuelve a pasar por el motor de reglas antes de guardarse:
  Claude puede combinar mal una relación válida con un tipo de entidad
  inválido para esa relación, y eso también se detecta y se marca.

La clave de API se lee de la variable de entorno ANTHROPIC_API_KEY.
"""

from typing import Literal

import anthropic
from django.conf import settings
from pydantic import BaseModel, Field

from . import aprendizaje, reglas, tipos
from .proveedores import ErrorProveedorIA as _ErrorBase
from .proveedores import PropuestaCandidata, ProveedorIA

CONFIANZA = {"alta": 0.9, "media": 0.7, "baja": 0.4}


class ErrorProveedorIA(_ErrorBase):
    pass


class RelacionPropuestaRiC(BaseModel):
    relacion_id: str = Field(description="Un ID de relación de la lista de relaciones permitidas.")
    entidad_tipo: str = Field(description="Un ID de tipo de entidad de la lista de tipos permitidos para esa relación.")
    entidad_nombre: str = Field(description="Forma normalizada del nombre de la entidad.")
    evidencia: str = Field(description="Fragmento copiado literalmente del documento que respalda la propuesta.")
    confianza: Literal["alta", "media", "baja"]
    justificacion: str = Field(description="Una frase que explica el razonamiento.")


class PropuestasRecordRiC(BaseModel):
    relaciones: list[RelacionPropuestaRiC]


def _relaciones_aplicables(modelo_origen):
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


def _tabla_relaciones(aplicables):
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

EJEMPLOS = """

Ejemplos de decisiones ya validadas por la persona archivista en documentos parecidos \
(úsalos para aprender el patrón, pero cada propuesta debe seguir basándose en evidencia \
real de ESTE documento, no de los ejemplos):
{lista}"""


class ProveedorClaude(ProveedorIA):
    nombre = "claude"

    def __init__(self, cliente=None, modelo=None):
        self.modelo = modelo or settings.MAZUCA_MODELO_IA
        self.version = self.modelo
        self._cliente = cliente

    @property
    def cliente(self):
        if self._cliente is None:
            self._cliente = anthropic.Anthropic()
        return self._cliente

    def proponer(self, record, texto):
        aplicables = _relaciones_aplicables(type(record))
        if not aplicables:
            return []
        instrucciones = INSTRUCCIONES.format(tabla_relaciones=_tabla_relaciones(aplicables))

        ejemplos = aprendizaje.ejemplos_similares(texto, origen_modelo=type(record))
        if ejemplos:
            instrucciones += EJEMPLOS.format(lista=aprendizaje.formatear_ejemplos(ejemplos))

        try:
            respuesta = self.cliente.beta.messages.parse(
                model=self.modelo,
                max_tokens=16000,
                system=instrucciones,
                messages=[{"role": "user", "content": f"<documento>\n{texto}\n</documento>"}],
                output_format=PropuestasRecordRiC,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError:
            raise ErrorProveedorIA("La clave de API de Anthropic no es válida o no está configurada.")
        except anthropic.RateLimitError:
            raise ErrorProveedorIA("Se superó el límite de uso del servicio de IA. Intente más tarde.")
        except anthropic.APIConnectionError:
            raise ErrorProveedorIA("No hay conexión con el servicio de IA.")
        except anthropic.APIStatusError as e:
            raise ErrorProveedorIA(f"El servicio de IA respondió con un error ({e.status_code}).")

        if respuesta.stop_reason == "refusal":
            raise ErrorProveedorIA("El servicio de IA no procesó este documento.")
        if respuesta.stop_reason == "max_tokens" or respuesta.parsed_output is None:
            raise ErrorProveedorIA("La respuesta del servicio de IA llegó incompleta.")

        self.version = respuesta.model
        return [
            PropuestaCandidata(
                relacion_id=r.relacion_id,
                entidad_tipo=r.entidad_tipo,
                entidad_nombre=r.entidad_nombre,
                evidencia=r.evidencia,
                confianza=CONFIANZA[r.confianza],
                justificacion=r.justificacion,
            )
            for r in respuesta.parsed_output.relaciones
        ]
