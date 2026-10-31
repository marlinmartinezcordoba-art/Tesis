"""
Objetivo 3 de la tesis convertido en lógica: lo que el capítulo III promete
y el sistema ahora calcula, en lugar de dejarlo a una hoja de cálculo.

- Criterio de comparabilidad, fijado antes de iniciar la evaluación: un tipo
  de entidad es comparable si la F flexible del motor no queda más de
  `margen_f` por debajo del acuerdo F entre las archivistas en ese tipo
  (con al menos `minimo_casos` entidades de referencia), si la conformidad
  de las descripciones asistidas con RiC-O alcanza `conformidad_asistida`
  y si la media de la rúbrica es al menos `rubrica_minima` en los tres
  criterios. El acuerdo entre archivistas es el techo: no se le exige al
  motor más coincidencia que la que tienen entre sí dos profesionales.
- Supervisión en la condición asistida: cada entidad que propuso el motor
  quedó aceptada (igual), corregida (parecida) o rechazada (ausente); lo que
  la archivista añadió es «agregada».
- Desacuerdos: cada diferencia entre el motor y una referencia ciega, con una
  clave estable, para clasificarla con la taxonomía de errores. Dos
  investigadoras clasifican por separado; si difieren, deciden por consenso.
  El acuerdo entre ellas se mide con el kappa de Cohen (categorías nominales).
- Intervalos de confianza del 95 % para la F por remuestreo de documentos
  (Efron y Tibshirani, 1993): las entidades de un mismo documento no son
  independientes, así que se remuestrean documentos, no entidades.
- Prueba de rangos con signo de Wilcoxon (1945) para los tiempos pareados de
  una misma archivista en un mismo documento, ciega frente a asistida.

Todo son funciones puras salvo las de clasificación, que leen y escriben.
"""

import hashlib
import math
import random
import uuid
from collections import Counter
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import ahora

CRITERIO_POR_DEFECTO = {"margen_f": 0.10, "minimo_casos": 10, "rubrica_minima": 3.0, "conformidad_asistida": 1.0}
LIMITES_CRITERIO = {"margen_f": (0.0, 0.5), "minimo_casos": (1, 1000), "rubrica_minima": (1.0, 5.0),
                    "conformidad_asistida": (0.0, 1.0)}

# Taxonomía de errores de la tesis (capítulo III).
TIPOS_ERROR = {
    "reconocimiento": "Error de reconocimiento de texto",
    "sin_sustento": "Entidad sin sustento",
    "papel": "Papel equivocado",
    "normalizacion": "Normalización errónea",
    "granularidad": "Granularidad distinta",
    "omision": "Omisión",
    "criterio": "Diferencia de criterio",
}
CLASES_DESACUERDO = {
    "sobrante": "El motor la propuso; la archivista no la registró",
    "faltante": "La archivista la registró; el motor no la propuso",
    "variante": "Los dos la registraron con un valor distinto",
    "otra_relacion": "Los mismos extremos con otra relación",
    "relacion_sobrante": "Relación que propuso el motor y la archivista no",
    "relacion_faltante": "Relación que registró la archivista y el motor no",
}
REMUESTREOS = 1000
SEMILLA = 20261031  # fija: el mismo conjunto de datos da siempre el mismo intervalo


