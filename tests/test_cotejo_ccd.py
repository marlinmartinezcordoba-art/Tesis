"""
Fase C: cotejo del cuadro de clasificación (CCD) con la TRD (requisito 4).

- Se compara por código compuesto: series y subseries del CCD sin retención
  en la TRD, las de la TRD que el CCD no tiene, el mismo código con otro
  nombre, la misma serie en otra dependencia y las dependencias.
- El archivo del CCD se guarda con su huella, marcado como CCD, con su informe.
- Si algo no coincide hay alerta (alta si hay series sin retención); un
  cotejo posterior sin diferencias la atiende sola.
"""

from sqlalchemy import select

from app.models.alerta import Alerta
from tests.test_descripcion import fondo  # noqa: F401
from tests.test_parametrizacion_trd import _armar

ENCABEZADO = "Código sección;Sección (dependencia);Código subsección;Subsección;Código serie;Serie;Código subserie;Subserie"


def _ccd(*filas):
    return ("\n".join([ENCABEZADO, *filas]) + "\n").encode("utf-8")


def _leer(cliente, cab, contenido, nombre="ccd.csv"):
    r = cliente.post("/api/cuadro/vista-previa", headers=cab, files={"archivo": (nombre, contenido)})
    assert r.status_code == 200, r.text
    return r.json()


