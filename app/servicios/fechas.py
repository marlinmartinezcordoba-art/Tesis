"""
Fechas en formato extendido (EDTF, ISO 8601-2), limitado al subconjunto
que necesita un fondo histórico (decisión en
documentacion/modulo-2-descripcion.md):

- nivel 0: año, año-mes, año-mes-día, e intervalo «inicio/fin»;
- nivel 1: calificadores al final (? incierta, ~ aproximada, % ambas),
  dígitos sin precisar con X (194X, 19XX, 1948-XX) y extremos desconocidos
  de un intervalo («/1952», «1948/»);
- nivel 2: solo el conjunto de fechas discretas «{a,b,c}».

Quedan fuera, aunque el estándar los tenga: estaciones (1948-21), años
con exponente o cifras significativas, años negativos, calificadores por
componente, calificadores dentro de un conjunto ({1948~,1949}), dígitos sin
precisar que no van «desde la derecha» (1948-XX-12) y el conjunto «una de»
([a,b]). Un extremo de intervalo se modela como «desconocido» («/1952»), no
como «abierto» («../1952»): en un fondo cerrado lo que falta es el dato, no
una fecha que siga corriendo.

Dos capas: un filtro propio que acota el subconjunto (expresiones
regulares) y la librería `edtf`, que confirma que la expresión es EDTF
válido (por ejemplo, que el 30 de febrero no existe). Los límites del
intervalo (inicio, fin) se calculan aquí: la librería inventa un margen de
diez años para un extremo desconocido, y un archivo no debe inventar.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date

from edtf import parse_edtf
from edtf.parser.edtf_exceptions import EDTFParseException

SUBTIPOS = ("simple", "rango", "conjunto")

# Dígitos sin precisar de nivel 1: solo «desde la derecha» (194X, 1948-XX,
# 1948-03-XX). Un día preciso con el mes sin precisar (1948-XX-12) o un mes
# preciso con el año sin precisar (194X-03) es nivel 2 y queda fuera: antes
# se admitía y la forma legible perdía el día (hallazgo DES-03).
_FECHA = (r"(?:\d{4}(?:-(?:(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]|XX))?|XX(?:-XX)?))?"
          r"|(?:\d{3}X|\d{2}XX|XXXX)(?:-XX(?:-XX)?)?)")
_SIMPLE = re.compile(rf"^({_FECHA})([?~%])?$")
_RANGO = re.compile(rf"^(?:({_FECHA})([?~%])?)?/(?:({_FECHA})([?~%])?)?$")
_CONJUNTO = re.compile(rf"^\{{({_FECHA}(?:,{_FECHA})+)\}}$")

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


class FechaInvalida(ValueError):
    pass


@dataclass(frozen=True)
class Interpretacion:
    edtf: str
    subtipo: str
    legible: str
    inicio: date | None
    fin: date | None
    exacta: date | None  # el día, si es una fecha simple exacta sin calificador


def subtipo_de(edtf: str) -> str:
    if edtf.startswith("{"):
        return "conjunto"
    return "rango" if "/" in edtf else "simple"


def _limites(token: str) -> tuple[date | None, date | None]:
    """Primer y último día que cubre una fecha (con X sin precisar)."""
    partes = token.split("-")
    anio = partes[0]
    if anio == "XXXX":
        return None, None
    a_min, a_max = int(anio.replace("X", "0")), int(anio.replace("X", "9"))
    if len(partes) == 1 or partes[1] == "XX":
        return date(a_min, 1, 1), date(a_max, 12, 31)
    mes = int(partes[1])
    if len(partes) == 2 or partes[2] == "XX":
        return date(a_min, mes, 1), date(a_max, mes, calendar.monthrange(a_max, mes)[1])
    return date(a_min, mes, int(partes[2])), date(a_max, mes, int(partes[2]))


def _legible_fecha(token: str) -> str:
    partes = token.split("-")
    anio = partes[0]
    if anio == "XXXX":
        texto_anio = "año desconocido"
    elif anio.endswith("XX"):
        siglo = int(anio[:2]) + 1
        texto_anio = f"siglo {_romano(siglo)} ({anio[:2]}00–{anio[:2]}99)"
    elif anio.endswith("X"):
        texto_anio = f"década de {anio[:3]}0"
    else:
        texto_anio = anio
    if len(partes) == 1 or partes[1] == "XX":
        return texto_anio if len(partes) == 1 else f"{texto_anio} (mes sin precisar)"
    mes = MESES[int(partes[1]) - 1]
    if len(partes) == 2:
        return f"{mes} de {texto_anio}"
    if partes[2] == "XX":
        return f"{mes} de {texto_anio} (día sin precisar)"
    return f"{int(partes[2])} de {mes} de {texto_anio}"


def _con_calificador(texto: str, calificador: str | None) -> str:
    if calificador == "~":
        return f"c. {texto}"
    if calificador == "?":
        return f"{texto} (incierta)"
    if calificador == "%":
        return f"c. {texto} (incierta)"
    return texto


def _romano(n: int) -> str:
    valores = ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    salida = ""
    for v, letra in valores:
        while n >= v:
            salida += letra
            n -= v
    return salida


def _confirmar_con_libreria(edtf: str) -> None:
    try:
        parse_edtf(edtf)
    except (EDTFParseException, ValueError, TypeError) as exc:
        raise FechaInvalida(f"«{edtf}» no es una fecha válida.") from exc
    # La librería no rechaza todos los días imposibles dentro de un conjunto.
    for token in re.findall(r"\d{4}-\d{2}-\d{2}", edtf):
        try:
            date.fromisoformat(token)
        except ValueError as exc:
            raise FechaInvalida(f"«{token}» no es un día que exista.") from exc


def interpretar(edtf: str, subtipo: str | None = None) -> Interpretacion:
    """Valida la expresión contra el subconjunto y devuelve su forma legible
    en español y sus límites. `subtipo`, si se da, tiene que coincidir."""
    edtf = (edtf or "").strip().replace(" ", "")
    if not edtf:
        raise FechaInvalida("Falta la fecha.")
    real = subtipo_de(edtf)
    if subtipo and subtipo != real:
        nombres = {"simple": "una fecha simple", "rango": "un rango de fechas", "conjunto": "un conjunto de fechas"}
        raise FechaInvalida(f"«{edtf}» es {nombres[real]}, no {nombres[subtipo]}.")
    if real == "simple":
        m = _SIMPLE.match(edtf)
        if not m:
            raise FechaInvalida(f"«{edtf}» no es una fecha que este sistema admita.")
        _confirmar_con_libreria(edtf)
        inicio, fin = _limites(m.group(1))
        legible = _con_calificador(_legible_fecha(m.group(1)), m.group(2))
        exacta = inicio if (inicio and inicio == fin and not m.group(2)) else None
        return Interpretacion(edtf, real, legible, inicio, fin, exacta)
    if real == "rango":
        m = _RANGO.match(edtf)
        if not m or (not m.group(1) and not m.group(3)):
            raise FechaInvalida(f"«{edtf}» no es un rango que este sistema admita.")
        _confirmar_con_libreria(edtf)
        inicio = _limites(m.group(1))[0] if m.group(1) else None
        fin = _limites(m.group(3))[1] if m.group(3) else None
        if inicio and fin and inicio > fin:
            raise FechaInvalida("El inicio del rango es posterior a su fin.")
        a = _con_calificador(_legible_fecha(m.group(1)), m.group(2)) if m.group(1) else None
        b = _con_calificador(_legible_fecha(m.group(3)), m.group(4)) if m.group(3) else None
        legible = (f"de {a} a {b}" if a and b else f"hasta {b} (inicio desconocido)" if b
                   else f"desde {a} (fin desconocido)")
        return Interpretacion(edtf, real, legible, inicio, fin, None)
    m = _CONJUNTO.match(edtf)
    if not m:
        raise FechaInvalida(f"«{edtf}» no es un conjunto de fechas que este sistema admita.")
    _confirmar_con_libreria(edtf)
    tokens = m.group(1).split(",")
    limites = [_limites(t) for t in tokens]
    inicios = [i for i, _ in limites if i]
    fines = [f for _, f in limites if f]
    textos = [_legible_fecha(t) for t in tokens]
    legible = ", ".join(textos[:-1]) + f" y {textos[-1]}"
    return Interpretacion(edtf, real, legible, min(inicios) if inicios else None, max(fines) if fines else None, None)


def legible(edtf: str | None, expresion: str | None = None) -> str | None:
    """Forma legible para mostrar; si no hay EDTF (fechas antiguas), la
    expresión tal como se escribió."""
    if not edtf:
        return expresion
    try:
        return interpretar(edtf).legible
    except FechaInvalida:
        return expresion or edtf


_EXTREMAS = re.compile(r"^\s*(\d{4})\s*(?:(?:[–—-]|a|al|hasta|/)\s*(\d{4}))?\s*$", re.IGNORECASE)


def extremas(texto: str | None) -> Interpretacion | None:
    """Fechas extremas de un conjunto (fondo, serie, expediente) en EDTF
    (hallazgos CM-01, CM-16 y DES-02): «1930–1955», «1930 a 1955»,
    «1930-1955» o ya en EDTF («1930/1955», «1930~/1955»). Lo que no se
    pueda interpretar se rechaza: nunca queda texto libre sin normalizar."""
    texto = (texto or "").strip()
    if not texto:
        return None
    m = _EXTREMAS.match(texto)
    if m:
        texto = f"{m.group(1)}/{m.group(2)}" if m.group(2) else m.group(1)
    return interpretar(texto)
