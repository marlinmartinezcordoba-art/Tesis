"""
Disposición final ejecutada, como hecho de RiC.

La TRD dice qué se hace con cada serie al cumplir su retención (regla); aquí se
registra que se hizo. Cada disposición ejecutada es una rico:Activity del
vocabulario del fondo:

- de un tipo de actividad (rico:ActivityType): eliminación documental, selección,
  conservación total o reproducción por medio técnico;
- ejercida por un agente (el comité o la dependencia que la ejecuta, R060i);
- con su fecha (la del acta, R068);
- regulada por las reglas de retención que la mandaron (R063);
- documentada por el acta, si el acta está descrita en el fondo (R033);
- que afectó a cada expediente (R059, rol «disposicion»).

Nada se borra: el expediente eliminado sigue descrito y su estado de disposición
se lee de la actividad que lo afectó. Solo se dispone lo que la TRD manda (la
disposición de su regla vigente en su fecha) y cuando la retención se cumplió:
fecha final del expediente + años en archivo de gestión + años en central.
"""

import calendar
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import cuadro, fechas, retencion
from app.servicios.auditoria import registrar

TIPO = {"eliminacion": "Eliminación documental", "seleccion": "Selección documental",
        "conservacion_total": "Conservación total", "medio_tecnico": "Reproducción por medio técnico"}
DISPONIBLES = ("expediente", "unidad_documental")


class ErrorDisposicion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def _sumar_anios(d: date, anios: int) -> date:
    anio = d.year + anios
    return d.replace(year=anio, day=min(d.day, calendar.monthrange(anio, d.month)[1]))


def _fin(r: RecursoDocumental) -> date | None:
    if not r.fechas_extremas_edtf:
        return None
    try:
        i = fechas.interpretar(r.fechas_extremas_edtf)
    except fechas.FechaInvalida:
        return None
    return i.fin or i.inicio


def estado_de(db: Session, recurso_id: uuid.UUID) -> dict | None:
    """La disposición ejecutada sobre la descripción (la actividad que la afectó), si la hubo."""
    rel = db.scalar(select(Relacion).where(Relacion.destino_id == recurso_id, Relacion.codigo_ric == "affects_or_affected",
                                           Relacion.rol == "disposicion", Relacion.estado == "vigente"))
    if rel is None:
        return None
    a = db.get(EntidadVocabulario, rel.origen_id)
    return {"actividad": {"id": str(a.id), "nombre": a.nombre}, "tipo": a.subtipo,
            "tipo_nombre": TIPO.get(a.subtipo or ""), "fecha": a.existencia_edtf}


def calendario(db: Session, fondo: RecursoDocumental, al: date | None = None) -> list[dict]:
    """Expedientes y documentos de serie con su regla, cuándo se cumple su retención y qué
    manda la TRD; los ya dispuestos dicen cómo y cuándo."""
    al = al or date.today()
    filas = []
    todos = db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo.id,
                                                       RecursoDocumental.nivel.in_(DISPONIBLES))).all()
    por_id = {r.id: r for r in db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo.id))}
    for r in todos:
        superior = por_id.get(r.incluido_en_id)
        if r.nivel == "unidad_documental" and (superior is None or superior.nivel == "expediente"):
            continue  # un documento de expediente se dispone con su expediente
        regla = retencion.retencion_de(db, r)
        fin = _fin(r)
        anios = None if regla is None else (regla["gestion_anios"] or 0) + (regla["central_anios"] or 0)
        vence = _sumar_anios(fin, anios) if fin and anios is not None else None
        hecha = estado_de(db, r.id)
        filas.append({
            "id": str(r.id), "nivel": r.nivel, "titulo": r.titulo, "codigo": r.codigo_referencia,
            "serie": superior.titulo if superior else None, "fechas": r.fechas_extremas,
            "regla": regla["resumen"] if regla else None, "disposicion": regla["disposicion_final"] if regla else None,
            "disposicion_nombre": regla["disposicion_nombre"] if regla else None,
            "vence": vence.isoformat() if vence else None, "cumplida": bool(vence and vence <= al) and not hecha,
            "motivo": None if regla is None or regla["disposicion_final"] else "La regla no dice disposición final.",
            "ejecutada": hecha})
    return sorted(filas, key=lambda x: (x["ejecutada"] is not None, x["vence"] or "9999", x["titulo"]))


