"""
Evaluación frente a una referencia adjudicada, calibración de la certeza y
hojas para la verificación independiente.

- Referencia adjudicada (R): la que consolida la adjudicadora a partir de dos
  o más descripciones ciegas del mismo documento. Frente a ella se miden las
  propuestas originales del motor (A0) y las descripciones hechas con la
  propuesta delante (A1). El techo humano es el acuerdo entre las
  descripciones ciegas antes de la adjudicación.
- Comparabilidad con incertidumbre: por tipo de entidad, el intervalo de
  confianza del 95 % de la diferencia entre la F de A0 o A1 y el techo
  humano, remuestreando documentos. Un tipo es comparable si el límite
  inferior de ese intervalo no baja de menos el margen del criterio y hay
  los casos mínimos. Se informa como no inferioridad, nunca como
  superioridad.
- Calibración: por tramo de certeza del motor, qué proporción de sus
  entidades coincide con la referencia.
- Hoja de coincidencias: una fila por aserción, con su resultado estricto y
  flexible, para repetir el cálculo fuera del sistema.
- Hoja ciega: descripciones con un código al azar, sin origen ni certeza,
  para calificarlas sin saber quién las hizo; la llave va en un archivo
  aparte.
"""

import io
import random
import secrets
import zipfile
from itertools import combinations

from app.servicios.evaluacion import (TIPOS, _r, _sumar, conteo, entidades_de_anotacion, entidades_de_propuesta, pares,
                                      prf, texto_de)

REMUESTREOS = 1000
SEMILLA = 20261113
TRAMOS = [(i / 10, (i + 1) / 10) for i in range(10)]


def _f(c: dict) -> float | None:
    return prf(c)["f1"] if c["vp"] + c["fp"] + c["fn"] else None


def _diferencia_ic(por_doc: list[tuple[dict, dict]], remuestreos: int = REMUESTREOS) -> dict:
    """IC 95 % de F(sistema) − F(techo), remuestreando documentos. por_doc: [(cuentas sistema, cuentas techo)]."""
    docs = [x for x in por_doc if sum(x[0].values()) and sum(x[1].values())]
    if len(docs) < 2:
        return {"documentos": len(docs), "inferior": None, "superior": None}
    azar = random.Random(SEMILLA)
    valores = []
    for _ in range(remuestreos):
        muestra = [docs[azar.randrange(len(docs))] for _ in docs]
        a = {k: sum(m[0][k] for m in muestra) for k in ("vp", "fp", "fn")}
        b = {k: sum(m[1][k] for m in muestra) for k in ("vp", "fp", "fn")}
        fa, fb = _f(a), _f(b)
        if fa is not None and fb is not None:
            valores.append(fa - fb)
    if not valores:
        return {"documentos": len(docs), "inferior": None, "superior": None}
    valores.sort()
    n = len(valores) - 1
    return {"documentos": len(docs), "inferior": _r(valores[int(0.025 * n)]), "superior": _r(valores[-1 - int(0.025 * n)])}


