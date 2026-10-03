"""
Mecanismos (RiC-E13 Mechanism) que ejecutan acciones técnicas.

Los prompts de vocabularios (v2) y de preservación (v2.2) exigen que el
programa que actúa de forma autónoma —el motor de análisis, Siegfried,
Ghostscript, Pillow o el propio sistema en una verificación periódica—
quede como agente de subtipo mecanismo en el vocabulario del fondo, con su
versión exacta, y que cada acción técnica apunte a ese agente. Nunca se
guarda el nombre del programa como texto libre para identificar al agente.

Este archivo solo traduce «programa + versión» al agente; quien lo crea o
lo reutiliza es vocabulario.mecanismo(), el servicio único de registro.
"""

import re
import uuid

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.descripcion import EntidadVocabulario
from app.servicios import vocabulario

VERSION_SISTEMA = "2.0.0"  # la misma que publica la API (app/main.py)


def _vigente(db: Session, e: EntidadVocabulario | None) -> EntidadVocabulario | None:
    while e is not None and e.estado == "fusionada" and e.fusionada_en_id:
        e = db.get(EntidadVocabulario, e.fusionada_en_id)
    return e


def obtener(db: Session, fondo_id: uuid.UUID, programa: str, version: str,
            usuario_id: uuid.UUID | None = None) -> EntidadVocabulario:
    return vocabulario.mecanismo(db, fondo_id=fondo_id, nombre=programa, version=version or "desconocida",
                                 usuario_id=usuario_id)


def del_sistema(db: Session, fondo_id: uuid.UUID) -> EntidadVocabulario:
    """El propio sistema, cuando actúa solo: huella, verificación periódica,
    segunda copia, restauración ejecutada."""
    return obtener(db, fondo_id, settings.nombre_sistema, VERSION_SISTEMA)


def del_motor(db: Session, fondo_id: uuid.UUID, motor: str | None,
              usuario_id: uuid.UUID | None = None) -> EntidadVocabulario | None:
    """El motor de análisis: su versión exacta es el identificador del
    modelo («gemini-2.5-flash»), que es lo que cambia su comportamiento."""
    if not motor:
        return None
    return obtener(db, fondo_id, "Motor de análisis", motor.strip(), usuario_id)


CLAVE_MOTOR = "mecanismos_motor"


def preparar_motor(db: Session, fondo_id: uuid.UUID, motor: str | None,
                   usuario_id: uuid.UUID | None = None) -> EntidadVocabulario | None:
    """Antes de guardar lo que propuso el motor: deja el mecanismo listo en
    la sesión, y todo dato nuevo que lleve ese motor queda apuntando a él
    al guardarse (ver _vincular_motor)."""
    e = del_motor(db, fondo_id, motor, usuario_id)
    if e is not None:
        db.info.setdefault(CLAVE_MOTOR, {})[motor] = e.id
    return e


@event.listens_for(Session, "before_flush")
def _vincular_motor(sesion: Session, _contexto, _instancias) -> None:
    """Sin consultas: solo copia el identificador preparado. Lo que no se
    preparó lo vincula después el trabajador (vincular_anteriores)."""
    preparados = sesion.info.get(CLAVE_MOTOR)
    if not preparados:
        return
    for obj in sesion.new:
        motor = getattr(obj, "motor", None)
        if motor and hasattr(obj, "motor_id") and obj.motor_id is None and motor in preparados:
            obj.motor_id = preparados[motor]


# «siegfried 1.11.9 · PRONOM DROID_SignatureFile_V125.xml; container-signature-20260119.xml»
_SIEGFRIED = re.compile(r"^\s*siegfried\s+(\S+)(?:\s*·\s*PRONOM\s+(.+))?$", re.I)
# «Ghostscript 10.02.1 (pdfwrite, PDF/A-2b, perfil sRGB)»
_PROGRAMA = re.compile(r"^\s*([A-Za-zÁÉÍÓÚáéíóúñÑ][\w\-]*)\s+(\d[\w.\-]*)\s*(?:\((.*)\))?\s*$")


def version_siegfried(herramienta: str) -> tuple[str, str]:
    """Versión del programa y de sus firmas: las dos cambian el resultado de
    la identificación, así que las dos son parte de la versión exacta."""
    m = _SIEGFRIED.match(herramienta or "")
    if not m:
        return "Siegfried", (herramienta or "desconocida").strip()[:120]
    version, firmas = m.group(1), m.group(2)
    if firmas:
        nombres = [re.sub(r"\.xml$", "", f.strip()) for f in firmas.split(";") if f.strip()]
        version = f"{version} (firmas {', '.join(nombres)})"
    return "Siegfried", version[:120]


def de_identificacion(db: Session, fondo_id: uuid.UUID, herramienta: str | None) -> EntidadVocabulario | None:
    if not herramienta:
        return None
    programa, version = version_siegfried(herramienta)
    return obtener(db, fondo_id, programa, version)


def separar(texto: str | None) -> tuple[str, str, str | None] | None:
    """«Ghostscript 10.02.1 (pdfwrite, PDF/A-2b)» → (programa, versión,
    parámetros). None si el texto no nombra un programa con versión (una
    conversión externa, por ejemplo)."""
    m = _PROGRAMA.match(texto or "")
    if not m:
        return None
    return m.group(1), m.group(2), (m.group(3) or None)


