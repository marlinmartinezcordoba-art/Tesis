"""
Decisiones de la archivista frente a cada propuesta del motor de IA: la
fuente de datos del capítulo de evaluación de la tesis.

Se leen del registro de auditoría (eventos «decision_ia» que deja la
publicación de una descripción); no hay una tabla paralela. Por cada
propuesta: aceptada tal cual, corregida o rechazada. Además, «agregada»:
lo que la archivista registró y el motor no había propuesto (omisiones).
"""

import io
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auditoria import RegistroAuditoria
from app.models.usuario import Usuario
from app.servicios.trazabilidad import _zona

DECISIONES = ("aceptada", "corregida", "rechazada", "agregada")
TIPO_NOMBRE = {"agente": "Agente", "lugar": "Lugar", "fecha": "Fecha", "forma_documental": "Forma documental",
               "actividad": "Actividad", "tipo_actividad": "Tipo de actividad", "mandato": "Mandato o norma",
               "titulo": "Título", "alcance": "Alcance y contenido", "idioma": "Idioma"}
DECISION_NOMBRE = {"aceptada": "Aceptada", "corregida": "Corregida", "rechazada": "Rechazada",
                   "agregada": "Agregada por la archivista"}


def _limites(desde: date | None, hasta: date | None):
    z = _zona()
    inicio = datetime.combine(desde, time.min, z) if desde else None
    fin = datetime.combine(hasta + timedelta(days=1), time.min, z) if hasta else None
    return inicio, fin


def eventos(db: Session, *, tipo: str | None = None, decision: str | None = None, desde: date | None = None,
            hasta: date | None = None, fondo_id: str | None = None) -> list[RegistroAuditoria]:
    q = select(RegistroAuditoria).where(RegistroAuditoria.accion == "decision_ia")
    if tipo:
        q = q.where(RegistroAuditoria.valor_nuevo["tipo"].astext == tipo)
    if decision:
        q = q.where(RegistroAuditoria.valor_nuevo["decision"].astext == decision)
    if fondo_id:
        q = q.where(RegistroAuditoria.valor_nuevo["fondo_id"].astext == str(fondo_id))
    inicio, fin = _limites(desde, hasta)
    if inicio:
        q = q.where(RegistroAuditoria.fecha >= inicio)
    if fin:
        q = q.where(RegistroAuditoria.fecha < fin)
    return list(db.scalars(q.order_by(RegistroAuditoria.fecha.desc(), RegistroAuditoria.id.desc())).all())


ROL_NOMBRE = {"productor": "productor", "remitente": "remitente", "destinatario": "destinatario",
              "mencionado": "mencionado"}
SUBTIPO_NOMBRE = {"persona": "persona", "entidad_corporativa": "entidad corporativa", "cargo": "cargo",
                  "familia": "familia", "mecanismo": "mecanismo", "ley": "ley", "decreto": "decreto",
                  "ordenanza": "ordenanza", "acuerdo": "acuerdo", "resolucion": "resolución", "otro": "otro instrumento"}


def _texto(valores: dict | None) -> str | None:
    """El valor tal como lo lee una archivista: «Gobernador · destinatario ·
    cargo», «hacia 1948 · c. 1948 (1948~)»."""
    from app.servicios import fechas

    if not valores:
        return None
    partes = [str(valores["valor"])] if valores.get("valor") else []
    if valores.get("rol"):
        partes.append(ROL_NOMBRE.get(valores["rol"], valores["rol"]))
    if valores.get("subtipo"):
        partes.append(SUBTIPO_NOMBRE.get(valores["subtipo"], valores["subtipo"]))
    if valores.get("edtf"):
        partes.append(f"{fechas.legible(valores['edtf'])} ({valores['edtf']})")
    enlaces = [k for k in ("tipo_clave", "agente_clave", "mandato_clave") if valores.get(k)]
    if enlaces:
        nombres = {"tipo_clave": "tipo", "agente_clave": "agente", "mandato_clave": "mandato"}
        partes.append("con " + ", ".join(nombres[k] for k in enlaces))
    return " · ".join(partes) or None


def _rico(n: dict) -> tuple[str | None, dict | None]:
    """Clase RiC-O de lo propuesto y propiedad que la decisión afecta, del
    mapeo único. Las decisiones anteriores a la versión 7 no guardaron el
    código de la relación: se reconstruye con la misma regla de la
    publicación (rol → relación), nunca se inventa."""
    from app.servicios import ric_o
    from app.servicios.descripcion import codigo_de_decision

    tipo = n.get("tipo")
    datos = n.get("final") or n.get("propuesto") or {}
    clase = ric_o.clase_de_decision(tipo, n.get("subtipo") or datos.get("subtipo"))
    if tipo in ("titulo", "alcance", "idioma"):
        return clase, ric_o.propiedad_de_campo(tipo)
    codigo = n.get("codigo_ric") or codigo_de_decision(tipo, datos | {"clave": n.get("clave")})
    return clase, ric_o.propiedad_de_codigo(codigo)


