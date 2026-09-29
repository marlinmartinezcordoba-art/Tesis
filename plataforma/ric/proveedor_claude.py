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

import base64
from pathlib import Path

import anthropic
from django.conf import settings

from .ia_prompt import PropuestasRecordRiC, candidatos_desde_respuesta, construir_instrucciones
from .proveedores import ErrorProveedorIA as _ErrorBase
from .proveedores import ProveedorIA

# F05 (IA multimodal): formatos con representación visual que Claude puede
# leer directamente, para notar firmas, sellos o tablas que el OCR de F02
# no captura bien. Solo tipos de imagen documentados como soportados por la
# API de Claude (jpeg/png) — no se envían tif/bmp, que no lo están, aunque
# F01 los acepte para preservación.
_MEDIA_TYPE_IMAGEN = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def _contenido_visual(instanciacion):
    """Bloque de imagen o PDF con el documento real, además de su texto —
    de ahí que el módulo se llame "multimodal". Lista vacía si no hay
    instanciación, si su archivo no tiene representación visual (.txt,
    .docx: ahí el texto YA es el contenido completo, no hace falta verlo)
    o si el archivo no se puede leer."""
    if instanciacion is None or not instanciacion.archivo:
        return []
    extension = Path(instanciacion.archivo.name).suffix.lower()
    if extension != ".pdf" and extension not in _MEDIA_TYPE_IMAGEN:
        return []
    try:
        with instanciacion.archivo.open("rb") as f:
            datos = base64.standard_b64encode(f.read()).decode("ascii")
    except (FileNotFoundError, ValueError):
        return []
    if extension == ".pdf":
        return [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": datos}}]
    return [{"type": "image", "source": {"type": "base64", "media_type": _MEDIA_TYPE_IMAGEN[extension], "data": datos}}]


class ErrorProveedorIA(_ErrorBase):
    pass


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

    def proponer(self, record, texto, instanciacion=None):
        self.advertencias, self.forma_documental = [], None
        contenido_visual = _contenido_visual(instanciacion)
        instrucciones = construir_instrucciones(record, texto, con_visual=bool(contenido_visual))
        if instrucciones is None:
            return []

        contenido = [*contenido_visual, {"type": "text", "text": f"<documento>\n{texto}\n</documento>"}]

        try:
            respuesta = self.cliente.beta.messages.parse(
                model=self.modelo,
                max_tokens=16000,
                system=instrucciones,
                messages=[{"role": "user", "content": contenido}],
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
        candidatos, self.forma_documental, self.advertencias = candidatos_desde_respuesta(respuesta.parsed_output)
        return candidatos
