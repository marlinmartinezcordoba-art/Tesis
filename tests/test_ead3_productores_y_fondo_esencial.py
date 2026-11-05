"""
EAD3: cada productor con su elemento según su clase (persname, famname, corpname), sin partir
«Apellidos, Nombres». SHACL: el fondo sin los esenciales de ISAD(G) recibe advertencias, no violaciones.
"""

from lxml import etree

from app.servicios import conformidad_rico, exportacion_rico, intercambio
from tests.test_especializacion_ric import agente, relacion
from tests.test_preservacion import fondo  # noqa: F401  (fixture)

EAD = "{http://ead3.archivists.org/schema/}"


def test_productores_por_clase_sin_partir_el_nombre(db, fondo):  # noqa: F811
    relacion(db, fondo, agente(db, fondo, "Gómez Pérez, Pedro", "persona"), "has_creator")
    relacion(db, fondo, agente(db, fondo, "Alcaldía de Tunja", "entidad_corporativa"), "has_creator")
    db.commit()
    raiz = etree.fromstring(intercambio.ead3(db, fondo))
    origen = raiz.find(f".//{EAD}archdesc/{EAD}did/{EAD}origination")
    nombres = {(e.tag.replace(EAD, ""), e.findtext(f"{EAD}part")) for e in origen}
    assert ("persname", "Gómez Pérez, Pedro") in nombres and ("corpname", "Alcaldía de Tunja") in nombres


def test_fondo_sin_esenciales_da_advertencias_y_sigue_conforme(db, fondo):  # noqa: F811
    ex = exportacion_rico.exportar(db, fondo)
    r = conformidad_rico.validar_shacl(ex.grafo)
    advertencias = [x["mensaje"] for x in r["advertencias"]]
    assert r["conforme"] is True and r["resultados"] == []
    assert any("ISAD(G) 3.2.1" in m for m in advertencias)
