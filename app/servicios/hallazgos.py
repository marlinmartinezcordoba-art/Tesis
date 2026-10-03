"""
Hallazgos de conformidad con RiC (prompt de auditoría v7, §5bis) y
etiquetas legibles de las versiones de la instrucción del motor (§5).

Los hallazgos no se generan solos: los crea y los mantiene una persona con
rol de administrador. Del hallazgo creado solo cambian el estado, la fecha
de cierre y la acción; el título y la descripción originales no se tocan.
Todo cambio queda en la auditoría con el antes y el después.
"""

import io
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.auditoria import RegistroAuditoria
from app.models.hallazgo import COMPONENTES, ESTADO_HALLAZGO, EtiquetaVersionPrompt, HallazgoConformidad
from app.servicios.auditoria import registrar

ESTADO_NOMBRE = {"abierto": "Abierto", "en_correccion": "En corrección", "cerrado": "Cerrado"}
COMPONENTE_NOMBRE = {"autenticacion": "Autenticación", "ingesta": "Ingesta", "descripcion": "Descripción",
                     "vocabularios": "Vocabularios", "instrumentos": "Instrumentos", "preservacion": "Preservación",
                     "auditoria": "Auditoría"}


class ErrorHallazgo(ValueError):
    pass


def out(h: HallazgoConformidad) -> dict:
    return {"id": str(h.id), "numero": h.numero, "referencia": h.referencia, "titulo": h.titulo, "descripcion": h.descripcion,
            "componentes": list(h.componentes), "estado": h.estado, "estado_nombre": ESTADO_NOMBRE[h.estado],
            "abierto_en": h.abierto_en, "cerrado_en": h.cerrado_en, "accion": h.accion,
            "creado_en": h.creado_en, "actualizado_en": h.actualizado_en}


def listar(db: Session, *, estado: str | None = None, componente: str | None = None) -> dict:
    consulta = select(HallazgoConformidad).order_by(HallazgoConformidad.numero)
    if estado:
        consulta = consulta.where(HallazgoConformidad.estado == estado)
    if componente:
        consulta = consulta.where(HallazgoConformidad.componentes.any(componente))
    filas = db.scalars(consulta).all()
    todos = db.execute(select(HallazgoConformidad.estado, func.count()).group_by(HallazgoConformidad.estado)).all()
    return {"hallazgos": [out(h) for h in filas],
            "conteo": {e: 0 for e in ESTADO_HALLAZGO} | dict(todos),
            "conteo_filtrado": {e: sum(1 for h in filas if h.estado == e) for e in ESTADO_HALLAZGO}}


def _componentes(valores: list[str]) -> list[str]:
    limpios = list(dict.fromkeys(valores))
    if not limpios or any(c not in COMPONENTES for c in limpios):
        raise ErrorHallazgo("Indique al menos un componente, de los siete módulos del sistema.")
    return limpios


def crear(db: Session, *, titulo: str, descripcion: str, componentes: list[str], accion: str | None,
          usuario_id: uuid.UUID, ip: str | None = None) -> HallazgoConformidad:
    titulo, descripcion = " ".join(titulo.split()), descripcion.strip()
    if not titulo or not descripcion:
        raise ErrorHallazgo("Un hallazgo necesita un título y una descripción de la brecha.")
    numero = (db.scalar(select(func.max(HallazgoConformidad.numero))) or 0) + 1
    h = HallazgoConformidad(id=uuid.uuid4(), numero=numero, titulo=titulo[:300], descripcion=descripcion,
                            componentes=_componentes(componentes), estado="abierto", abierto_en=date.today(),
                            accion=(accion or "").strip() or None, creado_por_id=usuario_id)
    db.add(h)
    db.flush()
    registrar(db, modulo="auditoria", accion="hallazgo_creado", usuario_id=usuario_id, entidad_tipo="hallazgo",
              entidad_id=h.id, ip=ip, detalle=f"Hallazgo {numero}: {h.titulo}",
              nuevo={"numero": numero, "titulo": h.titulo, "estado": h.estado, "componentes": h.componentes})
    return h


