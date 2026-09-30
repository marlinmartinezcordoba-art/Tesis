"""
Motor de análisis: propone la descripción de uno o varios documentos a
partir de su texto ya extraído en la ingesta.

La inteligencia artificial propone y nunca decide: todo lo que devuelve
este módulo es una propuesta que el archivista acepta, edita o descarta.
Cada entidad propuesta viene con el fragmento exacto del que salió; si ese
fragmento no aparece de verdad en el texto, la confianza se rebaja y se
marca, para que nadie publique algo que el motor pudo inventar.
"""

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date

import httpx

from app.core.config import settings

log = logging.getLogger("ricora.motor")

TIPOS = ("agente", "lugar", "fecha", "actividad", "forma_documental")
ROLES_AGENTE = ("productor", "remitente", "destinatario", "mencionado")
SUBTIPOS_AGENTE = ("persona", "entidad_corporativa", "cargo", "familia")

MAX_CARACTERES_DOCUMENTO = 20_000
MAX_CARACTERES_TOTAL = 60_000
CONFIANZA_SIN_FRAGMENTO = 0.3


class MotorError(Exception):
    pass


@dataclass
class Documento:
    id: uuid.UUID
    nombre: str
    texto: str


@dataclass
class EntidadPropuesta:
    clave: str
    tipo: str
    valor: str
    subtipo: str | None = None
    rol: str | None = None
    fecha_normalizada: str | None = None
    fragmento: str | None = None
    documento_id: str | None = None
    inicio: int | None = None
    confianza: float = 0.0
    fragmento_localizado: bool = False


@dataclass
class Propuesta:
    titulo: str = ""
    alcance: str = ""
    confianza_alcance: float | None = None
    entidades: list[EntidadPropuesta] = field(default_factory=list)
    motor: str | None = None
    disponible: bool = False
    aviso: str | None = None

    def a_dict(self) -> dict:
        return asdict(self)


# --- Motor Gemini ------------------------------------------------------------------

INSTRUCCION = """Eres un asistente de descripción archivística que trabaja con el estándar Records in Contexts (RiC-CM 1.0) sobre documentos de un archivo histórico colombiano. Propones; una archivista valida.

Reglas estrictas:
- Usa solo lo que dice el texto. No inventes nombres, fechas ni lugares. Si algo es dudoso, propónlo con confianza baja.
- Cada entidad lleva "fragmento": un trozo copiado LITERALMENTE del texto (entre 3 y 25 palabras) donde aparece, y "documento": el número del documento del que sale.
- "confianza" entre 0 y 1: qué tan seguro estás de que la entidad y su rol son correctos.
- Tipos: agente (persona, entidad_corporativa, cargo o familia), lugar, fecha, actividad (la función o trámite que el documento documenta), forma_documental (tipo documental: oficio, acta, resolución, carta, etc.).
- Rol de un agente: productor (quien lo produce o firma), remitente, destinatario o mencionado.
- Para una fecha, "valor" es la expresión como aparece y "fecha_normalizada" es AAAA-MM-DD solo si el texto da día, mes y año; si no, vacío.
- "titulo": título formal breve del nivel descrito. "alcance_contenido": 2 a 6 frases de alcance y contenido (ISAD(G) 3.3.1) que sinteticen TODOS los documentos, sin opiniones.
Responde solo con el JSON pedido."""

ESQUEMA = {
    "type": "OBJECT",
    "properties": {
        "titulo": {"type": "STRING"},
        "alcance_contenido": {"type": "STRING"},
        "confianza_alcance": {"type": "NUMBER"},
        "entidades": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "tipo": {"type": "STRING", "enum": list(TIPOS)},
                    "subtipo": {"type": "STRING"},
                    "rol": {"type": "STRING"},
                    "valor": {"type": "STRING"},
                    "fecha_normalizada": {"type": "STRING"},
                    "fragmento": {"type": "STRING"},
                    "documento": {"type": "INTEGER"},
                    "confianza": {"type": "NUMBER"},
                },
                "required": ["tipo", "valor", "fragmento", "documento", "confianza"],
            },
        },
    },
    "required": ["titulo", "alcance_contenido", "entidades"],
}

NIVELES = {
    "unidad_documental": "una unidad documental (un solo documento)",
    "expediente": "un expediente (conjunto de documentos de un mismo trámite)",
    "subserie": "una subserie documental",
    "serie": "una serie documental",
}