class ErrorAnalisis(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def _r(x: float | None, d: int = 4) -> float | None:
    return round(x, d) if x is not None else None


# --- Criterio de comparabilidad --------------------------------------------------------------------


def criterio_de(guardado: dict | None) -> dict:
    return CRITERIO_POR_DEFECTO | (guardado or {})


def validar_criterio(datos: dict) -> dict:
    salida = {}
    for k, (minimo, maximo) in LIMITES_CRITERIO.items():
        v = datos.get(k, CRITERIO_POR_DEFECTO[k])
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not minimo <= v <= maximo:
            raise ErrorAnalisis(f"«{k}» debe estar entre {minimo} y {maximo}.")
        salida[k] = int(v) if k == "minimo_casos" else float(v)
    return salida


def veredicto(resultados: dict, criterio: dict) -> dict:
    """Aplica el criterio, tipo por tipo, a los resultados ya calculados."""
    c = criterio_de(criterio)
    conf = resultados["conformidad"].get("asistida") or {"descripciones": 0, "conformes": 0}
    tasa_asistida = conf["conformes"] / conf["descripciones"] if conf["descripciones"] else None
    medias = {k: v.get("media") for k, v in resultados["rubrica"].items()}
    condiciones = {
        "conformidad_asistida": {"valor": _r(tasa_asistida), "exigido": c["conformidad_asistida"],
                                 "cumple": tasa_asistida is not None and tasa_asistida >= c["conformidad_asistida"]},
        "rubrica": {"valor": medias, "exigido": c["rubrica_minima"],
                    "cumple": bool(medias) and all(m is not None and m >= c["rubrica_minima"] for m in medias.values())},
    }
    tipos = []
    for tipo, f in resultados["flexible"]["por_tipo"].items():
        casos = f["vp"] + f["fn"]  # entidades de referencia
        techo = (resultados.get("acuerdo_por_tipo") or {}).get(tipo, {}).get("f1")
        motivos = []
        if casos < c["minimo_casos"]:
            estado = "datos_insuficientes"
            motivos.append(f"{casos} entidad(es) de referencia; se exigen {c['minimo_casos']}")
        elif techo is None:
            estado = "sin_techo"
            motivos.append("no hay dos descripciones ciegas del mismo documento con este tipo")
        else:
            diferencia = (techo or 0) - (f["f1"] or 0)
            if diferencia > c["margen_f"]:
                motivos.append(f"la F del motor queda {_r(diferencia, 3)} por debajo del acuerdo entre archivistas")
            if not condiciones["conformidad_asistida"]["cumple"]:
                motivos.append("la conformidad de las descripciones asistidas no alcanza lo exigido")
            if not condiciones["rubrica"]["cumple"]:
                motivos.append("la rúbrica no alcanza la media exigida en los tres criterios")
            estado = "no_comparable" if motivos else "comparable"
        tipos.append({"tipo": tipo, "casos": casos, "f_motor": f["f1"], "techo": techo,
                      "diferencia": _r(techo - f["f1"]) if techo is not None and f["f1"] is not None else None,
                      "estado": estado, "motivos": motivos})
    return {"criterio": c, "condiciones": condiciones, "tipos": tipos,
            "comparables": [t["tipo"] for t in tipos if t["estado"] == "comparable"],
            "no_comparables": [t["tipo"] for t in tipos if t["estado"] == "no_comparable"],
            "sin_decidir": [t["tipo"] for t in tipos if t["estado"] in ("datos_insuficientes", "sin_techo")]}


# --- Emparejamiento con detalle ----------------------------------------------------------------------


def pares(sistema: list[dict], referencia: list[dict], umbral: float) -> list[tuple[int, int, float]]:
    """Como evaluacion.emparejar, pero devuelve qué entidad va con cuál y su
    parecido: uno a uno, del más parecido al menos, dentro del mismo tipo."""
    from app.servicios.evaluacion import clave_de, texto_de

    salida = []
    for grupo in {clave_de(e) for e in sistema} & {clave_de(e) for e in referencia}:
        s = [(i, texto_de(e)) for i, e in enumerate(sistema) if clave_de(e) == grupo]
        r = [(j, texto_de(e)) for j, e in enumerate(referencia) if clave_de(e) == grupo]
        candidatos = sorted(((SequenceMatcher(None, a, b).ratio() if a != b else 1.0, i, j)
                             for i, a in s for j, b in r), reverse=True)
        usados_s, usados_r = set(), set()
        for parecido, i, j in candidatos:
            if parecido < umbral:
                break
            if i not in usados_s and j not in usados_r:
                usados_s.add(i)
                usados_r.add(j)
                salida.append((i, j, parecido))
    return salida


def supervision(motor: list[dict], asistida: list[dict], umbral: float) -> dict:
    """Qué hizo la archivista con cada propuesta en la condición asistida."""
    from app.servicios.evaluacion import TIPOS

    cuentas = {t: {"aceptada": 0, "corregida": 0, "rechazada": 0, "agregada": 0} for t in TIPOS}
    emparejados = pares(motor, asistida, umbral)
    usados_m = {i for i, _, _ in emparejados}
    usados_a = {j for _, j, _ in emparejados}
    for i, _, parecido in emparejados:
        cuentas[motor[i]["tipo"]]["aceptada" if parecido >= 1.0 else "corregida"] += 1
    for i, e in enumerate(motor):
        if i not in usados_m and e["tipo"] in cuentas:
            cuentas[e["tipo"]]["rechazada"] += 1
    for j, e in enumerate(asistida):
        if j not in usados_a and e["tipo"] in cuentas:
            cuentas[e["tipo"]]["agregada"] += 1
    return {t: c for t, c in cuentas.items() if sum(c.values())}


def resumen_supervision(por_tipo: dict) -> dict:
    total = Counter()
    for c in por_tipo.values():
        total.update(c)
    propuestas = total["aceptada"] + total["corregida"] + total["rechazada"]

    def pct(x, base):
        return _r(100 * x / base, 1) if base else None
    return {"por_tipo": por_tipo, "total": dict(total), "propuestas": propuestas,
            "pct_aceptadas": pct(total["aceptada"], propuestas), "pct_corregidas": pct(total["corregida"], propuestas),
            "pct_rechazadas": pct(total["rechazada"], propuestas),
            "pct_agregadas": pct(total["agregada"], total["aceptada"] + total["corregida"] + total["agregada"])}


# --- Desacuerdos ---------------------------------------------------------------------------------------


def _texto_entidad(e: dict | None) -> str:
    if e is None:
        return "este documento"
    v = (e.get("valor") or "").strip()
    return f"{v} ({e['edtf']})" if e.get("tipo") == "fecha" and e.get("edtf") and e.get("edtf") != v else v


def _clave(*partes) -> str:
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:40]