def actualizar(db: Session, h: HallazgoConformidad, *, estado: str | None, accion: str | None,
               cerrado_en: date | None, usuario_id: uuid.UUID, ip: str | None = None) -> HallazgoConformidad:
    """Solo el estado, la fecha de cierre y la acción (nunca el título ni la
    descripción). Un hallazgo cerrado tiene fecha de cierre; si se reabre,
    la pierde (la historia queda en la auditoría)."""
    antes = {"estado": h.estado, "cerrado_en": h.cerrado_en.isoformat() if h.cerrado_en else None, "accion": h.accion}
    if estado is not None:
        if estado not in ESTADO_HALLAZGO:
            raise ErrorHallazgo("Estado desconocido.")
        h.estado = estado
    if h.estado == "cerrado":
        h.cerrado_en = cerrado_en or h.cerrado_en or date.today()
        if h.cerrado_en < h.abierto_en:
            raise ErrorHallazgo("La fecha de cierre no puede ser anterior a la de apertura.")
    else:
        if cerrado_en is not None:
            raise ErrorHallazgo("Solo un hallazgo cerrado tiene fecha de cierre.")
        h.cerrado_en = None
    if accion is not None:
        h.accion = accion.strip() or None
    despues = {"estado": h.estado, "cerrado_en": h.cerrado_en.isoformat() if h.cerrado_en else None, "accion": h.accion}
    cambios = {k for k in antes if antes[k] != despues[k]}
    if cambios:
        h.actualizado_en = ahora()
        registrar(db, modulo="auditoria", accion="hallazgo_actualizado", usuario_id=usuario_id,
                  entidad_tipo="hallazgo", entidad_id=h.id, ip=ip, detalle=f"Hallazgo {h.numero}: {h.titulo}",
                  anterior={k: antes[k] for k in sorted(cambios)}, nuevo={k: despues[k] for k in sorted(cambios)})
    db.flush()
    return h


def hoja_de_calculo(db: Session, **filtros) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    datos = listar(db, **filtros)
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Hallazgos"
    hoja.append(["N.º", "Título", "Estado", "Componentes", "Abierto", "Cerrado", "Descripción de la brecha",
                 "Acción tomada o pendiente"])
    for h in datos["hallazgos"]:
        hoja.append([h["numero"], h["titulo"], h["estado_nombre"],
                     ", ".join(COMPONENTE_NOMBRE[c] for c in h["componentes"]), h["abierto_en"], h["cerrado_en"],
                     h["descripcion"], h["accion"]])
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for fila in hoja.iter_rows(min_row=2):
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical="top")
    for letra, ancho in zip("ABCDEFGH", (6, 45, 14, 26, 12, 12, 60, 80)):
        hoja.column_dimensions[letra].width = ancho
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


# --- Etiquetas de versión de la instrucción ------------------------------------------------------


def etiquetas(db: Session) -> dict[str, str]:
    return dict(db.execute(select(EtiquetaVersionPrompt.version, EtiquetaVersionPrompt.etiqueta)).all())


def versiones(db: Session) -> list[dict]:
    """Las versiones que aparecen en las decisiones registradas (y la
    vigente), con su etiqueta si la tiene."""
    from app.servicios.motor import VERSION_PROMPT

    version = RegistroAuditoria.valor_nuevo["version_prompt"].astext
    filas = db.execute(select(version, func.count(), func.min(RegistroAuditoria.fecha), func.max(RegistroAuditoria.fecha))
                       .where(RegistroAuditoria.accion == "decision_ia", version.is_not(None))
                       .group_by(version)).all()
    nombres = etiquetas(db)
    salida = {v: {"version": v, "decisiones": n, "primera": a, "ultima": b, "etiqueta": nombres.get(v),
                  "vigente": v == VERSION_PROMPT} for v, n, a, b in filas}
    salida.setdefault(VERSION_PROMPT, {"version": VERSION_PROMPT, "decisiones": 0, "primera": None, "ultima": None,
                                       "etiqueta": nombres.get(VERSION_PROMPT), "vigente": True})
    return sorted(salida.values(), key=lambda x: (x["primera"] is None, x["primera"] or ahora()))


def etiquetar(db: Session, version: str, etiqueta: str | None, nota: str | None, usuario_id: uuid.UUID,
              ip: str | None = None) -> None:
    """Pone o cambia el nombre legible de una versión ya calculada (no se
    quita: nada se borra; el nombre anterior queda en la auditoría)."""
    if version not in {v["version"] for v in versiones(db)}:
        raise ErrorHallazgo("Esa versión de la instrucción no aparece en ninguna decisión ni es la vigente.")
    actual = db.get(EtiquetaVersionPrompt, version)
    antes = actual.etiqueta if actual else None
    etiqueta = " ".join((etiqueta or "").split())[:40] or None
    if etiqueta and db.scalar(select(EtiquetaVersionPrompt).where(EtiquetaVersionPrompt.etiqueta == etiqueta,
                                                                  EtiquetaVersionPrompt.version != version)):
        raise ErrorHallazgo(f"La etiqueta «{etiqueta}» ya nombra otra versión.")
    if etiqueta is None:
        raise ErrorHallazgo("Escriba la etiqueta, por ejemplo «v3».")
    if actual is None:
        db.add(EtiquetaVersionPrompt(version=version, etiqueta=etiqueta, nota=(nota or "").strip() or None,
                                     asignada_por_id=usuario_id))
    else:
        actual.etiqueta, actual.nota, actual.asignada_por_id, actual.asignada_en = etiqueta, (nota or "").strip() or None, usuario_id, ahora()
    if antes != etiqueta:
        registrar(db, modulo="auditoria", accion="version_prompt_etiquetada", usuario_id=usuario_id,
                  entidad_tipo="version_prompt", entidad_id=version, ip=ip, detalle=f"Versión {version}",
                  anterior={"etiqueta": antes}, nuevo={"etiqueta": etiqueta})
    db.flush()