class MotorGemini:
    def __init__(self, clave: str, modelo: str):
        self.clave = clave
        self.modelo = modelo
        self.nombre = modelo

    def analizar(self, documentos: list[Documento], nivel: str) -> dict:
        partes, total = [], 0
        for i, d in enumerate(documentos, start=1):
            texto = (d.texto or "")[:MAX_CARACTERES_DOCUMENTO]
            texto = texto[: max(0, MAX_CARACTERES_TOTAL - total)]
            total += len(texto)
            partes.append(f"[DOCUMENTO {i}: {d.nombre}]\n{texto or '(sin texto extraído)'}")
        pedido = (f"Describe {NIVELES.get(nivel, nivel)} formado por {len(documentos)} documento(s).\n\n"
                  + "\n\n".join(partes))
        cuerpo = {
            "systemInstruction": {"parts": [{"text": INSTRUCCION}]},
            "contents": [{"role": "user", "parts": [{"text": pedido}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json", "responseSchema": ESQUEMA},
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent"
        try:
            r = httpx.post(url, json=cuerpo, headers={"x-goog-api-key": self.clave}, timeout=settings.segundos_motor)
        except httpx.HTTPError as exc:
            raise MotorError("No hubo respuesta del motor de análisis.") from exc
        if r.status_code != 200:
            log.warning("Gemini respondió %s: %s", r.status_code, r.text[:300])
            raise MotorError(f"El motor de análisis respondió con un error ({r.status_code}).")
        try:
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(texto)
        except (KeyError, IndexError, ValueError) as exc:
            raise MotorError("La respuesta del motor no se pudo leer.") from exc


def motor_activo():
    """El motor configurado, o None si no hay ninguno."""
    if settings.gemini_api_key:
        return MotorGemini(settings.gemini_api_key, settings.modelo_ia)
    return None


# --- Normalización y control de la propuesta ----------------------------------------------


def _localizar(fragmento: str, texto: str) -> int | None:
    """Posición del fragmento en el texto: exacto, y si no, sin distinguir
    mayúsculas ni espacios."""
    if not fragmento or not texto:
        return None
    posicion = texto.find(fragmento)
    if posicion >= 0:
        return posicion
    patron = r"\s+".join(re.escape(p) for p in fragmento.split())
    hallado = re.search(patron, texto, flags=re.IGNORECASE)
    return hallado.start() if hallado else None


def _confianza(valor) -> float:
    try:
        return max(0.0, min(1.0, float(valor)))
    except (TypeError, ValueError):
        return 0.0


def _fecha(valor) -> str | None:
    try:
        return date.fromisoformat(str(valor)).isoformat() if valor else None
    except ValueError:
        return None


def normalizar(crudo: dict, documentos: list[Documento], motor: str) -> Propuesta:
    entidades = []
    for i, e in enumerate(crudo.get("entidades") or []):
        tipo = str(e.get("tipo", "")).strip().lower()
        valor = " ".join(str(e.get("valor", "")).split())[:300]
        if tipo not in TIPOS or not valor:
            continue
        indice = e.get("documento")
        documento = documentos[indice - 1] if isinstance(indice, int) and 1 <= indice <= len(documentos) else (
            documentos[0] if len(documentos) == 1 else None)
        fragmento = " ".join(str(e.get("fragmento", "")).split())[:500] or None
        inicio = _localizar(fragmento, documento.texto) if (fragmento and documento) else None
        if inicio is None and fragmento:
            # Buscar en los demás documentos antes de darlo por no localizado.
            for d in documentos:
                if (p := _localizar(fragmento, d.texto)) is not None:
                    documento, inicio = d, p
                    break
        confianza = _confianza(e.get("confianza"))
        if inicio is None:
            confianza = min(confianza, CONFIANZA_SIN_FRAGMENTO)
        rol = str(e.get("rol") or "").strip().lower() or None
        subtipo = str(e.get("subtipo") or "").strip().lower() or None
        if tipo == "agente":
            rol = rol if rol in ROLES_AGENTE else "mencionado"
            subtipo = subtipo if subtipo in SUBTIPOS_AGENTE else "persona"
        entidades.append(EntidadPropuesta(
            clave=f"p{i + 1}", tipo=tipo, valor=valor, subtipo=subtipo, rol=rol,
            fecha_normalizada=_fecha(e.get("fecha_normalizada")) if tipo == "fecha" else None,
            fragmento=fragmento, documento_id=str(documento.id) if documento and inicio is not None else None,
            inicio=inicio, confianza=round(confianza, 2), fragmento_localizado=inicio is not None,
        ))
    return Propuesta(
        titulo=" ".join(str(crudo.get("titulo", "")).split())[:300],
        alcance=str(crudo.get("alcance_contenido", "")).strip()[:5000],
        confianza_alcance=_confianza(crudo.get("confianza_alcance", 0.8)),
        entidades=entidades, motor=motor, disponible=True,
    )


def proponer(documentos: list[Documento], nivel: str) -> Propuesta:
    motor = motor_activo()
    if motor is None:
        return Propuesta(aviso="No hay un motor de análisis configurado en el servidor. Puede describir a mano: "
                               "escriba el título y el alcance, y agregue las entidades.")
    if not any((d.texto or "").strip() for d in documentos):
        return Propuesta(motor=motor.nombre, aviso="Los documentos no tienen texto extraído (por ejemplo, una imagen "
                                                   "sin texto legible). Describa a mano.")
    try:
        return normalizar(motor.analizar(documentos, nivel), documentos, motor.nombre)
    except MotorError as exc:
        return Propuesta(motor=motor.nombre, aviso=f"{exc} Puede describir a mano o volver a intentarlo más tarde.")