def frente_a_referencia(documentos, por_doc, adjudicadas, ev) -> dict:
    """A0 y A1 frente a la referencia adjudicada, por tipo, con el techo humano y el veredicto."""
    from app.servicios.evaluacion_analisis import criterio_de

    criterio = criterio_de(ev.criterio)
    umbral = ev.umbral_similitud
    cuentas = {f: {m: {t: {"vp": 0, "fp": 0, "fn": 0} for t in TIPOS} for m in ("estricto", "flexible")}
               for f in ("A0", "A1")}
    techo = {t: {"vp": 0, "fp": 0, "fn": 0} for t in TIPOS}
    doc_tipo = {f: {t: [] for t in TIPOS} for f in ("A0", "A1")}
    documentos_con_r = 0
    for d in documentos:
        adj = adjudicadas.get(d.instanciacion_id)
        if adj is None:
            continue
        documentos_con_r += 1
        ref = entidades_de_anotacion(adj.datos)
        a0 = entidades_de_propuesta(d.propuesta)
        anotadas = por_doc.get(d.instanciacion_id, [])
        a1s = [entidades_de_anotacion(a.datos) for a in anotadas if a.condicion == "asistida"]
        ciegas = [entidades_de_anotacion(a.datos) for a in anotadas if a.condicion == "ciega"]
        techo_doc = {t: {"vp": 0, "fp": 0, "fn": 0} for t in TIPOS}
        for x, y in combinations(ciegas, 2):
            for t in TIPOS:
                techo_doc[t] = _sumar(techo_doc[t], conteo([e for e in x if e["tipo"] == t],
                                                           [e for e in y if e["tipo"] == t], umbral))
        for t in TIPOS:
            techo[t] = _sumar(techo[t], techo_doc[t])
            r_t = [e for e in ref if e["tipo"] == t]
            for fuente, sistemas in (("A0", [a0]), ("A1", a1s)):
                c_doc = {"vp": 0, "fp": 0, "fn": 0}
                for sis in sistemas:
                    s_t = [e for e in sis if e["tipo"] == t]
                    cuentas[fuente]["estricto"][t] = _sumar(cuentas[fuente]["estricto"][t], conteo(s_t, r_t, 1.0))
                    c = conteo(s_t, r_t, umbral)
                    cuentas[fuente]["flexible"][t] = _sumar(cuentas[fuente]["flexible"][t], c)
                    c_doc = _sumar(c_doc, c)
                if sistemas:
                    doc_tipo[fuente][t].append((c_doc, techo_doc[t]))
    if not documentos_con_r:
        return {"documentos": 0, "tipos": [], "nota": "Aún no hay documentos con referencia adjudicada."}
    tipos = []
    for t in TIPOS:
        casos = cuentas["A0"]["flexible"][t]["vp"] + cuentas["A0"]["flexible"][t]["fn"]
        if not casos and not sum(cuentas["A1"]["flexible"][t].values()):
            continue
        fila = {"tipo": t, "casos_referencia": casos, "techo": _f(techo[t]) if sum(techo[t].values()) else None}
        for fuente in ("A0", "A1"):
            est, flex = prf(cuentas[fuente]["estricto"][t]), prf(cuentas[fuente]["flexible"][t])
            ic = _diferencia_ic(doc_tipo[fuente][t])
            if casos < criterio["minimo_casos"]:
                estado = "datos_insuficientes"
            elif fila["techo"] is None or ic["inferior"] is None:
                estado = "sin_techo"
            else:
                estado = "no_inferior" if ic["inferior"] >= -criterio["margen_f"] else "inferior"
            fila[fuente] = {"estricto": est, "flexible": flex, "diferencia_ic95": ic, "estado": estado}
        tipos.append(fila)
    return {"documentos": documentos_con_r, "margen_f": criterio["margen_f"], "minimo_casos": criterio["minimo_casos"],
            "tipos": tipos,
            "nota": "No inferior significa que el límite inferior del IC 95 % de la diferencia de F frente al acuerdo "
                    "entre archivistas no baja de menos el margen. No se informa superioridad."}


def calibracion(documentos, por_doc, adjudicadas, umbral: float) -> dict:
    """Por tramo de certeza del motor, la proporción de sus entidades que coincide con la referencia
    (la adjudicada si existe; si no, cada descripción ciega)."""
    tramos = [{"desde": a, "hasta": b, "propuestas": 0, "correctas": 0} for a, b in TRAMOS]
    for d in documentos:
        crudas = [e for e in (d.propuesta or {}).get("entidades", []) if e.get("tipo") in TIPOS and (e.get("valor") or "").strip()]
        if not crudas:
            continue
        adj = adjudicadas.get(d.instanciacion_id)
        refs = [entidades_de_anotacion(adj.datos)] if adj else [
            entidades_de_anotacion(a.datos) for a in por_doc.get(d.instanciacion_id, []) if a.condicion == "ciega"]
        for ref in refs:
            acertadas = {i for i, _ in pares(crudas, ref, umbral)}
            for i, e in enumerate(crudas):
                c = e.get("confianza")
                if not isinstance(c, (int, float)):
                    continue
                k = min(int(max(0.0, min(1.0, float(c))) * 10), 9)
                tramos[k]["propuestas"] += 1
                tramos[k]["correctas"] += int(i in acertadas)
    for t in tramos:
        t["proporcion"] = _r(t["correctas"] / t["propuestas"]) if t["propuestas"] else None
    usados = [t for t in tramos if t["propuestas"]]
    total = sum(t["propuestas"] for t in usados)
    ece = _r(sum(t["propuestas"] / total * abs(t["proporcion"] - (t["desde"] + t["hasta"]) / 2) for t in usados)) if total else None
    return {"tramos": tramos, "propuestas": total, "error_esperado_de_calibracion": ece}


# --- Hojas para verificación independiente ---------------------------------------------------------


