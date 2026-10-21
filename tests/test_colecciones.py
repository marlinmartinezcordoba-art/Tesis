"""
Pertenencia múltiple y colecciones (RiC: un documento en varios conjuntos).

- La colección es un rico:RecordSet de tipo rst:Collection; va en el fondo o
  en otra colección, nunca dentro del cuadro orgánico.
- Un expediente sigue en su serie (orgánica) y además entra a la colección
  (pertenencia adicional); la exportación dice las dos inclusiones.
- La pertenencia adicional se quita (queda anulada, con constancia).
- El grafo de control sigue reconstruyendo exacto con varios conjuntos.
"""

from rdflib import Namespace
from sqlalchemy import select

from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import Relacion
from app.servicios import exportacion_rico, grafo_rdf
from tests.test_cierre_cm02 import crear
from tests.test_descripcion import archivista, fondo  # noqa: F401

RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")
RST = Namespace("https://www.ica.org/standards/RiC/vocabularies/recordSetTypes#")


def test_coleccion_y_pertenencia_adicional(cliente, db, fondo, archivista):  # noqa: F811
    serie = crear(cliente, archivista, fondo, "serie", "Correspondencia").json()
    exp = crear(cliente, archivista, fondo, "expediente", "Oficios de 1948", serie["id"]).json()
    col = crear(cliente, archivista, fondo, "coleccion", "Documentos sobre el ferrocarril")
    assert col.status_code in (200, 201), col.text
    col = col.json()
    # Una colección no entra en el cuadro orgánico, ni un expediente se pone «dentro» de ella orgánicamente.
    assert crear(cliente, archivista, fondo, "coleccion", "Mal ubicada", serie["id"]).status_code == 422
    assert crear(cliente, archivista, fondo, "expediente", "Mal ubicado", col["id"]).status_code == 422
    sub = crear(cliente, archivista, fondo, "coleccion", "Planos del ferrocarril", col["id"])
    assert sub.status_code in (200, 201), sub.text
    # Pertenencia adicional: el expediente sigue en su serie y además está en la colección.
    r = cliente.post(f"/api/descripcion/registros/{exp['id']}/inclusiones", headers=archivista,
                     json={"conjunto_id": col["id"]})
    assert r.status_code == 201, r.text
    d = r.json()
    assert [x["id"] for x in d["tambien_en"]] == [col["id"]]
    relacion_id = d["tambien_en"][0]["relacion_id"]
    detalle_col = cliente.get(f"/api/descripcion/registros/{col['id']}", headers=archivista)
    assert detalle_col.status_code == 200, detalle_col.text
    assert [x["id"] for x in detalle_col.json()["miembros_adicionales"]] == [exp["id"]]
    # RiC-O: la colección es rst:Collection e incluye al expediente; la serie, también.
    db.commit()
    g = exportacion_rico.exportar(db, fondo, incluir_restringidos=True).grafo
    u = exportacion_rico.uri
    assert (u(col["id"]), RICO.hasRecordSetType, RST.Collection) in g
    assert (u(col["id"]), RICO.includesOrIncluded, u(exp["id"])) in g
    assert (u(serie["id"]), RICO.includesOrIncluded, u(exp["id"])) in g
    # El grafo como fuente de verdad sigue exacto con dos conjuntos.
    for alcance in grafo_rdf.ALCANCES:
        grafo_rdf.sincronizar(db, fondo, alcance)
    assert grafo_rdf.comparar(db, fondo.id) == []
    # Quitarla: queda anulada (no se borra) y en la auditoría; la orgánica no se toca.
    r = cliente.post(f"/api/descripcion/registros/{exp['id']}/inclusiones/{relacion_id}/anular", headers=archivista)
    assert r.status_code == 200 and r.json()["tambien_en"] == []
    assert db.get(Relacion, __import__("uuid").UUID(relacion_id)).estado == "anulada"
    assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "inclusion_adicional_anulada"))
    organica = db.scalar(select(Relacion).where(Relacion.destino_id == __import__("uuid").UUID(exp["id"]),
                                                Relacion.codigo_ric == "includes_or_included", Relacion.rol.is_(None),
                                                Relacion.estado == "vigente"))
    assert organica is not None and str(organica.origen_id) == serie["id"]
    # No se puede quitar la orgánica por este camino.
    assert cliente.post(f"/api/descripcion/registros/{exp['id']}/inclusiones/{organica.id}/anular",
                        headers=archivista).status_code == 404


def test_la_coleccion_no_se_ofrece_como_lugar_organico(cliente, db, fondo, archivista):  # noqa: F811
    crear(cliente, archivista, fondo, "coleccion", "Colección de planos")
    p = {"fondo_id": str(fondo.id), "nivel": "expediente"}
    organicos = cliente.get("/api/descripcion/niveles-superiores", headers=archivista, params=p).json()
    assert "coleccion" not in {o["nivel"] for o in organicos}
    adicionales = cliente.get("/api/descripcion/niveles-superiores", headers=archivista,
                              params=p | {"adicional": "true"}).json()
    assert "coleccion" in {o["nivel"] for o in adicionales}
