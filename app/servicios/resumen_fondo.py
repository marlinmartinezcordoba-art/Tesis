"""
Resumen del fondo para la portada del catálogo: composición por nivel,
productores, lugares y formas documentales más citados, archivos, y la
coherencia entre las fechas extremas declaradas del fondo y las fechas de
sus documentos descritos. Solo lectura; misma visibilidad que el grafo y la
exportación RiC-O (lo reservado no cuenta para quien no es archivista).
"""

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios.grafo import _Contexto
from app.servicios.instrumentos import NIVEL_NOMBRE

PRODUCCION = ("has_creator", "has_author", "has_accumulator")
TOPE = 5
_AÑOS = re.compile(r"(\d{4})")


def _citadas(db: Session, conteo: Counter) -> list[dict]:
    if not conteo:
        return []
    nombres = {e.id: e.nombre for e in db.scalars(select(EntidadVocabulario).where(
        EntidadVocabulario.id.in_(list(conteo)), EntidadVocabulario.estado == "activa"))}
    return [{"id": str(i), "nombre": nombres[i], "documentos": n}
            for i, n in conteo.most_common() if i in nombres][:TOPE]


def resumen(db: Session, fondo: RecursoDocumental, ver_restringidos: bool) -> dict:
    ctx = _Contexto(db, fondo, ver_restringidos)
    descripciones = [r for r in ctx.recursos.values() if r.id != fondo.id]
    ids = [r.id for r in descripciones]
    niveles = Counter(r.nivel for r in descripciones)
    productores, lugares, formas, archivos = Counter(), Counter(), Counter(), set()
    clases = {}
    if ids:
        filas = db.execute(select(Relacion.origen_id, Relacion.codigo_ric, Relacion.destino_tipo, Relacion.destino_id)
                           .where(Relacion.estado == "vigente", Relacion.origen_id.in_(ids))).all()
        entidades = {d for _, _, t, d in filas if t == "entidad_vocabulario"}
        clases = dict(db.execute(select(EntidadVocabulario.id, EntidadVocabulario.clase).where(
            EntidadVocabulario.id.in_(list(entidades)))).all()) if entidades else {}
        for _, codigo, tipo, destino in filas:
            if tipo == "instanciacion" and codigo == "has_or_had_instantiation":
                archivos.add(destino)
            elif tipo == "entidad_vocabulario" and codigo in PRODUCCION:
                productores[destino] += 1
            elif tipo == "entidad_vocabulario" and clases.get(destino) == "lugar":
                lugares[destino] += 1
        for r in descripciones:
            forma = r.tipo_parte_id if r.nivel == "parte_documental" else r.forma_documental_id
            if forma:
                formas[forma] += 1
    # Fechas: las de los documentos frente a las declaradas al registrar el fondo.
    fechas = [f for r in descripciones for par in ctx.fechas_recurso.get(r.id, []) for f in par if f]
    documentos = (min(fechas), max(fechas)) if fechas else None
    declaradas = [int(a) for a in _AÑOS.findall(fondo.fechas_extremas or "")]
    coherencia = None
    if documentos and len(declaradas) >= 1:
        desde, hasta = min(declaradas), max(declaradas)
        fuera = documentos[0].year < desde or documentos[1].year > hasta
        coherencia = {"declaradas": fondo.fechas_extremas, "documentos": f"{documentos[0].year}–{documentos[1].year}",
                      "coinciden": not fuera}
    return {
        "niveles": [{"nivel": n, "nombre": NIVEL_NOMBRE[n], "cantidad": niveles[n]} for n in NIVEL_NOMBRE if niveles.get(n)],
        "descripciones": len(descripciones), "archivos": len(archivos),
        "productores": _citadas(db, productores), "lugares": _citadas(db, lugares), "formas": _citadas(db, formas),
        "fechas": coherencia,
    }
