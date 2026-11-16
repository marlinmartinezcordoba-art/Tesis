"""Estado de la descripción por componentes RiC (no por áreas de ISAD(G)): qué tiene y qué falta en
recurso, agentes, funciones y actividades, relaciones, tiempo y lugar, custodia y manifestaciones, y
fuentes y validación."""

from tests.test_busqueda_contexto import _funcion
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def _estado(cliente, quien, recurso):
    r = cliente.get(f"/api/descripcion/registros/{recurso.id}/componentes-ric", headers=quien)
    assert r.status_code == 200, r.text
    datos = r.json()
    return datos, {c["clave"]: c for c in datos["componentes"]}


def test_siete_componentes_con_lo_que_tiene_y_lo_que_falta(cliente, db, fondo_descrito, archivista):  # noqa: F811
    o114 = fondo_descrito["o114"]
    datos, c = _estado(cliente, archivista, o114)
    assert [x["clave"] for x in datos["componentes"]] == [
        "recurso", "agentes", "funciones", "relaciones", "tiempo_lugar", "custodia", "fuentes"]
    assert c["agentes"]["estado"] == "completo" and any("Alcaldía Municipal" in t for t in c["agentes"]["tiene"])
    assert c["funciones"]["estado"] == "por_completar"
    # La relación con Boyacá la propuso el motor con su fragmento: tiene evidencia.
    assert "con evidencia" in c["fuentes"]["tiene"][0]


def test_la_funcion_completa_el_contexto_funcional(cliente, db, fondo_descrito, archivista):  # noqa: F811
    _funcion(db, fondo_descrito)
    _, c = _estado(cliente, archivista, fondo_descrito["o114"])
    assert c["funciones"]["estado"] == "completo"
    assert c["funciones"]["tiene"] == ["Informe de daños en el archivo → función: Correspondencia oficial"]


def test_sin_sesion_no_se_consulta(cliente, fondo_descrito):  # noqa: F811
    assert cliente.get(f"/api/descripcion/registros/{fondo_descrito['o114'].id}/componentes-ric").status_code == 401