def ejecutar(db: Session, fondo: RecursoDocumental, *, recursos: list[uuid.UUID], disposicion: str, acta_numero: str,
             acta_fecha: date, ejecutor: str, usuario_id: uuid.UUID, acta_recurso_id: uuid.UUID | None = None,
             observaciones: str | None = None) -> EntidadVocabulario:
    from app.servicios import descripcion

    if disposicion not in TIPO:
        raise ErrorDisposicion("La disposición es eliminación, selección, conservación total o medio técnico.")
    acta_numero, ejecutor = " ".join((acta_numero or "").split()), " ".join((ejecutor or "").split())
    if not acta_numero or not ejecutor:
        raise ErrorDisposicion("Indique el número del acta y quién ejecuta la disposición (comité o dependencia).")
    if not recursos:
        raise ErrorDisposicion("Elija al menos un expediente.")
    if acta_fecha > date.today():
        raise ErrorDisposicion("La fecha del acta no puede ser futura.")
    elegidos, reglas = [], set()
    for rid in dict.fromkeys(recursos):
        r = db.get(RecursoDocumental, rid)
        if r is None or r.fondo_id != fondo.id or r.nivel not in DISPONIBLES:
            raise ErrorDisposicion("Algún elemento no es un expediente o documento de este fondo.")
        if estado_de(db, r.id):
            raise ErrorDisposicion(f"«{r.titulo}» ya tiene su disposición ejecutada.", 409)
        regla = retencion.retencion_de(db, r)
        if regla is None or regla["disposicion_final"] != disposicion:
            dice = regla["disposicion_nombre"].lower() if regla and regla["disposicion_nombre"] else "ninguna disposición"
            raise ErrorDisposicion(f"La TRD dice {dice} para «{r.titulo}», no {TIPO[disposicion].lower()}.")
        fin = _fin(r)
        if fin is None:
            raise ErrorDisposicion(f"«{r.titulo}» no tiene fecha final: no se sabe si cumplió su retención.")
        vence = _sumar_anios(fin, (regla["gestion_anios"] or 0) + (regla["central_anios"] or 0))
        if vence > acta_fecha:
            raise ErrorDisposicion(f"«{r.titulo}» cumple su retención el {vence.isoformat()}: todavía no se dispone.")
        elegidos.append(r)
        reglas.add(uuid.UUID(regla["regla"]["id"]))
    # La actividad, su tipo y quien la ejerce, en el vocabulario del fondo.
    nombre = f"{TIPO[disposicion]} · Acta {acta_numero} del {acta_fecha.isoformat()}"
    actividad, _ = cuadro._de_vocabulario(db, fondo.id, "actividad", nombre, usuario_id)
    actividad.subtipo = disposicion  # el tipo de disposición, para leer el estado sin recorrer el grafo
    actividad.existencia_edtf = acta_fecha.isoformat()
    actividad.historia = (observaciones or "").strip()[:5000] or None
    tipo, _ = cuadro._de_vocabulario(db, fondo.id, "tipo_actividad", TIPO[disposicion], usuario_id)
    agente, _ = cuadro._de_vocabulario(db, fondo.id, "agente", ejecutor, usuario_id, "entidad_corporativa")
    db.flush()
    yo, procedencia = ("entidad_vocabulario", actividad.id), ("persona", None, None)
    descripcion._relacionar(db, yo, ("entidad_vocabulario", tipo.id), "has_activity_type", "asociacion", usuario_id,
                            procedencia)
    descripcion._relacionar(db, ("entidad_vocabulario", agente.id), yo, "performs_or_performed", "asociacion",
                            usuario_id, procedencia)
    i = fechas.interpretar(acta_fecha.isoformat())
    f = descripcion._crear_fecha(db, acta_fecha.isoformat(), i, "persona", None, None)
    db.flush()
    descripcion._relacionar(db, ("fecha", f.id), yo, "is_date_associated_with", "temporal", usuario_id, procedencia)
    for regla_id in reglas:
        descripcion._relacionar(db, ("entidad_vocabulario", regla_id), yo, "regulates_or_regulated", "asociacion",
                                usuario_id, procedencia)
    if acta_recurso_id:
        acta = db.get(RecursoDocumental, acta_recurso_id)
        if acta is None or acta.fondo_id != fondo.id:
            raise ErrorDisposicion("El acta elegida no es una descripción de este fondo.")
        descripcion._relacionar(db, ("recurso_documental", acta.id), yo, "documents", "asociacion", usuario_id,
                                procedencia)
    for r in elegidos:
        descripcion._relacionar(db, yo, ("recurso_documental", r.id), "affects_or_affected", "asociacion", usuario_id,
                                procedencia, rol="disposicion")
    db.flush()
    registrar(db, modulo="instrumentos", accion="disposicion_ejecutada", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=actividad.id,
              detalle=f"{nombre}: {len(elegidos)} elemento(s), ejecutada por {ejecutor}",
              nuevo={"disposicion": disposicion, "acta": acta_numero, "fecha": acta_fecha.isoformat(),
                     "recursos": [str(r.id) for r in elegidos]})
    return actividad


