"""
Guía de los metadatos de la descripción: cada campo dice qué es, por qué
importa y con qué se relaciona, con su elemento ISAD(G), su propiedad RiC-O y
su fila del Esquema de Metadatos del AGN.
"""

from app.servicios import atributos, guia_metadatos
from app.servicios.descripcion import TIPOS_ENTIDAD


def test_todo_campo_y_todo_tipo_de_entidad_tienen_su_explicacion():
    assert set(guia_metadatos.ATRIBUTOS) == {a.clave for a in atributos.ATRIBUTOS}
    assert set(guia_metadatos.ENTIDADES) == set(TIPOS_ENTIDAD)
    for g in list(guia_metadatos.ATRIBUTOS.values()) + list(guia_metadatos.ENTIDADES.values()):
        assert len(g.que_es) > 20 and len(g.por_que) > 20 and len(g.se_relaciona) > 15


def test_la_guia_une_cada_campo_con_sus_normas(cliente, cabeceras_admin):
    r = cliente.get("/api/descripcion/guia", headers=cabeceras_admin)
    assert r.status_code == 200
    por_clave = {a["clave"]: a for a in r.json()["atributos"]}
    titulo = por_clave["titulo"]
    assert titulo["isad"] == "3.1.2" and titulo["rico"] == "rico:title" and titulo["obligatorio"]
    assert {"AGN-REC-02", "AGN-FUID-02"} <= {f["id"] for f in titulo["agn"]}
    # Una fila del AGN cubre varios campos: volumen documental = folios, caja y carpeta.
    for clave in ("folios", "caja", "carpeta"):
        assert "AGN-FUID-10" in {f["id"] for f in por_clave[clave]["agn"]}, clave
    materia = next(e for e in r.json()["entidades"] if e["tipo"] == "materia")
    assert materia["rico"] == "rico:Concept" and "tesauro" in materia["que_es"]
