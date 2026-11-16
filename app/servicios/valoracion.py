"""La valoración documental como actividad RiC (RiC-AG 0.1, «Appraisal and disposition»).

Aprobar una versión de la TRD o de la TVD es el resultado de una valoración: una rico:Activity
del tipo «Valoración documental» que afecta al fondo valorado (R059) y da como resultado las
reglas de retención de esa versión (R061), con su fecha (la de aprobación, R068). Así el grafo
cierra el ciclo valoración → regla → disposición: la disposición final ya es una actividad
regulada por esas mismas reglas (servicios/disposicion.py).

No se inventa quién valoró: el acto de aprobación y la convalidación quedan en la historia de la
actividad; el comité o la dependencia se une desde su ficha cuando se conozca.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.models.trd import VersionTrd

TIPO = "Valoración documental"


def _reglas_de(db: Session, v: VersionTrd) -> list[uuid.UUID]:
    """Las reglas de retención que esta versión dejó regulando series del fondo."""
    recursos = select(RecursoDocumental.id).where(RecursoDocumental.fondo_id == v.fondo_id)
    return list(dict.fromkeys(db.scalars(select(Relacion.origen_id).where(
        Relacion.codigo_ric == "regulates_or_regulated", Relacion.estado == "vigente", Relacion.nota == v.nombre,
        Relacion.origen_tipo == "entidad_vocabulario", Relacion.destino_id.in_(recursos)))))


def registrar(db: Session, v: VersionTrd, usuario_id: uuid.UUID) -> EntidadVocabulario:
    from app.servicios import cuadro, descripcion, fechas

    sigla = v.instrumento.upper()
    actividad = cuadro._de_vocabulario(db, v.fondo_id, "actividad", f"{TIPO}: {sigla} {v.nombre}", usuario_id)[0]
    fecha = (v.fecha_aprobacion or v.vigente_desde)
    actividad.existencia_edtf = fecha.isoformat() if fecha else None
    actividad.historia = " ".join(x for x in (
        f"Aprobada por {v.acto_aprobacion}." if v.acto_aprobacion else None,
        f"Convalidada: {v.convalidacion}." if v.convalidacion else None,
        f"Periodo valorado: {v.periodo}." if v.instrumento == "tvd" and v.periodo else None) if x) or None
    tipo = cuadro._de_vocabulario(db, v.fondo_id, "tipo_actividad", TIPO, usuario_id)[0]
    db.flush()
    yo, procedencia = ("entidad_vocabulario", actividad.id), ("persona", None, None)
    descripcion._relacionar(db, yo, ("entidad_vocabulario", tipo.id), "has_activity_type", "asociacion", usuario_id,
                            procedencia)
    descripcion._relacionar(db, yo, ("recurso_documental", v.fondo_id), "affects_or_affected", "asociacion", usuario_id,
                            procedencia, rol="valoracion")
    if fecha:
        f = descripcion._crear_fecha(db, fecha.isoformat(), fechas.interpretar(fecha.isoformat()), "persona", None, None)
        db.flush()
        descripcion._relacionar(db, ("fecha", f.id), yo, "is_date_associated_with", "temporal", usuario_id, procedencia)
    for regla_id in _reglas_de(db, v):
        descripcion._relacionar(db, yo, ("entidad_vocabulario", regla_id), "results_or_resulted_in", "asociacion",
                                usuario_id, procedencia)
    db.flush()
    return actividad
