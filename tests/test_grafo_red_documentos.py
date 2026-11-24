"""La red de los documentos descritos: cómo se relacionan entre sí por lo que comparten
(productor, lugar, norma, tipo documental) y por sus vínculos directos."""

import uuid

from app.db.base import ahora
from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def _doc(db, fondo, titulo):
    r = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo=titulo, fondo_id=fondo.id,
                          incluido_en_id=fondo.id, publicado_en=ahora())
    db.add(r)
    return r


def test_une_los_documentos_por_lo_que_comparten_y_por_sus_vinculos(cliente, db, fondo_descrito, archivista):  # noqa: F811
    fondo = fondo_descrito["fondo"]
    a, b, c = _doc(db, fondo, "Resolución 1919"), _doc(db, fondo, "Resolución 1920"), _doc(db, fondo, "Resolución 2001")
    mina = EntidadVocabulario(id=uuid.uuid4(), fondo_id=fondo.id, clase="agente", subtipo="entidad_corporativa",
                              nombre="Ministerio de Ambiente y Desarrollo Sostenible", nombre_normalizado="ministerio ambiente",
                              origen="persona", estado="activa")
    solo = EntidadVocabulario(id=uuid.uuid4(), fondo_id=fondo.id, clase="lugar", nombre="Vereda única",
                              nombre_normalizado="vereda unica", origen="persona", estado="activa")
    db.add_all([mina, solo])
    db.flush()
    for d in (a, b):
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=d.id, destino_tipo="entidad_vocabulario",
                        destino_id=mina.id, tipo_relacion="procedencia", codigo_ric="has_creator", origen="persona"))
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=c.id, destino_tipo="entidad_vocabulario",
                    destino_id=solo.id, tipo_relacion="espacial", codigo_ric="has_or_had_subject", origen="persona"))
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=b.id, destino_tipo="recurso_documental",
                    destino_id=c.id, tipo_relacion="asociacion", codigo_ric="is_record_resource_associated_with_record_resource", origen="persona"))
    db.commit()
    r = cliente.get("/api/grafo/documentos", headers=archivista, params={"fondo_id": str(fondo.id)})
    assert r.status_code == 200, r.text
    g = r.json()
    etiquetas = {n["etiqueta"] for n in g["nodos"]}
    assert {"Resolución 1919", "Resolución 1920", "Resolución 2001", "Ministerio de Ambiente y Desarrollo Sostenible"} <= etiquetas
    assert "Vereda única" in etiquetas  # la de un solo documento también entra, después de las compartidas
    claves = {n["clave"] for n in g["nodos"]}
    assert all(x["desde"] in claves and x["hacia"] in claves for x in g["aristas"])
    productor = [x for x in g["aristas"] if x["hacia"] == f"entidad_vocabulario:{mina.id}"]
    assert {x["desde"] for x in productor} == {f"recurso_documental:{a.id}", f"recurso_documental:{b.id}"}
    assert any(x["desde"] == f"recurso_documental:{b.id}" and x["hacia"] == f"recurso_documental:{c.id}" for x in g["aristas"])
    # La clasificación de cada documento en el cuadro también se ve (lo une a los de su misma serie).
    docs = {n["clave"] for n in g["nodos"] if n["clase"] in ("unidad_documental", "expediente")}
    assert all(x["hacia"] in docs for x in g["aristas"] if x["codigo_ric"] == "includes_or_included")
