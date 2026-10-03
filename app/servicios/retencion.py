"""
Regla de retención de la tabla de retención documental (TRD) como
rico:Rule del vocabulario (hallazgos CM-18 y DES-09).

La regla dice cuántos años permanece la documentación en el archivo de
gestión y en el central, y cuál es su disposición final (Acuerdo AGN 004
de 2019). Se une a la serie o subserie que regula con
regulates_or_regulated (rol «retencion»). Los expedientes y documentos la
heredan del nivel más cercano hacia arriba que la tenga.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import DISPOSICION_FINAL, EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import vocabulario
from app.servicios.auditoria import registrar

DISPOSICION_NOMBRE = {"conservacion_total": "Conservación total", "eliminacion": "Eliminación",
                      "seleccion": "Selección", "medio_tecnico": "Reproducción por medio técnico"}


class ErrorRetencion(ValueError):
    pass


def validar(gestion, central, disposicion) -> None:
    for nombre, valor in (("archivo de gestión", gestion), ("archivo central", central)):
        if valor is not None and (not isinstance(valor, int) or isinstance(valor, bool) or not 0 <= valor <= 100):
            raise ErrorRetencion(f"Los años en el {nombre} son un número entero entre 0 y 100.")
    if disposicion is not None and disposicion not in DISPOSICION_FINAL:
        raise ErrorRetencion("La disposición final es conservación total, eliminación, selección o medio técnico.")


def crear_regla(db: Session, *, fondo_id: uuid.UUID, nombre: str, gestion: int | None, central: int | None,
                disposicion: str | None, procedimiento: str | None, usuario_id: uuid.UUID) -> EntidadVocabulario:
    nombre = " ".join((nombre or "").split())
    if not nombre:
        raise ErrorRetencion("La regla necesita un nombre (por ejemplo «TRD Actas, código 110.2»).")
    validar(gestion, central, disposicion)
    e = vocabulario.crear(db, fondo_id=fondo_id, clase="regla", nombre=nombre, subtipo=None, origen="persona",
                          confianza=None, motor=None, usuario_id=usuario_id)
    e.retencion_gestion_anios, e.retencion_central_anios, e.disposicion_final = gestion, central, disposicion
    e.historia = (procedimiento or "").strip() or None
    db.flush()
    registrar(db, modulo="vocabularios", accion="regla_creada", usuario_id=usuario_id,
              entidad_tipo="entidad_vocabulario", entidad_id=e.id, detalle=f"Regla de retención «{nombre}»",
              nuevo={"gestion": gestion, "central": central, "disposicion": disposicion})
    return e


def resumen(e: EntidadVocabulario) -> str:
    partes = []
    if e.retencion_gestion_anios is not None:
        partes.append(f"{e.retencion_gestion_anios} año(s) en el archivo de gestión")
    if e.retencion_central_anios is not None:
        partes.append(f"{e.retencion_central_anios} año(s) en el archivo central")
    if e.disposicion_final:
        partes.append(f"disposición final: {DISPOSICION_NOMBRE[e.disposicion_final].lower()}")
    return "; ".join(partes).capitalize() + "." if partes else ""


def retencion_de(db: Session, recurso: RecursoDocumental) -> dict | None:
    """La regla que rige la descripción: la propia o la del nivel más
    cercano hacia arriba (un expediente hereda la de su subserie o serie)."""
    actual = recurso
    while actual is not None:
        regla_id = db.scalar(select(Relacion.origen_id).where(
            Relacion.destino_id == actual.id, Relacion.codigo_ric == "regulates_or_regulated",
            Relacion.rol == "retencion", Relacion.estado == "vigente"))
        regla = db.get(EntidadVocabulario, regla_id) if regla_id else None
        if regla is not None and regla.estado == "activa":
            return {"regla": {"id": str(regla.id), "nombre": regla.nombre},
                    "gestion_anios": regla.retencion_gestion_anios, "central_anios": regla.retencion_central_anios,
                    "disposicion_final": regla.disposicion_final,
                    "disposicion_nombre": DISPOSICION_NOMBRE.get(regla.disposicion_final or ""),
                    "procedimiento": regla.historia, "resumen": resumen(regla),
                    "heredada_de": None if actual.id == recurso.id else {"id": str(actual.id), "nivel": actual.nivel,
                                                                         "titulo": actual.titulo}}
        actual = db.get(RecursoDocumental, actual.incluido_en_id) if actual.incluido_en_id and actual.id != actual.fondo_id else None
    return None
