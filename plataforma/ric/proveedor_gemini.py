"""Proveedor de IA en la nube para el núcleo RiC: propone relaciones entre un
Record y entidades (nuevas o existentes) usando Gemini con salida
estructurada.

Mismas reglas que `ric.proveedor_claude` (la IA propone, RICORA decide) —
los dos comparten el prompt y el esquema de salida en `ric.ia_prompt` para
que una corrección no quede aplicada en un proveedor y olvidada en el otro:
- Solo se le ofrecen a Gemini los IDs de relación y de tipo de entidad que
  el motor de reglas (`ric.reglas`, construido sobre RiC-CM 1.0 / RiC-O 1.1
  verificados) sabe que son válidos para un Record — no puede inventar un
  ID que no exista.
- Evidencia: cada propuesta debe citar el fragmento literal que la
  respalda; `ric.proveedores.generar_propuestas` la verifica contra el
  texto real, no confía en la palabra de Gemini.
- Aun así, todo vuelve a pasar por el motor de reglas antes de guardarse.

La clave de API se lee de la variable de entorno GEMINI_API_KEY (la que usa
el SDK oficial `google-genai` por convención).
"""

from pathlib import Path

from django.conf import settings
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from httpx import RequestError as _HttpxRequestError

from . import aprendizaje
from .ia_prompt import CONFIANZA, EJEMPLOS, INSTRUCCIONES, INSTRUCCIONES_VISUAL, PropuestasRecordRiC, relaciones_aplicables, tabla_relaciones
from .proveedores import ErrorProveedorIA as _ErrorBase
from .proveedores import PropuestaCandidata, ProveedorIA

# F05 (IA multimodal): mismo alcance documentado que ric.proveedor_claude —
# solo formatos con representación visual soportados directamente por la
# API (imagen o PDF); .txt/.docx no lo necesitan porque ahí el texto YA es
# el contenido completo.
_MEDIA_TYPE_IMAGEN = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def _contenido_visual(instanciacion):
    """Parte(s) de imagen o PDF con el documento real, además de su texto.
    Lista vacía si no hay instanciación, si su archivo no tiene
    representación visual soportada, o si el archivo no se puede leer."""
    if instanciacion is None or not instanciacion.archivo:
        return []
    extension = Path(instanciacion.archivo.name).suffix.lower()
    if extension != ".pdf" and extension not in _MEDIA_TYPE_IMAGEN:
        return []
    try:
        with instanciacion.archivo.open("rb") as f:
            datos = f.read()
    except (FileNotFoundError, ValueError):
        return []
    media_type = "application/pdf" if extension == ".pdf" else _MEDIA_TYPE_IMAGEN[extension]
    return [genai_types.Part.from_bytes(data=datos, mime_type=media_type)]


class ErrorProveedorIA(_ErrorBase):
    pass


class ProveedorGemini(ProveedorIA):
    nombre = "gemini"

    def __init__(self, cliente=None, modelo=None):
        self.modelo = modelo or settings.MAZUCA_MODELO_IA_GEMINI
        self.version = self.modelo
        self._cliente = cliente

    @property
    def cliente(self):
        if self._cliente is None:
            self._cliente = genai.Client()
        return self._cliente

    def proponer(self, record, texto, instanciacion=None):
        aplicables = relaciones_aplicables(type(record))
        if not aplicables:
            return []
        instrucciones = INSTRUCCIONES.format(tabla_relaciones=tabla_relaciones(aplicables))

        contenido_visual = _contenido_visual(instanciacion)
        if contenido_visual:
            instrucciones += INSTRUCCIONES_VISUAL

        ejemplos = aprendizaje.ejemplos_similares(texto, origen_modelo=type(record))
        if ejemplos:
            instrucciones += EJEMPLOS.format(lista=aprendizaje.formatear_ejemplos(ejemplos))

        partes = [*contenido_visual, genai_types.Part.from_text(text=f"<documento>\n{texto}\n</documento>")]

        try:
            respuesta = self.cliente.models.generate_content(
                model=self.modelo,
                contents=[genai_types.Content(role="user", parts=partes)],
                config=genai_types.GenerateContentConfig(
                    system_instruction=instrucciones,
                    response_mime_type="application/json",
                    response_schema=PropuestasRecordRiC,
                    max_output_tokens=16000,
                ),
            )
        except genai_errors.ClientError as e:
            if e.code == 401 or e.code == 403:
                raise ErrorProveedorIA("La clave de API de Gemini no es válida o no está configurada.")
            if e.code == 429:
                raise ErrorProveedorIA("Se superó el límite de uso del servicio de IA. Intente más tarde.")
            raise ErrorProveedorIA(f"El servicio de IA respondió con un error ({e.code}).")
        except genai_errors.ServerError as e:
            raise ErrorProveedorIA(f"El servicio de IA respondió con un error ({e.code}).")
        except _HttpxRequestError:
            raise ErrorProveedorIA("No hay conexión con el servicio de IA.")

        candidatos = respuesta.candidates or []
        finalizacion = candidatos[0].finish_reason if candidatos else None
        if finalizacion is not None and finalizacion.name not in ("STOP", "FINISH_REASON_UNSPECIFIED"):
            if finalizacion.name == "MAX_TOKENS":
                raise ErrorProveedorIA("La respuesta del servicio de IA llegó incompleta.")
            raise ErrorProveedorIA("El servicio de IA no procesó este documento.")
        if respuesta.parsed is None:
            raise ErrorProveedorIA("La respuesta del servicio de IA llegó incompleta.")

        if respuesta.model_version:
            self.version = respuesta.model_version
        return [
            PropuestaCandidata(
                relacion_id=r.relacion_id,
                entidad_tipo=r.entidad_tipo,
                entidad_nombre=r.entidad_nombre,
                evidencia=r.evidencia,
                confianza=CONFIANZA[r.confianza],
                justificacion=r.justificacion,
            )
            for r in respuesta.parsed.relaciones
        ]