def desacuerdos(documento_id: str, referencia_id: str, motor: list[dict], referencia: list[dict],
                motor_rel: list, referencia_rel: list, umbral: float) -> list[dict]:
    """Cada diferencia entre el motor y una referencia ciega, con una clave
    que no cambia mientras los datos no cambien."""
    from app.servicios import evaluacion_ric as ric

    salida = []
    vistos: Counter = Counter()

    def agregar(clase, tipo, del_motor, de_archivista, propiedad=None, propiedad_archivista=None):
        base = (documento_id, referencia_id, clase, tipo, propiedad, propiedad_archivista, del_motor, de_archivista)
        vistos[base] += 1
        salida.append({"clave": _clave(*base, vistos[base]), "documento_id": documento_id, "referencia_id": referencia_id,
                       "clase": clase, "clase_nombre": CLASES_DESACUERDO[clase], "tipo": tipo,
                       "propiedad": propiedad, "propiedad_archivista": propiedad_archivista,
                       "motor": del_motor, "archivista": de_archivista})

    emparejados = pares(motor, referencia, umbral)
    for i, j, parecido in emparejados:
        if parecido < 1.0:
            agregar("variante", motor[i]["tipo"], _texto_entidad(motor[i]), _texto_entidad(referencia[j]))
    usados_m = {i for i, _, _ in emparejados}
    usados_r = {j for _, j, _ in emparejados}
    for i, e in enumerate(motor):
        if i not in usados_m:
            agregar("sobrante", e["tipo"], _texto_entidad(e), None)
    for j, e in enumerate(referencia):
        if j not in usados_r:
            agregar("faltante", e["tipo"], None, _texto_entidad(e))

    # Relaciones: misma propiedad y extremos parecidos = acierto; mismos extremos con otra propiedad = confusión.
    def pares_rel(mismo: bool, libres_m: set, libres_r: set):
        candidatos = sorted(((ric._parecido(s, r), i, j) for i, s in enumerate(motor_rel) for j, r in enumerate(referencia_rel)
                             if (s[0] == r[0]) == mismo and i in libres_m and j in libres_r), reverse=True)
        hechos = []
        for parecido, i, j in candidatos:
            if parecido < umbral:
                break
            if i in libres_m and j in libres_r:
                libres_m.discard(i)
                libres_r.discard(j)
                hechos.append((i, j))
        return hechos

    libres_m, libres_r = set(range(len(motor_rel))), set(range(len(referencia_rel)))
    pares_rel(True, libres_m, libres_r)
    texto_rel = lambda t: f"{_texto_entidad(t[1])} → {_texto_entidad(t[2])}"  # noqa: E731
    for i, j in pares_rel(False, libres_m, libres_r):
        agregar("otra_relacion", "relacion", texto_rel(motor_rel[i]), texto_rel(referencia_rel[j]),
                propiedad=motor_rel[i][0], propiedad_archivista=referencia_rel[j][0])
    for i in sorted(libres_m):
        agregar("relacion_sobrante", "relacion", texto_rel(motor_rel[i]), None, propiedad=motor_rel[i][0])
    for j in sorted(libres_r):
        agregar("relacion_faltante", "relacion", None, texto_rel(referencia_rel[j]), propiedad=referencia_rel[j][0])
    return salida