def historial(db: Session, fondo: RecursoDocumental) -> list[dict]:
    actividades = db.scalars(select(EntidadVocabulario).where(
        EntidadVocabulario.fondo_id == fondo.id, EntidadVocabulario.clase == "actividad",
        EntidadVocabulario.subtipo.in_(tuple(TIPO)), EntidadVocabulario.estado == "activa")
        .order_by(EntidadVocabulario.existencia_edtf.desc())).all()
    salida = []
    for a in actividades:
        afectados = db.scalars(select(Relacion.destino_id).where(
            Relacion.origen_id == a.id, Relacion.codigo_ric == "affects_or_affected", Relacion.rol == "disposicion",
            Relacion.estado == "vigente")).all()
        ejecutor = db.scalar(select(EntidadVocabulario.nombre).join(Relacion, Relacion.origen_id == EntidadVocabulario.id)
                             .where(Relacion.destino_id == a.id, Relacion.codigo_ric == "performs_or_performed"))
        salida.append({"id": str(a.id), "nombre": a.nombre, "tipo": a.subtipo, "tipo_nombre": TIPO[a.subtipo],
                       "fecha": a.existencia_edtf, "ejecutor": ejecutor, "elementos": len(afectados),
                       "observaciones": a.historia})
    return salida


def transferencia(db: Session, lote, archivos: list, usuario_id: uuid.UUID) -> EntidadVocabulario | None:
    """El ingreso de un lote confirmado (transferencia, donación, compra…) como
    rico:Activity: ejercida por la dependencia de origen o el remitente, con la fecha
    del acta, que afectó a cada archivo recibido."""
    from app.models.lote import NOMBRE_FORMA_INGRESO
    from app.servicios import descripcion

    tipo_nombre = NOMBRE_FORMA_INGRESO[lote.forma_ingreso]
    nombre = f"{tipo_nombre} · lote {lote.numero}" + (f" · acta {lote.acta_numero}" if lote.acta_numero else "")
    actividad, _ = cuadro._de_vocabulario(db, lote.fondo_id, "actividad", nombre, usuario_id)
    tipo, _ = cuadro._de_vocabulario(db, lote.fondo_id, "tipo_actividad", tipo_nombre, usuario_id)
    db.flush()
    yo, procedencia = ("entidad_vocabulario", actividad.id), ("persona", None, None)
    descripcion._relacionar(db, yo, ("entidad_vocabulario", tipo.id), "has_activity_type", "asociacion", usuario_id,
                            procedencia)
    for agente_id in {lote.dependencia_origen_id, lote.remitente_id} - {None}:
        descripcion._relacionar(db, ("entidad_vocabulario", agente_id), yo, "performs_or_performed", "asociacion",
                                usuario_id, procedencia)
    if lote.acta_fecha_edtf:
        try:
            i = fechas.interpretar(lote.acta_fecha_edtf)
            actividad.existencia_edtf = i.edtf
            f = descripcion._crear_fecha(db, lote.acta_fecha_edtf, i, "persona", None, None)
            db.flush()
            descripcion._relacionar(db, ("fecha", f.id), yo, "is_date_associated_with", "temporal", usuario_id,
                                    procedencia)
        except fechas.FechaInvalida:
            pass
    for inst in archivos:
        descripcion._relacionar(db, yo, ("instanciacion", inst.id), "affects_or_affected", "asociacion", usuario_id,
                                procedencia, rol="ingreso")
    db.flush()
    return actividad


