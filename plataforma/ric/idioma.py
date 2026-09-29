"""M2 (RF-M2-03): detectar el idioma del texto extraído.

Heurística por palabras vacías (stopwords), sin modelo ni dependencia
nueva: cuenta cuántas de las palabras más frecuentes de cada idioma
aparecen en el texto y se queda con el idioma que más suma. Es suficiente
para distinguir español, inglés, portugués y francés en documentos
administrativos; devuelve "" si el texto es demasiado corto para decidir.
"""

import re

_STOPWORDS = {
    "es": {"el", "la", "de", "que", "y", "en", "los", "las", "del", "se", "por", "con", "para", "una", "es", "al", "como", "su", "sus", "este", "esta"},
    "en": {"the", "of", "and", "to", "in", "is", "that", "for", "with", "as", "this", "by", "on", "are", "be", "from", "at", "or", "an", "it"},
    "pt": {"o", "a", "de", "que", "e", "do", "da", "em", "um", "para", "com", "não", "uma", "os", "no", "na", "por", "mais", "as", "dos"},
    "fr": {"le", "la", "de", "et", "les", "des", "en", "un", "une", "du", "que", "qui", "dans", "pour", "pas", "sur", "au", "est", "ce", "il"},
}
NOMBRES = {"es": "Español", "en": "Inglés", "pt": "Portugués", "fr": "Francés"}
_MIN_PALABRAS = 8


def detectar_idioma(texto):
    palabras = re.findall(r"[a-záéíóúñüàâçèêëîïôùûœ]+", (texto or "").lower())
    if len(palabras) < _MIN_PALABRAS:
        return ""
    puntajes = {codigo: sum(1 for p in palabras if p in vacias) for codigo, vacias in _STOPWORDS.items()}
    codigo, mejor = max(puntajes.items(), key=lambda kv: kv[1])
    if mejor == 0:
        return ""
    return codigo


def nombre_idioma(codigo):
    return NOMBRES.get(codigo, codigo or "")