def kappa_nominal(pares_: list[tuple[str, str]]) -> float | None:
    """Kappa de Cohen entre dos clasificadoras, categorías nominales."""
    if not pares_:
        return None
    n = len(pares_)
    observado = sum(1 for a, b in pares_ if a == b) / n
    ca, cb = Counter(a for a, _ in pares_), Counter(b for _, b in pares_)
    esperado = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return _r((observado - esperado) / (1 - esperado)) if esperado < 1 else (1.0 if observado == 1 else None)


def resumen_clasificaciones(claves: list[str], filas: list) -> dict:
    """La clasificación final de cada desacuerdo (el consenso, o el acuerdo de
    las dos clasificadoras), el kappa entre ellas y lo que falta."""
    individuales: dict[str, dict] = {}
    consenso: dict[str, str] = {}
    for f in filas:
        if f.ronda == "consenso":
            consenso[f.clave] = f.tipo_error
        else:
            individuales.setdefault(f.clave, {})[f.clasificadora_id] = f.tipo_error
    clasificadoras = sorted({f.clasificadora_id for f in filas if f.ronda == "individual"}, key=str)
    pares_ = []
    if len(clasificadoras) >= 2:
        a, b = clasificadoras[:2]
        pares_ = [(v[a], v[b]) for v in individuales.values() if a in v and b in v]
    finales: dict[str, str] = {}
    pendientes_consenso = 0
    for clave in claves:
        if clave in consenso:
            finales[clave] = consenso[clave]
            continue
        valores = set((individuales.get(clave) or {}).values())
        if len(valores) == 1 and len(individuales.get(clave, {})) >= min(2, len(clasificadoras) or 1):
            finales[clave] = valores.pop()
        elif len(valores) > 1:
            pendientes_consenso += 1
    distribucion = Counter(finales.values())
    return {"desacuerdos": len(claves), "clasificados": len(finales), "pendientes_consenso": pendientes_consenso,
            "sin_clasificar": len(claves) - len(finales) - pendientes_consenso,
            "clasificadoras": len(clasificadoras), "pares": len(pares_), "kappa": kappa_nominal(pares_),
            "distribucion": [{"tipo_error": k, "nombre": TIPOS_ERROR[k], "veces": distribucion[k],
                              "porcentaje": _r(100 * distribucion[k] / len(finales), 1) if finales else None}
                             for k in TIPOS_ERROR if distribucion[k]],
            "finales": finales}


def clasificar(db: Session, ev, clave: str, tipo_error: str, ronda: str, nota: str | None, claves_validas: set,
               usuario_id: uuid.UUID):
    from app.models.evaluacion import ClasificacionError
    from app.servicios.auditoria import registrar

    if ev.estado != "cerrada":
        raise ErrorAnalisis("Los desacuerdos se clasifican con la evaluación cerrada, cuando ya no cambian.", 409)
    if clave not in claves_validas:
        raise ErrorAnalisis("Ese desacuerdo no existe en esta evaluación.", 404)
    if tipo_error not in TIPOS_ERROR:
        raise ErrorAnalisis("Tipo de error desconocido.")
    if ronda not in ("individual", "consenso"):
        raise ErrorAnalisis("Ronda desconocida.")
    filas = db.scalars(select(ClasificacionError).where(ClasificacionError.evaluacion_id == ev.id,
                                                        ClasificacionError.clave == clave)).all()
    if ronda == "consenso":
        individuales = {f.tipo_error for f in filas if f.ronda == "individual"}
        if len({f.clasificadora_id for f in filas if f.ronda == "individual"}) < 2 or len(individuales) < 2:
            raise ErrorAnalisis("El consenso solo se registra cuando dos clasificadoras difieren.", 409)
        mia = next((f for f in filas if f.ronda == "consenso"), None)
    else:
        mia = next((f for f in filas if f.ronda == "individual" and f.clasificadora_id == usuario_id), None)
    anterior = mia.tipo_error if mia else None
    if mia is None:
        mia = ClasificacionError(id=uuid.uuid4(), evaluacion_id=ev.id, clave=clave, ronda=ronda,
                                 clasificadora_id=usuario_id, tipo_error=tipo_error, nota=(nota or "").strip() or None)
        db.add(mia)
    else:
        mia.tipo_error, mia.nota, mia.clasificadora_id, mia.creada_en = tipo_error, (nota or "").strip() or None, \
            usuario_id, ahora()
    registrar(db, modulo="evaluacion", accion="desacuerdo_clasificado", usuario_id=usuario_id,
              entidad_tipo="evaluacion", entidad_id=ev.id, anterior={"tipo_error": anterior} if anterior else None,
              nuevo={"clave": clave, "ronda": ronda, "tipo_error": tipo_error})
    db.flush()
    return mia


