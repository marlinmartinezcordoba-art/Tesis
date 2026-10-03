"""
Motor de análisis: propone la descripción de uno o varios documentos a
partir de su texto ya extraído en la ingesta.

La inteligencia artificial propone y nunca decide: todo lo que devuelve
este módulo es una propuesta que el archivista acepta, edita o descarta.
Cada entidad propuesta viene con el fragmento exacto del que salió; si ese
fragmento no aparece de verdad en el texto, la confianza se rebaja y se
marca, para que nadie publique algo que el motor pudo inventar.
"""

import hashlib
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field

import httpx

from app.core.config import settings
from app.servicios import fechas

log = logging.getLogger("ricora.motor")

TIPOS = ("agente", "lugar", "fecha", "actividad", "tipo_actividad", "mandato", "forma_documental")
ROLES_AGENTE = ("productor", "remitente", "destinatario", "mencionado")
from app.models.descripcion import SUBTIPO_AGENTE as SUBTIPOS_AGENTE  # noqa: E402
SUBTIPOS_MANDATO = ("ley", "decreto", "ordenanza", "acuerdo", "resolucion", "otro")

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
    # Fecha en EDTF: la de una entidad fecha, el periodo de una actividad o
    # la expedición de un mandato. fecha_subtipo: simple, rango o conjunto.
    edtf: str | None = None
    fecha_subtipo: str | None = None
    fecha_legible: str | None = None
    # Cadena de contexto de una actividad: claves de otras entidades de la
    # misma propuesta (tipo de actividad, agente que la ejerce, mandato).
    tipo_clave: str | None = None
    agente_clave: str | None = None
    mandato_clave: str | None = None
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
    version_prompt: str | None = None
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
- Tipos: agente (subtipo persona, entidad_corporativa, grupo —un colectivo sin personería, como un comité o una junta—, cargo, familia o mecanismo), lugar, fecha, actividad, mandato y forma_documental (tipo documental: oficio, acta, resolución, carta, etc.).
- Rol de un agente: productor (quien lo produce o firma), remitente, destinatario o mencionado.
- Fecha: "valor" es la expresión como aparece; "subtipo_fecha" es simple, rango o conjunto; "edtf" es su forma en EDTF, usando SOLO estas formas: 1948-03-15 (exacta), 1948-03 o 1948 (sin día o sin mes), 1948~ (aproximada, «hacia 1948»), 1948? (incierta), 1948% (las dos), 194X (década), 19XX (siglo), 1948/1952 (rango), /1952 o 1948/ (un extremo desconocido), {1948-01-15,1948-03-02} (fechas sueltas de un mismo hecho repetido). Nunca inventes precisión que el texto no da.
- Actividad: el ejercicio concreto de una competencia por un agente en un periodo, que el documento documenta (por ejemplo «Ejercicio de la policía local por la Alcaldía, 1948»). En la misma entidad indica, si el texto lo permite: "tipo_actividad" (la competencia estable y reutilizable, por ejemplo «Policía local», «Registro civil», «Hacienda municipal»), "ejercida_por" (el valor exacto de uno de los agentes que propusiste) y "mandato" (el valor exacto de uno de los mandatos que propusiste). Su periodo va en "edtf".
- Mandato: la ley, decreto, ordenanza, acuerdo o resolución que el texto cita como fundamento. "subtipo" es el instrumento (ley, decreto, ordenanza, acuerdo, resolucion u otro); "edtf", su fecha de expedición si aparece.
- Si el texto no permite identificar actividad, tipo de actividad o mandato con confianza razonable, no los propongas: no es obligatorio.
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
                    "subtipo_fecha": {"type": "STRING", "enum": list(fechas.SUBTIPOS)},
                    "edtf": {"type": "STRING"},
                    "tipo_actividad": {"type": "STRING"},
                    "ejercida_por": {"type": "STRING"},
                    "mandato": {"type": "STRING"},
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