def agente_premis(e: EntidadVocabulario) -> dict:
    """El agente PREMIS de un mecanismo: su identificador es el del
    vocabulario del fondo, el mismo que usan descripción y la exportación."""
    return {"tipo_id": f"{settings.nombre_sistema} vocabulario", "id": str(e.id), "nombre": e.nombre,
            "tipo": "software", "version": e.version}


def etiqueta(db: Session, mecanismo_id: uuid.UUID | None, respaldo: str | None = None) -> str | None:
    """Nombre vigente del mecanismo (si se fusionó, el de la definitiva)."""
    e = _vigente(db, db.get(EntidadVocabulario, mecanismo_id)) if mecanismo_id else None
    return e.nombre if e is not None else respaldo


def resumen(db: Session, mecanismo_id: uuid.UUID | None) -> dict | None:
    e = _vigente(db, db.get(EntidadVocabulario, mecanismo_id)) if mecanismo_id else None
    return {"id": str(e.id), "nombre": e.nombre, "version": e.version} if e is not None else None


# --- Filas anteriores a la migración 0013 -------------------------------------------------------


def vincular_anteriores(db: Session, limite: int = 200) -> int:
    """La llama el trabajador: las filas que se guardaron antes de esta
    versión con el programa como texto quedan apuntando a su mecanismo. El
    texto original no se borra (es lo que se vio entonces). Devuelve
    cuántas filas vinculó."""
    from app.models.descripcion import Actividad, Fecha, Relacion
    from app.models.instanciacion import Instanciacion
    from app.models.preservacion import Migracion, Restauracion, SegundaCopia, VerificacionIntegridad
    from app.models.recurso_documental import RecursoDocumental

    n = 0
    for inst in db.scalars(select(Instanciacion).where(Instanciacion.mecanismo_identificacion_id.is_(None),
                                                       Instanciacion.herramienta_identificacion.is_not(None))
                           .limit(limite)).all():
        inst.mecanismo_identificacion_id = de_identificacion(db, inst.fondo_id, inst.herramienta_identificacion).id
        n += 1
    for m, fondo_id in db.execute(select(Migracion, Instanciacion.fondo_id)
                                  .join(Instanciacion, Instanciacion.id == Migracion.instanciacion_origen_id)
                                  .where(Migracion.mecanismo_id.is_(None), Migracion.modo == "automatica",
                                         Migracion.herramienta.is_not(None)).limit(limite)).all():
        partes = separar(m.herramienta)
        if partes:
            m.mecanismo_id = obtener(db, fondo_id, partes[0], partes[1]).id
            m.parametros = m.parametros or partes[2]
            n += 1
    for modelo in (VerificacionIntegridad, SegundaCopia, Restauracion):
        for fila, fondo_id in db.execute(select(modelo, Instanciacion.fondo_id)
                                         .join(Instanciacion, Instanciacion.id == modelo.instanciacion_id)
                                         .where(modelo.mecanismo_id.is_(None)).limit(limite)).all():
            fila.mecanismo_id = del_sistema(db, fondo_id).id
            n += 1
    for modelo in (EntidadVocabulario, RecursoDocumental):
        for fila in db.scalars(select(modelo).where(modelo.motor_id.is_(None), modelo.motor.is_not(None))
                               .limit(limite)).all():
            fondo_id = fila.fondo_id if modelo is EntidadVocabulario else (fila.fondo_id or fila.id)
            fila.motor_id = del_motor(db, fondo_id, fila.motor).id
            n += 1
    for modelo in (Relacion, Fecha, Actividad):
        for fila in db.scalars(select(modelo).where(modelo.motor_id.is_(None), modelo.motor.is_not(None))
                               .limit(limite)).all():
            fondo_id = _fondo_de(db, fila)
            if fondo_id is not None:
                fila.motor_id = del_motor(db, fondo_id, fila.motor).id
                n += 1
    if n:
        db.flush()
    return n


def _fondo_de(db: Session, fila) -> uuid.UUID | None:
    """El fondo de una relación, actividad o fecha: el del recurso que la cita."""
    from app.models.descripcion import Relacion
    from app.models.recurso_documental import RecursoDocumental

    if getattr(fila, "fondo_id", None):
        return fila.fondo_id
    recurso_id = None
    if getattr(fila, "origen_tipo", None) == "recurso_documental":
        recurso_id = fila.origen_id
    elif getattr(fila, "destino_tipo", None) == "recurso_documental":
        recurso_id = fila.destino_id
    else:  # una fecha: la relación que la cita
        recurso_id = db.scalar(select(Relacion.origen_id).where(Relacion.destino_id == fila.id,
                                                               Relacion.origen_tipo == "recurso_documental").limit(1))
    r = db.get(RecursoDocumental, recurso_id) if recurso_id else None
    if r is None and getattr(fila, "origen_tipo", None) == "entidad_vocabulario":
        e = db.get(EntidadVocabulario, fila.origen_id)
        return e.fondo_id if e else None
    return (r.fondo_id or r.id) if r is not None else None
