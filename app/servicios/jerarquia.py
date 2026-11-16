"""
La línea de un recurso documental hacia arriba en el cuadro: el recurso, el conjunto que lo incluye
y así hasta el fondo (rico:isOrWasIncludedIn). Un solo recorrido para todo lo que se hereda de un nivel
superior (la regla de retención, la declaración de derechos, la custodia, la serie de un documento) y
para las migas de las pantallas y los paquetes. No se repite un nivel (defensa ante un ciclo) y para
en el fondo.
"""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental

LIMITE = 64  # más niveles que cualquier cuadro real


def linea(db: Session, recurso: RecursoDocumental | None, *, incluir_propio: bool = True) -> Iterator[RecursoDocumental]:
    """El recurso (si `incluir_propio`) y sus superiores hasta el fondo, del más cercano al más lejano."""
    vistos: set = set()
    actual = recurso
    primero = True
    while actual is not None and actual.id not in vistos and len(vistos) < LIMITE:
        vistos.add(actual.id)
        if incluir_propio or not primero:
            yield actual
        primero = False
        if actual.nivel == "fondo" or actual.id == actual.fondo_id or not actual.incluido_en_id:
            return
        actual = db.get(RecursoDocumental, actual.incluido_en_id)


def serie_de(db: Session, recurso: RecursoDocumental) -> RecursoDocumental | None:
    """La serie o subserie más cercana por encima del recurso (o él mismo, si lo es)."""
    return next((x for x in linea(db, recurso) if x.nivel in ("serie", "subserie")), None)


def migas(db: Session, recurso: RecursoDocumental | None) -> list[RecursoDocumental]:
    """Del fondo al recurso, para mostrar dónde está."""
    return list(reversed(list(linea(db, recurso))))