def _filas_comparacion(doc: str, etiqueta: str, sistema: list[dict], referencia: list[dict], umbral: float) -> list[list]:
    filas = []
    for t in TIPOS:
        s_t = [e for e in sistema if e["tipo"] == t]
        r_t = [e for e in referencia if e["tipo"] == t]
        estricto = dict(pares(s_t, r_t, 1.0))
        flexible = dict(pares(s_t, r_t, umbral))
        usadas_e, usadas_f = set(estricto.values()), set(flexible.values())
        for i, e in enumerate(s_t):
            j = flexible.get(i, estricto.get(i))
            filas.append([doc, etiqueta, t, texto_de(e) or e.get("valor"), texto_de(r_t[j]) if j is not None else None,
                          "VP" if i in estricto else "FP", "VP" if i in flexible else "FP"])
        for j, e in enumerate(r_t):
            if j not in usadas_e or j not in usadas_f:
                filas.append([doc, etiqueta, t, None, texto_de(e) or e.get("valor"),
                              "FN" if j not in usadas_e else None, "FN" if j not in usadas_f else None])
    return [f for f in filas if f[5] or f[6]]


def coincidencias(db, ev) -> list[list]:
    """Una fila por aserción evaluada o por aserción de la referencia no recuperada."""
    from sqlalchemy import select

    from app.models.evaluacion import Anotacion, EvaluacionDocumento
    from app.models.instanciacion import Instanciacion

    documentos = [d for d in db.scalars(select(EvaluacionDocumento).where(EvaluacionDocumento.evaluacion_id == ev.id))
                  if not d.piloto]
    filas = []
    for d in documentos:
        nombre = db.get(Instanciacion, d.instanciacion_id).nombre_original
        anot = db.scalars(select(Anotacion).where(Anotacion.evaluacion_id == ev.id, Anotacion.instanciacion_id ==
                                                  d.instanciacion_id, Anotacion.estado == "enviada")).all()
        adj = next((a for a in anot if a.condicion == "adjudicada"), None)
        ciegas = sorted((a for a in anot if a.condicion == "ciega"), key=lambda a: a.enviada_en)
        if adj is not None:
            ref = entidades_de_anotacion(adj.datos)
            filas += _filas_comparacion(nombre, "A0 frente a R", entidades_de_propuesta(d.propuesta), ref, ev.umbral_similitud)
            for a in anot:
                if a.condicion == "asistida":
                    filas += _filas_comparacion(nombre, "A1 frente a R", entidades_de_anotacion(a.datos), ref,
                                                ev.umbral_similitud)
        if len(ciegas) >= 2:
            filas += _filas_comparacion(nombre, "B2 frente a B1", entidades_de_anotacion(ciegas[1].datos),
                                        entidades_de_anotacion(ciegas[0].datos), ev.umbral_similitud)
    return filas