# Identificador de la versión de las instrucciones que recibe el motor:
# resumen SHA-256 de la instrucción y del esquema de respuesta. Cambia solo
# si cambia lo que se le pide; queda en cada propuesta y en cada decisión
# registrada en auditoría, para saber con qué instrucción se obtuvo.
VERSION_PROMPT = hashlib.sha256(
    (INSTRUCCION + json.dumps(ESQUEMA, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()[:8]

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
        try:
            return json.loads(self._llamar(cuerpo))
        except ValueError as exc:
            raise MotorError("La respuesta del motor no se pudo leer.") from exc

    def redactar(self, instruccion: str, pedido: str) -> str:
        """Texto libre (p. ej. la nota de presentación de la guía)."""
        cuerpo = {
            "systemInstruction": {"parts": [{"text": instruccion}]},
            "contents": [{"role": "user", "parts": [{"text": pedido}]}],
            "generationConfig": {"temperature": 0.3},
        }
        return self._llamar(cuerpo).strip()

    def _llamar(self, cuerpo: dict) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent"
        try:
            r = httpx.post(url, json=cuerpo, headers={"x-goog-api-key": self.clave}, timeout=settings.segundos_motor)
        except httpx.HTTPError as exc:
            raise MotorError("No hubo respuesta del motor de análisis.") from exc
        if r.status_code != 200:
            log.warning("Gemini respondió %s: %s", r.status_code, r.text[:300])
            raise MotorError(f"El motor de análisis respondió con un error ({r.status_code}).")
        try:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
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


def _fecha_edtf(e: dict) -> tuple[str | None, str | None, str | None]:
    """(edtf, subtipo, forma legible) de lo que propuso el motor, o None si no
    es una expresión válida del subconjunto: la archivista la completa."""
    crudo = str(e.get("edtf") or "").strip()
    if not crudo and e.get("fecha_normalizada"):  # respuestas en el formato anterior
        crudo = str(e.get("fecha_normalizada")).strip()
    if not crudo:
        return None, None, None
    try:
        i = fechas.interpretar(crudo)
    except fechas.FechaInvalida:
        return None, None, None
    return i.edtf, i.subtipo, i.legible


def _norm(texto: str) -> str:
    return " ".join(str(texto or "").split()).casefold()


def normalizar(crudo: dict, documentos: list[Documento], motor: str) -> Propuesta:
    entidades: list[EntidadPropuesta] = []
    pendientes_contexto: list[tuple[EntidadPropuesta, dict]] = []
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
        elif tipo == "mandato":
            subtipo = subtipo if subtipo in SUBTIPOS_MANDATO else "otro"
            rol = None
        else:
            rol = subtipo = None
        edtf, fecha_subtipo, fecha_legible = _fecha_edtf(e) if tipo in ("fecha", "actividad", "mandato") else (None,) * 3
        propuesta = EntidadPropuesta(
            clave=f"p{i + 1}", tipo=tipo, valor=valor, subtipo=subtipo, rol=rol,
            fecha_normalizada=edtf if (tipo == "fecha" and edtf and re.fullmatch(r"\d{4}-\d{2}-\d{2}", edtf)) else None,
            edtf=edtf, fecha_subtipo=fecha_subtipo, fecha_legible=fecha_legible,
            fragmento=fragmento, documento_id=str(documento.id) if documento and inicio is not None else None,
            inicio=inicio, confianza=round(confianza, 2), fragmento_localizado=inicio is not None,
        )
        entidades.append(propuesta)
        if tipo == "actividad":
            pendientes_contexto.append((propuesta, e))
    _enlazar_contexto(entidades, pendientes_contexto)
    return Propuesta(
        titulo=" ".join(str(crudo.get("titulo", "")).split())[:300],
        alcance=str(crudo.get("alcance_contenido", "")).strip()[:5000],
        confianza_alcance=_confianza(crudo.get("confianza_alcance", 0.8)),
        entidades=entidades, motor=motor, version_prompt=VERSION_PROMPT, disponible=True,
    )


def _enlazar_contexto(entidades: list[EntidadPropuesta], actividades: list[tuple[EntidadPropuesta, dict]]) -> None:
    """Convierte los nombres que el motor dio para el tipo de actividad, el
    agente y el mandato de cada actividad en claves de la propuesta. Un tipo
    de actividad o un mandato que no venía como entidad aparte se agrega como
    propuesta propia (con el mismo fragmento): la archivista decide cada uno.
    Un agente que no se propuso no se inventa."""
    def buscar(tipo: str, valor: str) -> EntidadPropuesta | None:
        return next((x for x in entidades if x.tipo == tipo and _norm(x.valor) == _norm(valor)), None)

    for act, crudo in actividades:
        tipo_valor = " ".join(str(crudo.get("tipo_actividad") or "").split())[:300]
        if tipo_valor:
            tipo = buscar("tipo_actividad", tipo_valor)
            if tipo is None:
                tipo = EntidadPropuesta(clave=f"{act.clave}t", tipo="tipo_actividad", valor=tipo_valor,
                                        fragmento=act.fragmento, documento_id=act.documento_id, inicio=act.inicio,
                                        confianza=act.confianza, fragmento_localizado=act.fragmento_localizado)
                entidades.append(tipo)
            act.tipo_clave = tipo.clave
        mandato_valor = " ".join(str(crudo.get("mandato") or "").split())[:300]
        if mandato_valor:
            mandato = buscar("mandato", mandato_valor)
            if mandato is None:
                mandato = EntidadPropuesta(clave=f"{act.clave}m", tipo="mandato", valor=mandato_valor, subtipo="otro",
                                           fragmento=act.fragmento, documento_id=act.documento_id, inicio=act.inicio,
                                           confianza=min(act.confianza, CONFIANZA_SIN_FRAGMENTO),
                                           fragmento_localizado=act.fragmento_localizado)
                entidades.append(mandato)
            act.mandato_clave = mandato.clave
        agente_valor = str(crudo.get("ejercida_por") or "")
        if agente_valor and (agente := buscar("agente", agente_valor)) is not None:
            act.agente_clave = agente.clave


def proponer(documentos: list[Documento], nivel: str) -> Propuesta:
    motor = motor_activo()
    if motor is None:
        return Propuesta(aviso="No hay un motor de análisis configurado en el servidor. Puede describir a mano: "
                               "escriba el título y el alcance, y agregue las entidades.")
    if not any((d.texto or "").strip() for d in documentos):
        return Propuesta(motor=motor.nombre, version_prompt=VERSION_PROMPT, aviso="Los documentos no tienen texto extraído (por ejemplo, una imagen "
                                                   "sin texto legible). Describa a mano.")
    try:
        return normalizar(motor.analizar(documentos, nivel), documentos, motor.nombre)
    except MotorError as exc:
        return Propuesta(motor=motor.nombre, version_prompt=VERSION_PROMPT,
                         aviso=f"{exc} Puede describir a mano o volver a intentarlo más tarde.")
