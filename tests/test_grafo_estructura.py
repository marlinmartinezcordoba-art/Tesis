"""
Vista «Estructura según la TRD» del grafo: el fondo, sus dependencias, las series y los documentos
(rico:includesOrIncluded), la regla de retención de cada serie (rico:regulatesOrRegulated) y el documento
de la TRD, que expresa las reglas (rico:isOrWasExpressedBy) y describe el fondo (rico:describesOrDescribed).
Agentes, lugares y fechas no entran: son contexto.
"""

import uuid

from app.db.base import ahora
from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental
from app.models.trd import VersionTrd
from app.servicios import vocabulario


def _fondo(db):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Ministerio de Ambiente", publicado_en=ahora())
    f.fondo_id = f.id
    db.add(f)
    db.flush()

    def recurso(nivel, titulo, padre, codigo=None):
        r = RecursoDocumental(id=uuid.uuid4(), nivel=nivel, titulo=titulo, fondo_id=f.id, incluido_en_id=padre.id,
                              codigo_referencia=codigo, publicado_en=ahora())
        db.add(r)
        db.flush()
        return r

    seccion = recurso("seccion", "Despacho del Ministro", f, "1000")
    serie = recurso("serie", "Actas", seccion, "1000.02")
    doc = recurso("unidad_documental", "Acta 12 de 2025", serie)
    regla = vocabulario.crear(db, fondo_id=f.id, clase="regla", nombre="Actas: AG 2, AC 8, CT", subtipo=None,
                              origen="persona", confianza=None, motor=None, usuario_id=None)
    db.add(Relacion(origen_tipo="entidad_vocabulario", origen_id=regla.id, destino_tipo="recurso_documental",
                    destino_id=serie.id, tipo_relacion="asociacion", codigo_ric="regulates_or_regulated",
                    rol="retencion", origen="persona"))
    persona = vocabulario.crear(db, fondo_id=f.id, clase="agente", nombre="Ana Ruiz", subtipo="persona",
                                origen="persona", confianza=None, motor=None, usuario_id=None)
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=doc.id, destino_tipo="entidad_vocabulario",
                    destino_id=persona.id, tipo_relacion="procedencia", codigo_ric="has_creator", origen="persona"))
    v = VersionTrd(fondo_id=f.id, numero=1, nombre="TRD versión 1", estado="vigente",
                   acto_aprobacion="Resolución 123 de 2024")
    db.add(v)
    db.commit()
    return f, seccion, serie, doc, regla, persona, v


def test_la_estructura_muestra_dependencias_series_reglas_trd_y_documentos(cliente, db, cabeceras_admin):
    f, seccion, serie, doc, regla, persona, v = _fondo(db)
    r = cliente.get(f"/api/grafo/estructura?fondo_id={f.id}", headers=cabeceras_admin)
    assert r.status_code == 200, r.text
    g = r.json()
    claves = {n["clave"] for n in g["nodos"]}
    k = lambda tipo, x: f"{tipo}:{x.id}"  # noqa: E731
    assert {k("recurso_documental", x) for x in (f, seccion, serie, doc)} <= claves
    assert k("entidad_vocabulario", regla) in claves and f"trd:{v.id}" in claves
    assert k("entidad_vocabulario", persona) not in claves  # el contexto no entra en la estructura
    aristas = {(a["desde"], a["hacia"], a["codigo_ric"]) for a in g["aristas"]}
    assert (k("recurso_documental", f), k("recurso_documental", seccion), "includes_or_included") in aristas
    assert (k("recurso_documental", serie), k("recurso_documental", doc), "includes_or_included") in aristas
    assert (k("entidad_vocabulario", regla), k("recurso_documental", serie), "regulates_or_regulated") in aristas
    assert (k("entidad_vocabulario", regla), f"trd:{v.id}", "is_or_was_expressed_by") in aristas
    assert (f"trd:{v.id}", k("recurso_documental", f), "describes_or_described") in aristas
    uris = {a["codigo_ric"]: a["uri_rico"] for a in g["aristas"]}
    assert uris["is_or_was_expressed_by"].endswith("isOrWasExpressedBy")
    assert uris["describes_or_described"].endswith("describesOrDescribed")
