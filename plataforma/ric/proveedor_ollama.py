"""Proveedor de IA local para el núcleo RiC: Ollama corriendo en el mismo
servidor (servicio `ollama` de docker-compose). El texto del documento no
sale a internet y no depende de la disponibilidad de un servicio en la nube.

Mismas reglas que Gemini y Claude: comparte instrucciones y esquema de
salida con ellos (`ric.ia_prompt`), Ollama devuelve JSON restringido a ese
esquema (salida estructurada, parámetro `format`) y todo lo que proponga
vuelve a pasar por la verificación de evidencia y el motor de reglas en
`ric.proveedores.generar_propuestas`.

Límite honesto: en un servidor pequeño (2 GB de RAM, 1 CPU) solo cabe un
modelo pequeño (qwen2.5:1.5b por defecto): tarda minutos por documento y
propone con menos precisión que un modelo grande en la nube. Por eso corre
en la cola (M2) y su resultado siempre pasa por la persona archivista.
"""

import json

import httpx
from django.conf import settings
from pydantic import ValidationError

from .ia_prompt import PropuestasRecordRiC, candidatos_desde_respuesta, construir_instrucciones
from .proveedores import ErrorProveedorIA, ProveedorIA

# Contexto amplio: las instrucciones llevan las relaciones permitidas y el
# vocabulario existente, además del texto del documento.
_CONTEXTO = 8192
_TIEMPO_MAXIMO_S = 1500


class ProveedorOllama(ProveedorIA):
    nombre = "ollama"

    def __init__(self, url=None, modelo=None, cliente=None):
        self.url = (url or settings.OLLAMA_URL or "").rstrip("/")
        self.modelo = modelo or settings.RICORA_MODELO_OLLAMA
        self.version = self.modelo
        self._cliente = cliente

    @property
    def cliente(self):
        if self._cliente is None:
            self._cliente = httpx.Client(timeout=httpx.Timeout(_TIEMPO_MAXIMO_S, connect=10))
        return self._cliente

    def _post(self, ruta, datos):
        if not self.url:
            raise ErrorProveedorIA("La IA local no está configurada en este servidor (falta OLLAMA_URL).")
        try:
            respuesta = self.cliente.post(f"{self.url}{ruta}", json=datos)
        except httpx.TimeoutException:
            raise ErrorProveedorIA("La IA local tardó demasiado en responder; el documento puede ser muy extenso para el servidor.")
        except httpx.RequestError:
            raise ErrorProveedorIA("La IA local (Ollama) no está disponible en este momento.")
        if respuesta.status_code == 404:
            raise ErrorProveedorIA(f"El modelo «{self.modelo}» todavía no está descargado en la IA local.")
        if respuesta.status_code >= 400:
            raise ErrorProveedorIA(f"La IA local respondió con un error ({respuesta.status_code}).")
        return respuesta.json()

    def modelos_disponibles(self):
        if not self.url:
            raise ErrorProveedorIA("La IA local no está configurada en este servidor (falta OLLAMA_URL).")
        try:
            respuesta = self.cliente.get(f"{self.url}/api/tags", timeout=10)
            respuesta.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError):
            raise ErrorProveedorIA("La IA local (Ollama) no está disponible en este momento.")
        return [m.get("name", "") for m in respuesta.json().get("models", [])]

    def proponer(self, record, texto, instanciacion=None):
        self.advertencias, self.forma_documental = [], None
        instrucciones = construir_instrucciones(record, texto, con_visual=False)
        if instrucciones is None:
            return []
        datos = self._post("/api/chat", {
            "model": self.modelo,
            "stream": False,
            "format": PropuestasRecordRiC.model_json_schema(),
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_ctx": _CONTEXTO},
            "messages": [
                {"role": "system", "content": instrucciones},
                {"role": "user", "content": f"<documento>\n{texto}\n</documento>"},
            ],
        })
        contenido = (datos.get("message") or {}).get("content", "")
        if datos.get("done_reason") == "length":
            raise ErrorProveedorIA("La respuesta de la IA local llegó incompleta (documento demasiado extenso).")
        try:
            parsed = PropuestasRecordRiC.model_validate(json.loads(contenido))
        except (json.JSONDecodeError, ValidationError):
            raise ErrorProveedorIA("La IA local devolvió una respuesta que no cumple el formato esperado.")
        candidatos, self.forma_documental, self.advertencias = candidatos_desde_respuesta(parsed)
        return candidatos
