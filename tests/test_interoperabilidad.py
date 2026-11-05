"""
Prueba de interoperabilidad (app/servicios/interoperabilidad.py): lo público de un
fondo cumple RiC-O 1.1 y SHACL, se relee idéntico en cuatro formatos RDF, el
importador de RiC-O lo reconoce, y el EAD3 y el EAC-CPF validan contra la SAA.
"""

from app.models.auditoria import RegistroAuditoria
from sqlalchemy import select
from tests.test_especializacion_ric import agente, documento, relacion
from tests.test_preservacion import archivista, fondo  # noqa: F401  (fixtures)


def test_lo_publicado_lo_puede_leer_otro_sistema(cliente, db, fondo, archivista):  # noqa: F811
    doc = documento(db, fondo, "Oficio 301 de 1949")
    alcaldia = agente(db, fondo, "Alcaldía de Tunja", "entidad_corporativa")
    relacion(db, doc, alcaldia, "has_creator")
    db.commit()
    r = cliente.get("/api/exportacion/interoperabilidad", headers=archivista, params={"fondo_id": str(fondo.id)})
    assert r.status_code == 200, r.text
    inf = r.json()
    pruebas = {p["prueba"]: p for p in inf["pruebas"]}
    for nombre in ("Términos de RiC-O 1.1", "Perfil SHACL de RICORA", "Formatos de la web de datos",
                   "Reimportación en RiC-O", "EAD3 del fondo", "EAC-CPF de los agentes"):
        assert pruebas[nombre]["superada"], (nombre, pruebas[nombre]["detalle"])
    assert "cuatro formatos" in pruebas["Formatos de la web de datos"]["detalle"]
    # Sin enlaces externos todavía: la prueba lo dice y orienta a la búsqueda en Wikidata.
    assert not pruebas["Enlaces con la web de datos"]["superada"]
    assert "Wikidata" in pruebas["Enlaces con la web de datos"]["detalle"]
    assert inf["superadas"] == inf["total"] - 1 and "RecordSet" in inf["clases"]
    assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "interoperabilidad_probada")) is not None


def test_con_un_enlace_a_wikidata_la_prueba_de_enlaces_se_supera(cliente, db, fondo, archivista):  # noqa: F811
    doc = documento(db, fondo, "Oficio 302 de 1949")
    alcaldia = agente(db, fondo, "Alcaldía de Tunja", "entidad_corporativa")
    relacion(db, doc, alcaldia, "has_creator")
    db.commit()
    assert cliente.post(f"/api/vocabulario/{alcaldia.id}/identificadores", headers=archivista,
                        json={"esquema": "wikidata", "valor": "Q2841"}).status_code == 201
    inf = cliente.get("/api/exportacion/interoperabilidad", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    enlaces = next(p for p in inf["pruebas"] if p["prueba"] == "Enlaces con la web de datos")
    assert enlaces["superada"] and "wikidata 1" in enlaces["detalle"]
