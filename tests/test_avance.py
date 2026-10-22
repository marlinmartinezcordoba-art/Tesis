"""Avance del fondo para el Inicio: cada paso con su estado y la siguiente acción."""

from tests.test_disposicion import _fondo
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401  (fixtures)


def test_un_fondo_con_trd_y_descripciones_dice_que_sigue(cliente, fondo_descrito, archivista):  # noqa: F811
    r = cliente.get(f"/api/fondos/{fondo_descrito['fondo'].id}/avance", headers=archivista)
    assert r.status_code == 200, r.text
    a = r.json()
    pasos = {p["clave"]: p for p in a["pasos"]}
    assert list(pasos) == ["instrumentos", "carga", "descripcion", "autoridades", "difusion", "preservacion"]
    # Sin TRD: lo primero que se recomienda es cargarla.
    assert pasos["instrumentos"]["estado"] == "pendiente" and a["siguiente"] == "instrumentos"
    assert pasos["descripcion"]["estado"] == "hecho" and "publicadas" in pasos["descripcion"]["resumen"]
    assert pasos["difusion"]["estado"] == "en_curso" and "inventario" in pasos["difusion"]["resumen"]


def test_con_trd_vigente_el_paso_queda_hecho(cliente, db, cabeceras_admin):
    fnd, _, _ = _fondo(cliente, db, cabeceras_admin)
    a = cliente.get(f"/api/fondos/{fnd.id}/avance", headers=cabeceras_admin).json()
    paso = a["pasos"][0]
    assert paso["estado"] == "hecho" and "vigente" in paso["resumen"] and paso["ruta"] == "/fondos?vista=versiones"
