"""Contexto funcional del fondo y cifras RiC del panel institucional."""

from tests.test_brechas_lote4 import _reservar
from tests.test_busqueda_contexto import _funcion
from tests.test_grafo_contexto import consulta  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def test_funcion_con_su_actividad_y_sus_documentos(cliente, db, fondo_descrito, archivista):  # noqa: F811
    act, fun = _funcion(db, fondo_descrito)
    r = cliente.get(f"/api/fondos/{fondo_descrito['fondo'].id}/contexto-funcional", headers=archivista)
    assert r.status_code == 200, r.text
    d = r.json()
    [f] = [x for x in d["funciones"] if x["nombre"] == "Correspondencia oficial"]
    [a] = f["actividades"]
    assert a["nombre"] == "Informe de daños en el archivo" and a["documentos"]["total"] == 1
    assert a["documentos"]["ejemplos"][0]["titulo"] == "Oficio N.º 114" and f["documentos"]["total"] == 1
    assert d["totales"]["funciones"] >= 1 and d["actividades_sin_funcion"] == []


def test_consulta_no_ve_los_documentos_reservados(cliente, db, fondo_descrito, consulta):  # noqa: F811
    _funcion(db, fondo_descrito)
    _reservar(db, fondo_descrito, "recurso_documental", fondo_descrito["o114"].id)
    d = cliente.get(f"/api/fondos/{fondo_descrito['fondo'].id}/contexto-funcional", headers=consulta).json()
    [f] = [x for x in d["funciones"] if x["nombre"] == "Correspondencia oficial"]
    assert f["documentos"]["total"] == 0 and "Oficio N.º 114" not in str(d)


def test_cifras_ric_del_panel_institucional(cliente, db, fondo_descrito, archivista):  # noqa: F811
    _funcion(db, fondo_descrito)
    c = cliente.get(f"/api/fondos/{fondo_descrito['fondo'].id}/avance", headers=archivista).json()["conocimiento"]
    assert c["recursos"] >= 4 and c["agentes"] == 2 and c["funciones"] == 1 and c["actividades"] == 1
    assert c["lugares"] == 1 and c["relaciones"] > 0
    assert c["sin_evidencia"] == 0  # la única relación del motor trae su fragmento
