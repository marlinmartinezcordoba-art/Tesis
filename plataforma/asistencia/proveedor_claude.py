"""Proveedor de IA en la nube: borradores de descripción ISAD(G) con Claude.

Reglas que aplica este proveedor (lineamientos de la tesis):
- Privacidad (Ley 1581 de 2012, art. 26): solo se envía a la nube un documento
  con la revisión de datos personales decidida. Si se decidió anonimizar, se
  envía el texto anonimizado; si el documento está restringido, no se envía.
- Evidencia: cada dato propuesto debe citar el fragmento literal que lo
  respalda. MAZUCA verifica la cita en `generar_sugerencias`.
- Trazabilidad: la sugerencia guarda el modelo que respondió realmente.

La clave de API se lee de la variable de entorno ANTHROPIC_API_KEY.
"""

from typing import Literal

import anthropic
from django.conf import settings
from pydantic import BaseModel, Field

from acervo.models import UnidadClasificacion

from .proveedores import Propuesta, ProveedorIA

CONFIANZA = {"alta": 0.9, "media": 0.7, "baja": 0.4}


class ErrorProveedorIA(Exception):
    """Error que se muestra a la persona archivista en lenguaje claro."""


# --- Estructura de la respuesta (salida estructurada) -----------------------

class CampoPropuesto(BaseModel):
    valor: str = Field(description="Valor propuesto; cadena vacía si el texto no permite determinarlo.")
    evidencia: str = Field(description="Fragmento copiado literalmente del documento que respalda el valor.")
    confianza: Literal["alta", "media", "baja"]
    justificacion: str = Field(description="Una o dos frases que explican el razonamiento.")


class EntidadPropuesta(BaseModel):
    tipo: Literal["persona", "lugar", "institucion"]
    nombre: str = Field(description="Forma normalizada del nombre.")
    evidencia: str = Field(description="Fragmento literal donde aparece la entidad.")
    confianza: Literal["alta", "media", "baja"]


class BorradorDescripcion(BaseModel):
    titulo: CampoPropuesto
    fechas: CampoPropuesto
    productor: CampoPropuesto
    alcance_contenido: CampoPropuesto
    entidades: list[EntidadPropuesta]


