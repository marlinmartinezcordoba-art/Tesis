"""Tablas de Control de Acceso: la condición de cada serie se hereda a sus documentos."""

import uuid
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


def test_importar_la_tca_existente(cliente, db, fondo_descrito, cabeceras_admin, archivista):  # noqa: F811
    f = fondo_descrito
    serie = f["serie"]
    if not serie.codigo_referencia:
        serie.codigo_referencia = "100.2"
        db.commit()
    codigo = serie.codigo_referencia
    csv = ("Código;Serie;Categoría de acceso;Fundamento legal;Plazo de la reserva;Responsable\n"
           f"{codigo};{serie.titulo};Información pública reservada;Ley 1712 de 2014, art. 19;5 años;Secretaría General\n"
           "999.9;Serie que no existe;Pública;Ley 1712 de 2014;;\n"
           f"{codigo};{serie.titulo};Clasificada;;3 años;\n").encode("utf-8")
    url = f"/api/fondos/{f['fondo'].id}/tca"
    archivo = {"archivo": ("tca.csv", csv, "text/csv")}
    assert cliente.post(f"{url}/vista-previa", headers=archivista, files=archivo).status_code == 403
    r = cliente.post(f"{url}/vista-previa", headers=cabeceras_admin, files=archivo)
    assert r.status_code == 200, r.text
    previa = r.json()
    assert previa["validas"] == 1 and previa["con_problemas"] == 2
    buena, otra, sin_fundamento = previa["filas"]
    assert buena["acceso"] == "reservado" and buena["vigente_hasta"] and buena["responsable"] == "Secretaría General"
    assert "no es una serie" in otra["problemas"][0] and any("fundamento" in p for p in sin_fundamento["problemas"])
    r = cliente.post(f"{url}/aplicar", headers=cabeceras_admin, files=archivo)
    assert r.status_code == 200 and r.json()["aplicadas"] == 1
    [fila] = [s for s in cliente.get(url, headers=archivista).json()["series"] if s["id"] == str(serie.id)]
    assert fila["propia"]["acceso"] == "reservado"


def test_lo_que_hereda_quien_se_clasifica_en_la_serie(cliente, fondo_descrito, cabeceras_admin, archivista):  # noqa: F811
    f = fondo_descrito
    url = "/api/descripcion/acceso-que-rige"
    antes = cliente.get(url, headers=archivista, params={"recurso_id": str(f["serie"].id)})
    assert antes.status_code == 200, antes.text
    assert antes.json()["acceso"] is None
    r = cliente.put(f"/api/fondos/{f['fondo'].id}/tca/{f['serie'].id}", headers=cabeceras_admin, json={
        "acceso": "clasificado", "fundamento": "Ley 1712 de 2014, art. 18", "reproduccion": "condicionada",
        "vigente_hasta": (date.today() + timedelta(days=365)).isoformat()})
    assert r.status_code == 200, r.text
    rige = cliente.get(url, headers=archivista, params={"recurso_id": str(f["serie"].id)}).json()
    assert rige["acceso"] == "clasificado" and rige["fundamento"] == "Ley 1712 de 2014, art. 18"
    assert rige["de"] == f["serie"].titulo and rige["serie"] == f["serie"].titulo
    assert isinstance(rige["tipos_documentales"], list)
    assert cliente.get(url, headers=archivista, params={"recurso_id": str(uuid.uuid4())}).status_code == 404
