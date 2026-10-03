"""
Declaración básica de derechos (entidad Derechos de PREMIS), en la versión
mínima que pide un fondo histórico de acceso público: sobre qué base
(estatuto, licencia…), si el acceso es público, clasificado o reservado
(Ley 1712 de 2014, arts. 18 y 19), si se permite reproducir, y el
fundamento citado. No es un gestor de derechos de autor.

Se declara sobre una instanciación o sobre un Record Resource de cualquier
nivel, y se hereda hacia abajo: a un archivo le aplica la suya propia o, si
no tiene, la del nivel más cercano hacia arriba (documento, expediente…
fondo). Una declaración no se borra: la nueva deja a la anterior como
«reemplazada».
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import ahora
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.preservacion import DeclaracionDerechos
from app.models.recurso_documental import RecursoDocumental
from app.servicios.auditoria import registrar

BASE_NOMBRE = {"estatuto": "Norma (estatuto)", "licencia": "Licencia", "derecho_de_autor": "Derecho de autor",
               "politica_institucional": "Política institucional", "otra": "Otra"}
# PREMIS rightsBasis (vocabulario de la Library of Congress).
BASE_PREMIS = {"estatuto": "Statute", "licencia": "License", "derecho_de_autor": "Copyright",
               "politica_institucional": "Institutional policy", "otra": "Other"}
ACCESO_NOMBRE = {"publico": "Acceso público", "clasificado": "Información clasificada (Ley 1712 de 2014, art. 18)",
                 "reservado": "Información reservada (Ley 1712 de 2014, art. 19)"}
# Ley 1712 de 2014: lo que no se entrega a quien no es del equipo de archivo.
ACCESO_RESTRINGIDO = ("clasificado", "reservado")

REPRODUCCION_NOMBRE = {"permitida": "Reproducción permitida", "condicionada": "Reproducción con condiciones",
                       "no_permitida": "Reproducción no permitida"}


def _vigente(db: Session, entidad_id: uuid.UUID) -> DeclaracionDerechos | None:
    return db.scalar(select(DeclaracionDerechos).where(DeclaracionDerechos.entidad_id == entidad_id,
                                                       DeclaracionDerechos.vigente.is_(True)))


def restringe(d: DeclaracionDerechos | None, hoy: date | None = None) -> bool:
    """¿Esta declaración impide hoy la consulta pública? Una reserva con plazo
    vencido ya no restringe: la Ley 1712, art. 22, fija su duración y al
    vencer el documento vuelve a ser público sin trámite. La declaración no
    se toca (la historia queda); solo deja de aplicarse."""
    if d is None or d.acceso not in ACCESO_RESTRINGIDO:
        return False
    return d.vigente_hasta is None or d.vigente_hasta >= (hoy or date.today())


def declaracion_que_rige(db: Session, inst: Instanciacion) -> tuple[DeclaracionDerechos | None, str | None, str | None]:
    """La declaración que rige el archivo (la propia o la heredada del nivel
    más cercano hacia arriba), con el nivel y el título de donde viene."""
    propia = _vigente(db, inst.id)
    if propia is not None:
        return propia, "instanciacion", inst.nombre_original
    for recurso in recursos_de(db, inst):
        actual = recurso
        while actual is not None:
            d = _vigente(db, actual.id)
            if d is not None:
                return d, actual.nivel, actual.titulo
            actual = db.get(RecursoDocumental, actual.incluido_en_id) if actual.incluido_en_id else None
    fondo = db.get(RecursoDocumental, inst.fondo_id)
    d = _vigente(db, fondo.id) if fondo else None
    return (d, "fondo", fondo.titulo) if d else (None, None, None)


def instanciacion_restringida(db: Session, inst: Instanciacion) -> bool:
    """¿El archivo está hoy bajo reserva o clasificación, propia o heredada?"""
    return restringe(declaracion_que_rige(db, inst)[0])


def out(d: DeclaracionDerechos, nivel: str | None = None, titulo: str | None = None) -> dict:
    return {"id": str(d.id), "entidad_tipo": d.entidad_tipo, "entidad_id": str(d.entidad_id), "nivel": nivel,
            "titulo": titulo, "base": d.base, "base_nombre": BASE_NOMBRE[d.base], "acceso": d.acceso,
            "acceso_nombre": ACCESO_NOMBRE[d.acceso], "reproduccion": d.reproduccion,
            "reproduccion_nombre": REPRODUCCION_NOMBRE[d.reproduccion], "fundamento": d.fundamento, "nota": d.nota,
            "vigente_hasta": d.vigente_hasta, "vencida": d.acceso in ACCESO_RESTRINGIDO and not restringe(d),
            "creada_en": d.creada_en}


def recursos_de(db: Session, inst: Instanciacion) -> list[RecursoDocumental]:
    """Record Resources que describen esta instanciación (o su original si
    salió de una migración y aún no se publicó con ella)."""
    ids = list(db.scalars(select(Relacion.origen_id).where(
        Relacion.destino_id == inst.id, Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente")).all())
    if not ids and inst.derivada_de_id:
        return recursos_de(db, db.get(Instanciacion, inst.derivada_de_id))
    return [r for r in (db.get(RecursoDocumental, i) for i in ids) if r is not None]


def aplicable(db: Session, inst: Instanciacion) -> dict | None:
    """La declaración que rige este archivo y de dónde viene."""
    d, nivel, titulo = declaracion_que_rige(db, inst)
    if d is None:
        return None
    return out(d, nivel, titulo) | {"heredada": nivel != "instanciacion", "restringe": restringe(d)}


def declarar(db: Session, *, entidad_tipo: str, entidad_id: uuid.UUID, base: str, acceso: str, reproduccion: str,
             fundamento: str, nota: str | None, vigente_hasta: date | None, usuario_id: uuid.UUID,
             ip: str | None = None) -> DeclaracionDerechos:
    if entidad_tipo == "instanciacion":
        entidad = db.get(Instanciacion, entidad_id)
        fondo_id, nombre = (entidad.fondo_id, entidad.nombre_original) if entidad else (None, None)
    else:
        entidad = db.get(RecursoDocumental, entidad_id)
        fondo_id, nombre = (entidad.fondo_id, entidad.titulo) if entidad else (None, None)
    if entidad is None:
        raise LookupError("No existe esa instanciación o ese Record Resource.")
    anterior = _vigente(db, entidad_id)
    if anterior is not None:
        anterior.vigente, anterior.reemplazada_en = False, ahora()
    d = DeclaracionDerechos(fondo_id=fondo_id, entidad_tipo=entidad_tipo, entidad_id=entidad_id, base=base,
                            acceso=acceso, reproduccion=reproduccion, fundamento=fundamento.strip(),
                            nota=(nota or "").strip() or None, vigente_hasta=vigente_hasta, creada_por_id=usuario_id)
    db.add(d)
    db.flush()
    registrar(db, modulo="preservacion", accion="derechos_declarados", usuario_id=usuario_id,
              entidad_tipo=entidad_tipo, entidad_id=entidad_id, ip=ip, detalle=nombre,
              anterior={"acceso": anterior.acceso, "fundamento": anterior.fundamento} if anterior else None,
              nuevo={"declaracion_id": str(d.id), "base": base, "acceso": acceso, "reproduccion": reproduccion,
                     "fundamento": d.fundamento})
    return d