def test_cotejar_el_ccd_con_la_trd(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab = cabeceras_admin
    v = _armar(cliente, cab, fondo)["version"]["id"]
    vista = _leer(cliente, cab, _ccd(
        "100;Secretaría General;110;Archivo;2;Actas;1;Actas del comité de archivo",
        "100;Secretaría General;110;Archivo;5;Contratos;;",
        "100;Secretaría General;120;Tesorería;8;Nóminas;;"))
    r = cliente.post(f"/api/trd/versiones/{v}/cotejo", headers=cab,
                     json={"filas": vista["filas"], "original": {**{k: vista["original"][k] for k in ("huella", "archivo")}}})
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["coinciden"] == 2  # la serie 110.2 y la subserie 110.2.1
    assert {x["codigo"] for x in c["sin_retencion"]} == {"110.5", "120.8"}
    assert c["dependencias"]["solo_en_ccd"] == [{"codigo": "120", "nombre": "Tesorería"}]
    assert c["nombre_distinto"] == []  # mayúsculas y tildes no cuentan
    assert c["archivo"]["archivo"] == "ccd.csv" and c["diferencias"] == 3
    alerta = db.scalar(select(Alerta).where(Alerta.tipo == "ccd_trd_no_coinciden"))
    assert alerta.severidad == "alta" and "2 serie(s) o subserie(s) del CCD sin retención" in alerta.mensaje
    # Queda guardado como CCD de la versión, aparte de los archivos de la TRD.
    assert [x["clase"] for x in cliente.get(f"/api/trd/versiones/{v}/cargas", headers=cab, params={"clase": "ccd"}).json()] == ["ccd"]
    assert cliente.get(f"/api/trd/versiones/{v}/cargas", headers=cab, params={"clase": "trd"}).json() == []
    assert cliente.get(f"/api/trd/versiones/{v}/cotejo", headers=cab).json()["diferencias"] == 3

    # Otro nombre y otra dependencia.
    vista = _leer(cliente, cab, _ccd("100;Secretaría General;130;Jurídica;2;Actas;1;Actas del Comité de Conciliación"), "ccd2.csv")
    c = cliente.post(f"/api/trd/versiones/{v}/cotejo", headers=cab, json={"filas": vista["filas"]}).json()
    assert {x["codigo"] for x in c["sin_retencion"]} == {"130.2", "130.2.1"}
    assert {x["codigo"] for x in c["solo_en_trd"]} == {"110.2", "110.2.1"}

    # El mismo CCD que la TRD: sin diferencias, y la alerta se atiende sola.
    vista = _leer(cliente, cab, _ccd("100;Secretaría General;110;Archivo;2;Actas;1;Actas del Comité de Archivo"), "ccd3.csv")
    c = cliente.post(f"/api/trd/versiones/{v}/cotejo", headers=cab,
                     json={"filas": vista["filas"], "original": {k: vista["original"][k] for k in ("huella", "archivo")}}).json()
    assert c["diferencias"] == 0 and c["coinciden"] == 2
    db.expire_all()
    assert db.scalar(select(Alerta).where(Alerta.tipo == "ccd_trd_no_coinciden")).atendida_en is not None
    # Volver a cotejar el último CCD guardado (después de corregir la TRD) da lo mismo.
    assert cliente.post(f"/api/trd/versiones/{v}/cotejo/repetir", headers=cab).json()["diferencias"] == 0


def test_un_archivo_sin_series_no_se_coteja(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    v = _armar(cliente, cabeceras_admin, fondo)["version"]["id"]
    r = cliente.post(f"/api/trd/versiones/{v}/cotejo", headers=cabeceras_admin, json={"filas": [{"fila": 1}]})
    assert r.status_code == 422 and "no trae series" in r.json()["detail"]
    assert cliente.post(f"/api/trd/versiones/{v}/cotejo/repetir", headers=cabeceras_admin).status_code == 404


def test_un_paquete_con_ccd_trd_y_tvd(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    """Requisito 3: un .zip con varios instrumentos; el sistema dice qué parece cada archivo y cada uno va a su lugar."""
    import io
    import zipfile

    cab = cabeceras_admin
    con_retencion = ENCABEZADO + ";Tipos documentales;Retención AG (años);Retención AC (años);CT;E;S;M"
    trd = "\n".join([con_retencion, "100;Secretaría General;110;Archivo;2;Actas;1;Actas del Comité;Acta;2;8;X;;;"]) + "\n"
    tvd = "\n".join([con_retencion, "100;Secretaría General;110;Archivo;9;Informes;;;Informe;;10;;;X;"]) + "\n"
    ccd = _ccd("100;Secretaría General;110;Archivo;2;Actas;1;Actas del Comité", "100;Secretaría General;110;Archivo;5;Contratos;;")
    paquete = io.BytesIO()
    with zipfile.ZipFile(paquete, "w") as z:
        z.writestr("instrumentos/TRD 2024.csv", trd)
        z.writestr("instrumentos/Cuadro de clasificación.csv", ccd)
        z.writestr("instrumentos/TVD 1990-1995.csv", tvd)
    vista = _leer(cliente, cab, paquete.getvalue(), "minambiente.zip")
    sugeridos = {p["archivo"]: p["sugerido"] for p in vista["partes"]}
    assert sugeridos == {"TRD 2024.csv": "trd", "Cuadro de clasificación.csv": "ccd", "TVD 1990-1995.csv": "tvd"}
    de = lambda archivo: [f for f in vista["filas"] if f["parte"] == archivo]  # noqa: E731
    original = {k: vista["original"][k] for k in ("huella", "archivo")}

    trd_r = cliente.post("/api/trd/cargar", headers=cab, json={"fondo_id": str(fondo.id), "filas": de("TRD 2024.csv"),
                                                              "original": original}).json()
    tvd_r = cliente.post("/api/trd/cargar", headers=cab, json={"fondo_id": str(fondo.id), "instrumento": "tvd",
                                                              "filas": de("TVD 1990-1995.csv"), "original": original}).json()
    assert trd_r["version"]["instrumento"] == "trd" and tvd_r["version"]["instrumento"] == "tvd"
    c = cliente.post(f"/api/trd/versiones/{trd_r['version']['id']}/cotejo", headers=cab,
                     json={"filas": de("Cuadro de clasificación.csv"), "original": original}).json()
    assert [x["codigo"] for x in c["sin_retencion"]] == ["110.5"]
    # El mismo archivo .zip queda citado por las dos versiones y por el cotejo, con una sola copia guardada.
    matriz = cliente.get(f"/api/trd/versiones/{trd_r['version']['id']}/filas", headers=cab).json()
    assert matriz[0]["procedencia"]["parte"] == "TRD 2024.csv"