def fila(e: RegistroAuditoria, nombres: dict, etiquetas: dict | None = None) -> dict:
    n = e.valor_nuevo or {}
    clase, propiedad = _rico(n)
    return {"id": e.id, "fecha": e.fecha, "documento": {"id": e.entidad_id, "titulo": n.get("titulo_documento")},
            "tipo": n.get("tipo"), "tipo_nombre": TIPO_NOMBRE.get(n.get("tipo"), n.get("tipo")),
            "clase_rico": clase, "propiedad_rico": propiedad,
            "decision": n.get("decision"), "propuesto": _texto(n.get("propuesto")), "final": _texto(n.get("final")),
            "confianza": n.get("confianza"), "modelo": n.get("modelo"), "version_prompt": n.get("version_prompt"),
            "version_etiqueta": (etiquetas or {}).get(n.get("version_prompt")),
            "por": nombres.get(e.usuario_id)}


def _conteos(lista: list[dict]) -> dict:
    c = {d: sum(1 for f in lista if f["decision"] == d) for d in DECISIONES}
    propuestas = c["aceptada"] + c["corregida"] + c["rechazada"]
    def pct(x, base):
        return round(100 * x / base, 1) if base else None
    return c | {"propuestas": propuestas, "pct_aceptadas": pct(c["aceptada"], propuestas),
                "pct_corregidas": pct(c["corregida"], propuestas), "pct_rechazadas": pct(c["rechazada"], propuestas),
                # De todo lo que quedó publicado, cuánto propuso el motor (exhaustividad aparente).
                "pct_cobertura": pct(c["aceptada"] + c["corregida"], c["aceptada"] + c["corregida"] + c["agregada"])}


def consultar(db: Session, limite: int = 500, **filtros) -> dict:
    from app.servicios.hallazgos import etiquetas as etiquetas_version

    nombres = dict(db.execute(select(Usuario.id, Usuario.nombre)).all())
    etiquetas = etiquetas_version(db)
    filas = [fila(e, nombres, etiquetas) for e in eventos(db, **filtros)]
    por_tipo = {}
    for t in TIPO_NOMBRE:
        del_tipo = [f for f in filas if f["tipo"] == t]
        if del_tipo:
            por_tipo[t] = {"tipo_nombre": TIPO_NOMBRE[t], **_conteos(del_tipo)}
    return {"resumen": _conteos(filas), "por_tipo": list(por_tipo.values()),
            "modelos": sorted({f["modelo"] for f in filas if f["modelo"]}),
            "versiones_prompt": sorted({f["version_prompt"] for f in filas if f["version_prompt"]}),
            "etiquetas_version": etiquetas,
            "total": len(filas), "filas": filas[:limite]}


def hoja_de_calculo(db: Session, **filtros) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    datos = consultar(db, limite=10**9, **filtros)
    libro = Workbook()
    resumen = libro.active
    resumen.title = "Resumen"
    encabezado = ["Tipo", "Propuestas", "Aceptadas", "Corregidas", "Rechazadas", "Agregadas por la archivista",
                  "% aceptadas", "% corregidas", "% rechazadas", "% cobertura del motor"]
    resumen.append(encabezado)
    for t in datos["por_tipo"] + [{"tipo_nombre": "Total", **datos["resumen"]}]:
        resumen.append([t["tipo_nombre"], t["propuestas"], t["aceptada"], t["corregida"], t["rechazada"], t["agregada"],
                        t["pct_aceptadas"], t["pct_corregidas"], t["pct_rechazadas"], t["pct_cobertura"]])
    resumen.append([])
    resumen.append(["Modelos", ", ".join(datos["modelos"])])
    resumen.append(["Versiones de la instrucción", ", ".join(datos["versiones_prompt"])])
    detalle = libro.create_sheet("Decisiones")
    detalle.append(["Fecha", "Documento", "Tipo", "Clase RiC-O", "Propuesto por el motor", "Valor final", "Decisión",
                    "Propiedad RiC-O", "Confianza", "Modelo", "Versión de la instrucción", "Etiqueta", "Archivista"])
    for f in datos["filas"]:
        prop = f["propiedad_rico"] or {}
        detalle.append([f["fecha"].astimezone(_zona()).replace(tzinfo=None), f["documento"]["titulo"], f["tipo_nombre"],
                        f["clase_rico"], f["propuesto"], f["final"], DECISION_NOMBRE.get(f["decision"], f["decision"]),
                        prop.get("nombre") or ("literal pendiente de confirmación" if prop else None), f["confianza"],
                        f["modelo"], f["version_prompt"], f["version_etiqueta"], f["por"]])
    for hoja in (resumen, detalle):
        for celda in hoja[1]:
            celda.font = Font(bold=True)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()