# --- Estadística ---------------------------------------------------------------------------------------


def _f(c: dict) -> float | None:
    p = c["vp"] / (c["vp"] + c["fp"]) if c["vp"] + c["fp"] else None
    e = c["vp"] / (c["vp"] + c["fn"]) if c["vp"] + c["fn"] else None
    if p is None or e is None:
        return None
    return 2 * p * e / (p + e) if p + e else 0.0


def intervalo_f(por_documento: list[dict], remuestreos: int = REMUESTREOS, semilla: int = SEMILLA) -> dict:
    """Intervalo de confianza del 95 % de la F micro, remuestreando documentos."""
    docs = [d for d in por_documento if d["vp"] + d["fp"] + d["fn"]]
    if len(docs) < 2:
        return {"documentos": len(docs), "inferior": None, "superior": None, "remuestreos": 0}
    azar = random.Random(semilla)
    valores = []
    for _ in range(remuestreos):
        muestra = [docs[azar.randrange(len(docs))] for _ in docs]
        f = _f({k: sum(d[k] for d in muestra) for k in ("vp", "fp", "fn")})
        if f is not None:
            valores.append(f)
    valores.sort()
    if not valores:
        return {"documentos": len(docs), "inferior": None, "superior": None, "remuestreos": 0}
    return {"documentos": len(docs), "remuestreos": len(valores),
            "inferior": _r(valores[int(0.025 * (len(valores) - 1))]),
            "superior": _r(valores[int(math.ceil(0.975 * (len(valores) - 1)))])}


def wilcoxon(pares_: list[tuple[float, float]]) -> dict:
    """Prueba de rangos con signo de Wilcoxon, bilateral, aproximación normal
    con corrección por empates y de continuidad. Con menos de 6 pares
    distintos de cero no se informa p: la aproximación no es fiable."""
    diferencias = [a - b for a, b in pares_ if a - b != 0]
    n = len(diferencias)
    if n == 0:
        return {"n": 0, "w_mas": None, "w_menos": None, "z": None, "p": None, "nota": "Sin diferencias."}
    orden = sorted(range(n), key=lambda i: abs(diferencias[i]))
    rangos = [0.0] * n
    i = 0
    empates = []
    while i < n:
        j = i
        while j + 1 < n and abs(diferencias[orden[j + 1]]) == abs(diferencias[orden[i]]):
            j += 1
        promedio = (i + j) / 2 + 1
        for k in range(i, j + 1):
            rangos[orden[k]] = promedio
        if j > i:
            empates.append(j - i + 1)
        i = j + 1
    w_mas = sum(r for r, d in zip(rangos, diferencias) if d > 0)
    w_menos = sum(r for r, d in zip(rangos, diferencias) if d < 0)
    if n < 6:
        return {"n": n, "w_mas": w_mas, "w_menos": w_menos, "z": None, "p": None,
                "nota": "Menos de 6 pares con diferencia: no se calcula p."}
    media = n * (n + 1) / 4
    varianza = n * (n + 1) * (2 * n + 1) / 24 - sum(t ** 3 - t for t in empates) / 48
    w = min(w_mas, w_menos)
    z = (w - media + 0.5) / math.sqrt(varianza) if varianza > 0 else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"n": n, "w_mas": w_mas, "w_menos": w_menos, "z": _r(z), "p": _r(min(1.0, p)), "nota": None}