INSTRUCCIONES = """Eres una persona experta en descripción archivística que apoya a un \
archivo histórico colombiano. Propones un BORRADOR de descripción según ISAD(G) \
a partir del texto de un documento obtenido por OCR. Una persona archivista \
revisará cada dato antes de usarlo.

Reglas:
- Título (ISAD(G) 3.1.2): si el documento no tiene título formal, redacta un \
título atribuido breve y escríbelo entre corchetes, por ejemplo \
"[Carta del virrey al Cabildo de Santafé]".
- Fechas (3.1.3): año o rango de años, por ejemplo "1781" o "1781-1783".
- Productor (3.2.1): la persona o institución que produjo el documento, no el \
destinatario.
- Alcance y contenido (3.3.1): resumen neutral de tres a cinco líneas.
- Entidades: personas, lugares e instituciones mencionadas, con su nombre \
normalizado.
- Evidencia: copia literalmente, sin corregir ortografía, el fragmento del \
documento que respalda cada dato. Si no hay fragmento que lo respalde, deja \
el valor vacío.
- No inventes datos. Si algo no se puede determinar, deja el valor vacío y \
explícalo en la justificación.
- El texto puede contener errores de OCR y la marca [DATO RESERVADO]; no \
intentes reconstruir los datos reservados."""


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

    def texto_de(self, documento):
        revision = documento.revisiones_datos.first()
        if revision is None or revision.decision == "pendiente":
            raise ErrorProveedorIA(
                "Antes de enviar el documento a la nube, revise y decida sus datos personales."
            )
        if not revision.vigente:
            raise ErrorProveedorIA(
                "El texto cambió después de la revisión de datos personales. Revise de nuevo."
            )
        if revision.decision == "restringido":
            raise ErrorProveedorIA(
                "El documento tiene acceso restringido y no se envía a servicios en la nube."
            )
        if revision.decision == "anonimizar":
            return documento.texto_publico
        return documento.texto_extraido

    def _consultar_generico(self, texto, instrucciones, formato, contexto=""):
        """Llama a Claude con salida estructurada; usada por descripción y clasificación."""
        partes = [f"<documento>\n{texto}\n</documento>"]
        if contexto:
            partes.append(contexto)
        try:
            respuesta = self.cliente.beta.messages.parse(
                model=self.modelo,
                max_tokens=16000,
                system=instrucciones,
                messages=[{"role": "user", "content": "\n\n".join(partes)}],
                output_format=formato,
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
        return respuesta

    def proponer(self, documento, texto):
        if not texto.strip():
            raise ErrorProveedorIA("El documento no tiene texto. Extraiga el texto primero.")
        respuesta = self._consultar_generico(
            texto, INSTRUCCIONES, BorradorDescripcion,
            contexto="Propón el borrador de descripción de este documento.",
        )

        # Registra el modelo que respondió realmente (puede ser el de respaldo).
        self.version = respuesta.model
        borrador = respuesta.parsed_output
        propuestas = []
        for campo in ("titulo", "fechas", "productor", "alcance_contenido"):
            c = getattr(borrador, campo)
            if c.valor.strip():
                propuestas.append(Propuesta(
                    proceso="descripcion",
                    campo=campo,
                    valor=c.valor.strip(),
                    confianza=CONFIANZA[c.confianza],
                    justificacion=c.justificacion,
                    evidencia=c.evidencia,
                    criterios=["DES-01", "DES-02", "DES-03"],
                ))
        vistas = set()
        for e in borrador.entidades:
            clave = (e.tipo, e.nombre.strip().lower())
            if e.nombre.strip() and clave not in vistas:
                vistas.add(clave)
                propuestas.append(Propuesta(
                    proceso="descripcion",
                    campo=e.tipo,
                    valor=e.nombre.strip(),
                    confianza=CONFIANZA[e.confianza],
                    justificacion=f"{e.tipo.capitalize()} mencionada en el documento.",
                    evidencia=e.evidencia,
                    criterios=["DES-02", "DES-03", "ACC-02"],
                ))
        return propuestas


# --- Clasificación --------------------------------------------------------

class ClasificacionPropuesta(BaseModel):
    codigo_unidad: str = Field(
        description="Código exacto de la serie o subserie elegida, copiado de la lista dada; "
                    "cadena vacía si ninguna encaja."
    )
    evidencia: str = Field(description="Fragmento literal del documento que respalda la elección.")
    confianza: Literal["alta", "media", "baja"]
    justificacion: str = Field(description="Por qué el documento pertenece a esa serie.")


INSTRUCCIONES_CLASIFICACION = """Eres una persona experta en archivística que apoya la \
clasificación de un archivo histórico colombiano, según el principio de procedencia \
(Ley 594 de 2000; ISAD(G)). Debes ubicar el documento en UNA de las series o \
subseries del cuadro de clasificación que te doy, nunca crear una nueva.

Reglas:
- Elige el código exacto de la lista, tal como aparece.
- Si ninguna serie encaja razonablemente, deja codigo_unidad vacío; no elijas \
la que menos mal quede.
- Evidencia: copia literalmente el fragmento del documento que justifica la \
elección. Si no hay evidencia clara, deja codigo_unidad vacío.
- El texto puede contener errores de OCR y la marca [DATO RESERVADO]."""


class ProveedorClasificacionClaude(ProveedorIA):
    """Propone la serie del cuadro de clasificación; reutiliza las reglas de
    privacidad y el cliente de ProveedorClaude (composición, no herencia,
    para no mezclar la salida estructurada de descripción con la de aquí)."""

    nombre = "claude"

    def __init__(self, cliente=None, modelo=None):
        self._base = ProveedorClaude(cliente=cliente, modelo=modelo)
        self.version = self._base.version

    def texto_de(self, documento):
        return self._base.texto_de(documento)

    def proponer(self, documento, texto):
        if not texto.strip():
            raise ErrorProveedorIA("El documento no tiene texto. Extraiga el texto primero.")

        unidades = list(
            UnidadClasificacion.objects.filter(
                tipo__in=[UnidadClasificacion.Tipo.SERIE, UnidadClasificacion.Tipo.SUBSERIE]
            )
        )
        if not unidades:
            raise ErrorProveedorIA(
                "No hay cuadro de clasificación cargado. Cárguelo antes de clasificar con IA."
            )
        codigos_validos = {u.codigo for u in unidades}
        cuadro = "\n".join(f"- {u.codigo}: {u.ruta()} — {u.descripcion}" for u in unidades)

        respuesta = self._base._consultar_generico(
            texto, INSTRUCCIONES_CLASIFICACION, ClasificacionPropuesta,
            contexto=f"<cuadro_de_clasificacion>\n{cuadro}\n</cuadro_de_clasificacion>",
        )
        self.version = respuesta.model

        propuesta = respuesta.parsed_output
        codigo = propuesta.codigo_unidad.strip()
        if not codigo:
            return []
        if codigo not in codigos_validos:
            # La IA propuso un código que no está en el cuadro: se descarta
            # en vez de crear una sugerencia con una unidad inexistente.
            return []
        return [Propuesta(
            proceso="clasificacion",
            campo="clasificacion",
            valor=codigo,
            confianza=CONFIANZA[propuesta.confianza],
            justificacion=propuesta.justificacion,
            evidencia=propuesta.evidencia,
            criterios=["CLA-01", "CLA-02", "CLA-03"],
        )]
