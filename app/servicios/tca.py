"""
Tablas de Control de Acceso (TCA): la condición de acceso de cada serie y subserie.

En RiC la restricción es una regla que rige la agrupación y se hereda a lo que
incluye: una declaración de derechos sobre la serie rige a sus expedientes y
documentos (la misma herencia que ya aplican el catálogo, el buscador, el grafo
y los datos abiertos). La TCA es la vista por serie de esas declaraciones, con
su categoría (pública, clasificada, reservada), el fundamento legal, la
vigencia de la restricción, las condiciones de consulta y quién autoriza.

- Una declaración nueva reemplaza a la anterior, que queda en el historial (nada se borra).
- La reserva y la clasificación exigen fundamento y una fecha final de no más de
  15 años (Ley 1712 de 2014, art. 22).
- Cada cambio queda en la auditoría.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental
from app.servicios import derechos

ACCESO = {"publico": "Pública", "clasificado": "Clasificada", "reservado": "Reservada"}
REPRODUCCION = {"permitida": "Permitida", "condicionada": "Condicionada", "no_permitida": "No permitida"}
MAXIMO_ANIOS = 15


class ErrorTca(ValueError):
    pass


def _fila(d) -> dict | None:
    if d is None:
        return None
    return {"acceso": d.acceso, "acceso_nombre": ACCESO.get(d.acceso, d.acceso), "fundamento": d.fundamento,
            "reproduccion": d.reproduccion, "vigente_hasta": d.vigente_hasta.isoformat() if d.vigente_hasta else None,
            "condiciones": d.nota, "responsable": d.responsable_autorizacion,
            "declarada_en": d.creada_en.isoformat() if d.creada_en else None}


def tabla(db: Session, fondo: RecursoDocumental) -> dict:
    todos = list(db.scalars(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo.id)))
    hijos: dict[uuid.UUID, list[RecursoDocumental]] = {}
    for r in todos:
        if r.incluido_en_id:
            hijos.setdefault(r.incluido_en_id, []).append(r)

    def documentos(rid: uuid.UUID) -> int:
        n, pila = 0, list(hijos.get(rid, []))
        while pila:
            x = pila.pop()
            n += x.nivel in ("expediente", "unidad_documental") and x.publicado_en is not None
            pila.extend(hijos.get(x.id, []))
        return n

    series = sorted((r for r in todos if r.nivel in ("serie", "subserie")),
                    key=lambda r: ((r.codigo_referencia or "~"), r.titulo.lower()))
    filas = []
    for s in series:
        propia = derechos._vigente(db, s.id)
        rige = propia or derechos.declaracion_de_recurso(db, s)
        filas.append({"id": str(s.id), "nivel": s.nivel, "codigo": s.codigo_referencia, "titulo": s.titulo,
                      "propia": _fila(propia), "heredada": None if propia else _fila(rige),
                      "documentos": documentos(s.id)})
    restringidas = sum(1 for f in filas if (f["propia"] or f["heredada"] or {}).get("acceso") in derechos.ACCESO_RESTRINGIDO)
    return {"fondo": {"id": str(fondo.id), "titulo": fondo.titulo}, "series": filas,
            "totales": {"series": len(filas), "con_condicion": sum(1 for f in filas if f["propia"]),
                        "restringidas": restringidas}}


def declarar(db: Session, serie: RecursoDocumental, *, acceso: str, fundamento: str, reproduccion: str,
             vigente_hasta: date | None, condiciones: str | None, responsable: str | None, usuario_id: uuid.UUID,
             ip: str | None = None):
    if serie.nivel not in ("serie", "subserie"):
        raise ErrorTca("La TCA se declara por serie o subserie; un documento suelto se declara en su descripción.")
    if acceso not in ACCESO:
        raise ErrorTca("Categoría de acceso no válida: pública, clasificada o reservada.")
    if reproduccion not in REPRODUCCION:
        raise ErrorTca("Condición de reproducción no válida.")
    if len((fundamento or "").strip()) < 5:
        raise ErrorTca("Escriba el fundamento legal (p. ej. «Ley 1712 de 2014, art. 19»).")
    if acceso != "publico":
        if vigente_hasta is None:
            raise ErrorTca("La clasificación o la reserva necesita la fecha hasta la que rige.")
        hoy = date.today()
        if vigente_hasta <= hoy:
            raise ErrorTca("La fecha final de la restricción ya pasó.")
        if vigente_hasta > hoy.replace(year=hoy.year + MAXIMO_ANIOS):
            raise ErrorTca(f"La restricción no puede durar más de {MAXIMO_ANIOS} años (Ley 1712 de 2014, art. 22).")
    d = derechos.declarar(db, entidad_tipo="recurso_documental", entidad_id=serie.id, base="estatuto", acceso=acceso,
                          reproduccion=reproduccion, fundamento=fundamento, nota=condiciones,
                          vigente_hasta=vigente_hasta if acceso != "publico" else None, usuario_id=usuario_id, ip=ip)
    d.responsable_autorizacion = (responsable or "").strip()[:200] or None
    return d
