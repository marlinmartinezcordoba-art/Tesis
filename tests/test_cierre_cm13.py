"""
CM-13: un hito institucional (rico:Event) afecta a varios agentes o
descripciones y tiene su lugar; se exporta y no rompe el grafo.
"""

from rdflib import Namespace

from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, ric_o
from tests.test_autoridad import archivista, entidad, ficha, fondo  # noqa: F401

RICO = Namespace(ric_o.RICO)


def test_fusion_que_afecta_a_dos_entidades_con_su_lugar(cliente, db, fondo, archivista):
    concejo = entidad(db, fondo, "Concejo de Tunja")
    junta = entidad(db, fondo, "Junta de Obras")
    tunja = entidad(db, fondo, "Tunja", clase="lugar")
    db.commit()
    r = cliente.post(f"/api/vocabulario/{concejo.id}/hitos", headers=archivista, json={
        "tipo": "reforma", "descripcion": "Fusión del Concejo con la Junta de Obras", "edtf": "1952",
        "lugar_id": str(tunja.id), "afectados": [{"tipo": "entidad_vocabulario", "id": str(junta.id)}]})
    assert r.status_code == 201, r.text
    [h] = ficha(cliente, archivista, concejo)["ficha"]["hitos"]
    assert h["lugar"]["nombre"] == "Tunja" and [a["nombre"] for a in h["afectados"]] == ["Junta de Obras"]
    # Un lugar que no es lugar, o un afectado de otro fondo, se rechazan.
    assert cliente.post(f"/api/vocabulario/{concejo.id}/hitos", headers=archivista, json={
        "tipo": "otro", "descripcion": "x", "edtf": "1953", "lugar_id": str(junta.id)}).status_code == 422
    # El concejo produjo un documento publicado: así entra a la exportación.
    import uuid

    from app.db.base import ahora
    from app.models.descripcion import Relacion

    doc = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo="Acta de fusión", fondo_id=fondo.id,
                            incluido_en_id=fondo.id, publicado_en=ahora())
    db.add(doc)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=doc.id, destino_tipo="entidad_vocabulario",
                    destino_id=concejo.id, tipo_relacion="procedencia", codigo_ric="has_creator", origen="persona"))
    db.commit()
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    u = exportacion_rico.uri
    hito = u(h["id"])
    assert (hito, RICO.affectsOrAffected, u(concejo.id)) in g
    assert (u(tunja.id), RICO.isOrWasLocationOf, hito) in g
    # El grafo de contexto sigue funcionando con la fila que nace de un hito.
    grafo = cliente.get(f"/api/grafo/entidad_vocabulario/{junta.id}", headers=archivista)
    assert grafo.status_code == 200, grafo.text
    [evento] = [n for n in grafo.json()["nodos"] if n["familia"] == "Event"]
    assert evento["etiqueta"].startswith("Fusión del Concejo")


def test_verificar_una_actividad_advierte_que_es_un_ejercicio_concreto(cliente, db, fondo, archivista):
    """CM-14: dos ejercicios del mismo trámite no se deben fusionar por parecerse."""
    entidad(db, fondo, "Expedición de licencias de 1948", clase="actividad", subtipo=None)
    db.commit()
    r = cliente.post("/api/descripcion/verificar-vocabulario", headers=archivista,
                     json={"fondo_id": str(fondo.id), "tipo": "actividad", "valor": "Expedición de licencias de 1952"})
    assert r.status_code == 200, r.text
    assert r.json() and "ejercicio concreto" in r.json()[0]["aviso"]
    r = cliente.post("/api/descripcion/verificar-vocabulario", headers=archivista,
                     json={"fondo_id": str(fondo.id), "tipo": "agente", "valor": "Concejo de Tunja"})
    assert all(c["aviso"] is None for c in r.json())