def hoja_coincidencias(db, ev, datos: dict) -> bytes:
    """Libro con las coincidencias, los tiempos y la versión con que se midió, para recalcular fuera del sistema."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    libro = Workbook()
    h = libro.active
    h.title = "Coincidencias"
    h.append(["Código documento", "Comparación", "Tipo de aserción", "Aserción evaluada", "Aserción de referencia",
              "Resultado estricto", "Resultado flexible"])
    for f in coincidencias(db, ev):
        h.append(f)
    t = libro.create_sheet("Tiempos")
    t.append(["Código documento", "Código persona", "Condición", "Minutos"])
    for x in datos.get("tiempos_por_documento", []):
        if x.get("ciega") is not None:
            t.append([x["documento"], x["evaluadora"], "Manual", x["ciega"]])
        if x.get("asistida") is not None:
            t.append([x["documento"], x["evaluadora"], "Asistida", x["asistida"]])
    v = libro.create_sheet("Versión")
    for k, val in (ev.version_congelada or {}).items():
        v.append([k, val])
    v.append(["umbral_similitud", ev.umbral_similitud])
    for k, val in (ev.criterio or {}).items():
        v.append([f"criterio.{k}", val])
    for hoja in libro.worksheets:
        for celda in hoja[1]:
            celda.font = Font(bold=True)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def instrumento_1(db, ev, datos: dict) -> list[list]:
    """El Instrumento 1 de la tesis (matriz de evaluación ciega), fila por fila: el motor frente a
    cada descripción ciega, con el resultado flexible, la clase de desacuerdo y el tipo de error que
    clasificaron las investigadoras. Mismo emparejamiento que las métricas y los desacuerdos."""
    from sqlalchemy import select

    from app.models.evaluacion import Anotacion, EvaluacionDocumento
    from app.models.instanciacion import Instanciacion
    from app.servicios import evaluacion_analisis as an
    from app.servicios import evaluacion_participantes as participantes

    codigos = participantes.codigos(db, ev)
    clasificados = {(x["documento_id"], x["referencia_id"], x["tipo"], x["motor"], x["archivista"]): x
                    for x in (datos.get("errores") or {}).get("lista", []) if not x.get("propiedad")}
    filas = []
    for d in db.scalars(select(EvaluacionDocumento).where(EvaluacionDocumento.evaluacion_id == ev.id)):
        if d.piloto or d.propuesta is None:
            continue
        nombre = db.get(Instanciacion, d.instanciacion_id).nombre_original
        motor = entidades_de_propuesta(d.propuesta)
        ciegas = db.scalars(select(Anotacion).where(Anotacion.evaluacion_id == ev.id, Anotacion.instanciacion_id ==
                                                    d.instanciacion_id, Anotacion.condicion == "ciega",
                                                    Anotacion.estado == "enviada").order_by(Anotacion.enviada_en))
        for a in ciegas:
            experta = codigos[a.evaluador_id].codigo if a.evaluador_id in codigos else "?"
            ref = entidades_de_anotacion(a.datos)
            emparejados = an.pares(motor, ref, ev.umbral_similitud)
            usados_m, usados_r = {i for i, _, _ in emparejados}, {j for _, j, _ in emparejados}

            def fila(e_m, e_r, resultado):
                tm = an._texto_entidad(e_m) if e_m else None
                tr = an._texto_entidad(e_r) if e_r else None
                tipo = (e_m or e_r)["tipo"]
                x = clasificados.get((str(d.instanciacion_id), str(a.id), tipo, tm, tr)) or {}
                error = an.TIPOS_ERROR.get(x["tipo_error"]) if x.get("tipo_error") else None
                filas.append([nombre, experta, tipo, tm, tr, resultado, x.get("clase_nombre"), error])

            for i, j, _ in emparejados:
                fila(motor[i], ref[j], "VP")
            for i, e in enumerate(motor):
                if i not in usados_m:
                    fila(e, None, "FP")
            for j, e in enumerate(ref):
                if j not in usados_r:
                    fila(None, e, "FN")
    return filas


def _texto(datos: dict) -> str:
    partes = []
    if datos.get("titulo"):
        partes.append(f"Título. {datos['titulo']}")
    if datos.get("alcance"):
        partes.append(f"Alcance y contenido. {datos['alcance']}")
    for e in datos.get("entidades", []):
        valor = e.get("edtf") or e.get("valor")
        if valor:
            partes.append(f"{e.get('tipo')}. {valor}")
    return "\n".join(partes)


def hoja_ciega(db, ev) -> bytes:
    """ZIP con dos libros: la hoja para calificar (código al azar, sin origen ni certeza, en orden barajado) y la
    llave que relaciona cada código con su origen. La llave no se entrega a quien califica."""
    from openpyxl import Workbook
    from sqlalchemy import select

    from app.models.evaluacion import Anotacion, EvaluacionDocumento
    from app.models.instanciacion import Instanciacion
    from app.servicios import evaluacion_participantes as participantes
    from app.servicios import evaluacion_ric

    codigos = participantes.codigos(db, ev)
    items = []
    for d in db.scalars(select(EvaluacionDocumento).where(EvaluacionDocumento.evaluacion_id == ev.id)):
        if d.piloto or d.propuesta is None:
            continue
        nombre = db.get(Instanciacion, d.instanciacion_id).nombre_original
        items.append(("A0", nombre, "motor", _texto(evaluacion_ric.desde_roles(d.propuesta))))
        for a in db.scalars(select(Anotacion).where(Anotacion.evaluacion_id == ev.id, Anotacion.instanciacion_id ==
                                                    d.instanciacion_id, Anotacion.estado == "enviada")):
            if a.condicion == "adjudicada":
                continue
            conjunto = "A1" if a.condicion == "asistida" else "B"
            quien = codigos[a.evaluador_id].codigo if a.evaluador_id in codigos else "?"
            items.append((conjunto, nombre, quien, _texto(a.datos or {})))
    random.SystemRandom().shuffle(items)
    hoja, llave = Workbook(), Workbook()
    h, k = hoja.active, llave.active
    h.title, k.title = "Calificación ciega", "Llave"
    h.append(["Código", "Descripción", "Exactitud (1 a 5)", "Completitud (1 a 5)", "Pertinencia (1 a 5)", "Observaciones"])
    k.append(["Código", "Conjunto", "Documento", "Autoría"])
    usados = set()
    for conjunto, nombre, quien, texto in items:
        codigo = secrets.token_hex(3).upper()
        while codigo in usados:
            codigo = secrets.token_hex(3).upper()
        usados.add(codigo)
        h.append([codigo, texto, None, None, None, None])
        k.append([codigo, conjunto, nombre, quien])
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, libro in (("calificacion-ciega.xlsx", hoja), ("llave-de-codigos.xlsx", llave)):
            b = io.BytesIO()
            libro.save(b)
            z.writestr(nombre, b.getvalue())
    return salida.getvalue()

