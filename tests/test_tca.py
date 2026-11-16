"""Tablas de Control de Acceso: la condición de cada serie se hereda a sus documentos."""

from datetime import date, timedelta

from tests.test_grafo_contexto import consulta  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def test_reserva_de_la_serie_rige_a_sus_documentos(cliente, db, fondo_descrito, cabeceras_admin, archivista, consulta):  # noqa: F811
    f = fondo_descrito
    url = f"/api/fondos/{f['fondo'].id}/tca"
    hasta = (date.today() + timedelta(days=365 * 5)).isoformat()
    r = cliente.put(f"{url}/{f['serie'].id}", headers=cabeceras_admin, json={
        "acceso": "reservado", "fundamento": "Ley 1712 de 2014, art. 19", "vigente_hasta": hasta,
        "condiciones": "Solo con autorización escrita", "responsable": "Secretaría General", "reproduccion": "no_permitida"})
    assert r.status_code == 200, r.text
    [fila] = [s for s in r.json()["series"] if s["id"] == str(f["serie"].id)]
    assert fila["propia"]["acceso"] == "reservado" and fila["propia"]["responsable"] == "Secretaría General"
    assert fila["documentos"] >= 3 and r.json()["totales"]["restringidas"] >= 1
    # La reserva heredada saca sus documentos de la búsqueda del rol de consulta.
    assert cliente.get("/api/buscar", headers=consulta, params={"q": "oficio"}).json()["total"] == 0
    assert cliente.get("/api/buscar", headers=archivista, params={"q": "oficio"}).json()["total"] >= 1


def test_reglas_de_la_ley_1712(cliente, fondo_descrito, cabeceras_admin, archivista):  # noqa: F811
    f = fondo_descrito
    url = f"/api/fondos/{f['fondo'].id}/tca/{f['serie'].id}"
    sin_fecha = {"acceso": "clasificado", "fundamento": "Ley 1712 de 2014, art. 18"}
    assert cliente.put(url, headers=cabeceras_admin, json=sin_fecha).status_code == 422
    largo = sin_fecha | {"vigente_hasta": (date.today() + timedelta(days=365 * 16)).isoformat()}
    r = cliente.put(url, headers=cabeceras_admin, json=largo)
    assert r.status_code == 422 and "15 años" in r.text
    assert cliente.put(url, headers=archivista, json={"acceso": "publico", "fundamento": "Ley 1712"}).status_code == 403
    doc = f"/api/fondos/{f['fondo'].id}/tca/{f['o114'].id}"
    assert cliente.put(doc, headers=cabeceras_admin, json={"acceso": "publico", "fundamento": "Ley 1712 de 2014"}).status_code == 422
