"""
Versiones consultables y restaurables de cada descripción (brecha RF-RIC-001).

- `registrar` toma la instantánea de la descripción (sus atributos con la
  procedencia, y el contexto: entidades, documentos, partes, secuencia,
  nivel superior y forma documental) y crea la versión siguiente, solo si
  algo cambió desde la anterior.
- `historial` lista las versiones con autor, fecha, motivo y lo que cambió
  respecto de la anterior.
- `restaurar` devuelve los atributos de una versión anterior y crea una
  versión nueva («restauración de la versión N»): nada se pierde. El
  contexto (relaciones con agentes, lugares, documentos) no se restaura así:
  cada relación tiene su propia historia (se anula, no se borra) y se
  corrige desde la edición, con la versión anterior a la vista.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental
from app.models.usuario import Usuario
from app.models.version_descripcion import VersionDescripcion
from app.servicios import atributos

MOTIVO_NOMBRE = {"estado_inicial": "Estado al activar el versionado", "publicacion": "Publicación",
                 "edicion": "Corrección", "restauracion": "Restauración", "agrupacion": "Creación de la agrupación"}
CONTEXTO = ("incluido_en", "forma_documental", "entidades", "instanciaciones", "partes", "secuencia")
ETIQUETA_CONTEXTO = {"incluido_en": "Nivel superior", "forma_documental": "Forma documental (nombre)",
                     "entidades": "Entidades y relaciones", "instanciaciones": "Documentos (instanciaciones)",
                     "partes": "Partes documentales", "secuencia": "Secuencia en la serie"}


class ErrorVersion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def _valor(v):
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return list(v)
    return v


def instantanea(db: Session, recurso: RecursoDocumental) -> dict:
    from app.servicios import descripcion

    columnas = [a.clave for a in atributos.ATRIBUTOS] + list(atributos.PROCEDENCIA)
    resumen = descripcion.resumen(db, recurso)
    return {"atributos": {c: _valor(getattr(recurso, c)) for c in columnas},
            "contexto": {k: resumen.get(k) for k in CONTEXTO}}


def ultima(db: Session, recurso_id: uuid.UUID) -> VersionDescripcion | None:
    return db.scalar(select(VersionDescripcion).where(VersionDescripcion.recurso_id == recurso_id)
                     .order_by(VersionDescripcion.numero.desc()).limit(1))


def registrar(db: Session, recurso: RecursoDocumental, motivo: str, autor_id: uuid.UUID | None,
              restaurada_de: int | None = None, hubo_cambio: bool = False) -> VersionDescripcion | None:
    """La versión siguiente, si algo cambió desde la anterior. La versión del
    estado inicial (migración 0037) no guardó el contexto: frente a ella, se
    crea versión si cambian los atributos o si la corrección cambió algo."""
    db.flush()
    contenido = instantanea(db, recurso)
    anterior = ultima(db, recurso.id)
    if anterior is not None and restaurada_de is None:
        if anterior.contenido.get("contexto") is None:
            if anterior.contenido["atributos"] == contenido["atributos"] and not hubo_cambio:
                return None
        elif anterior.contenido == contenido:
            return None
    # El número lo da la base bajo un candado por descripción: dos ediciones
    # simultáneas no repiten número.
    db.execute(text("SELECT pg_advisory_xact_lock(724200, hashtext(:r))"), {"r": str(recurso.id)})
    numero = (db.scalar(select(func.max(VersionDescripcion.numero)).where(VersionDescripcion.recurso_id == recurso.id))
              or 0) + 1
    v = VersionDescripcion(id=uuid.uuid4(), recurso_id=recurso.id, numero=numero, motivo=motivo,
                           restaurada_de=restaurada_de, autor_id=autor_id, contenido=contenido)
    db.add(v)
    db.flush()
    return v


def _cambios(antes: dict | None, despues: dict) -> list[dict]:
    if antes is None:
        return []
    salida = []
    for a in atributos.ATRIBUTOS:
        x, y = antes["atributos"].get(a.clave), despues["atributos"].get(a.clave)
        if x != y:
            fuente_x = antes["atributos"].get(a.origen) if a.origen else None
            fuente_y = despues["atributos"].get(a.origen) if a.origen else None
            salida.append({"campo": a.clave, "etiqueta": a.etiqueta, "antes": x, "despues": y,
                           "fuente_antes": fuente_x, "fuente_despues": fuente_y})
    ca, cd = antes.get("contexto"), despues.get("contexto")
    if ca is not None and cd is not None:
        for k in CONTEXTO:
            x, y = ca.get(k), cd.get(k)
            if x == y:
                continue
            if isinstance(x, list) and isinstance(y, list):
                salida.append({"campo": k, "etiqueta": ETIQUETA_CONTEXTO[k],
                               "agregados": [e for e in y if e not in x], "quitados": [e for e in x if e not in y]})
            else:
                salida.append({"campo": k, "etiqueta": ETIQUETA_CONTEXTO[k], "antes": x, "despues": y})
    return salida


def integra(db: Session, v: VersionDescripcion) -> bool:
    calculada = db.scalar(text("SELECT encode(sha256(convert_to(contenido::text, 'UTF8')), 'hex') "
                               "FROM versiones_descripcion WHERE id = :i"), {"i": v.id})
    return calculada == v.huella


def historial(db: Session, recurso: RecursoDocumental) -> list[dict]:
    versiones = db.scalars(select(VersionDescripcion).where(VersionDescripcion.recurso_id == recurso.id)
                           .order_by(VersionDescripcion.numero)).all()
    autores = {u.id: u.nombre for u in db.scalars(select(Usuario).where(
        Usuario.id.in_([v.autor_id for v in versiones if v.autor_id])))}
    salida, previa = [], None
    for v in versiones:
        salida.append({"numero": v.numero, "motivo": v.motivo, "motivo_nombre": MOTIVO_NOMBRE.get(v.motivo, v.motivo),
                       "restaurada_de": v.restaurada_de, "autor": autores.get(v.autor_id),
                       "creada_en": v.creada_en.isoformat(), "huella": v.huella, "integra": integra(db, v),
                       "con_contexto": v.contenido.get("contexto") is not None,
                       "cambios": _cambios(previa.contenido if previa else None, v.contenido)})
        previa = v
    return list(reversed(salida))  # la más reciente primero


def una(db: Session, recurso: RecursoDocumental, numero: int) -> VersionDescripcion:
    v = db.scalar(select(VersionDescripcion).where(VersionDescripcion.recurso_id == recurso.id,
                                                   VersionDescripcion.numero == numero))
    if v is None:
        raise ErrorVersion("Esa versión no existe.", 404)
    return v


def restaurar(db: Session, recurso: RecursoDocumental, numero: int, autor_id: uuid.UUID) -> VersionDescripcion:
    """Devuelve los atributos de la versión `numero` (con su procedencia) y
    crea una versión nueva. Se valida igual que una edición."""
    from app.models.descripcion import EntidadVocabulario, TrabajoDescripcion

    if db.scalar(select(TrabajoDescripcion.id).where(TrabajoDescripcion.recurso_id == recurso.id,
                                                     TrabajoDescripcion.estado == "abierto")):
        raise ErrorVersion("La descripción está en edición: termine o cancele la edición antes de restaurar.", 409)
    v = una(db, recurso, numero)
    if numero == ultima(db, recurso.id).numero:
        raise ErrorVersion("Esa ya es la versión vigente.", 409)
    valores = v.contenido["atributos"]
    for a in atributos.ATRIBUTOS:
        if a.clave not in valores:
            continue
        try:
            atributos.validar_cardinalidad(a.clave, valores[a.clave])
        except atributos.ErrorAtributo as exc:
            raise ErrorVersion(str(exc)) from exc
    forma = valores.get("forma_documental_id")
    if forma and db.get(EntidadVocabulario, uuid.UUID(forma)) is None:
        raise ErrorVersion("La forma documental de esa versión ya no existe en el vocabulario.")
    for clave, valor in valores.items():
        if clave == "forma_documental_id":
            valor = uuid.UUID(valor) if valor else None
        setattr(recurso, clave, valor)
    from app.db.base import ahora

    recurso.actualizado_en = ahora()
    return registrar(db, recurso, "restauracion", autor_id, restaurada_de=numero)
