"""
Ficha ISDIAH de la institución que custodia los fondos.

- Una entidad corporativa guarda su contacto, acceso y servicios (ISDIAH
  5.2, 5.4 y 5.5); lo demás (identidad, historia, estructura, control) es la
  ficha ISAAR que ya tiene. Una persona no lleva ficha ISDIAH.
- La custodia de cada fondo es un vínculo (ISDIAH 5.3.7) que sale en RiC-O
  como rico:hasOrHadHolder; el contacto no sale en el grafo (RiC-O no tiene
  dónde ponerlo) y queda en la ficha.
"""

from rdflib import URIRef

from app.servicios import exportacion_rico
from tests.test_autoridad import vincular
from tests.test_descripcion import archivista, fondo  # noqa: F401
from tests.test_vocabularios import entidad


def test_ficha_isdiah_y_custodia_del_fondo(cliente, db, fondo, archivista):  # noqa: F811
    agn = entidad(db, fondo, "Archivo General de la Nación")
    r = cliente.patch(f"/api/vocabulario/{agn.id}", headers=archivista, json={"isdiah": {
        "direccion": "Carrera 6 # 6-91, Bogotá", "correo": "contacto@archivogeneral.gov.co",
        "sitio_web": "https://www.archivogeneral.gov.co", "horarios": "Lunes a viernes, 8:00 a 16:00"}})
    assert r.status_code == 200, r.text
    ficha = cliente.get(f"/api/vocabulario/{agn.id}", headers=archivista).json()
    assert ficha["ficha"]["campos"]["isdiah"]["horarios"] == "Lunes a viernes, 8:00 a 16:00"
    # Un campo vacío lo quita; los demás quedan.
    cliente.patch(f"/api/vocabulario/{agn.id}", headers=archivista, json={"isdiah": {"horarios": ""}})
    campos = cliente.get(f"/api/vocabulario/{agn.id}", headers=archivista).json()["ficha"]["campos"]["isdiah"]
    assert "horarios" not in campos and campos["correo"] == "contacto@archivogeneral.gov.co"

    # Validaciones: correo, sitio web, campos desconocidos y quién lleva ficha ISDIAH.
    for malo in ({"correo": "sin-arroba"}, {"sitio_web": "archivogeneral.gov.co"}, {"telefax": "1"}):
        assert cliente.patch(f"/api/vocabulario/{agn.id}", headers=archivista, json={"isdiah": malo}).status_code == 422
    persona = entidad(db, fondo, "Ana Pérez", subtipo="persona")
    assert cliente.patch(f"/api/vocabulario/{persona.id}", headers=archivista,
                         json={"isdiah": {"horarios": "x"}}).status_code == 422

    # La institución custodia el fondo: sale en RiC-O como hasOrHadHolder; el contacto no.
    r = vincular(cliente, archivista, agn, "custodia_fondo", fondo, con_tipo="recurso_documental", fecha_edtf="1989")
    assert r.status_code == 201, r.text
    ficha = cliente.get(f"/api/vocabulario/{agn.id}", headers=archivista).json()["ficha"]
    assert any(v["vinculo"] == "custodia_fondo" for v in ficha["vinculos"])
    g = exportacion_rico.exportar(db, fondo).grafo
    rico = "https://www.ica.org/standards/RiC/ontology#"
    base = exportacion_rico.base()
    assert (URIRef(base + str(fondo.id)), URIRef(rico + "hasOrHadHolder"), URIRef(base + str(agn.id))) in g
    assert "archivogeneral" not in g.serialize(format="nt")
