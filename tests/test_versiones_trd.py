"""
Fase B: versiones de la TRD (requisitos 3 y 7).

- El archivo leído se guarda tal como llegó, por su huella; la carga lo cita y
  cada fila de la matriz dice de qué archivo y de qué fila salió.
- Comparar el borrador con la vigente dice qué series se agregan, se retiran y
  qué cambió en cada una, y qué registros afecta: los cerrados antes de que rija
  la nueva conservan la anterior; los abiertos pasan a la nueva.
- Cada descripción guarda la versión de la TRD que regía cuando se clasificó.
"""

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.recurso_documental import RecursoDocumental
from tests.archivos import trd_agn_pdf
from tests.test_descripcion import (OFICIO_114, aceptar_todo, archivista, documento, fondo, iniciar,  # noqa: F401
                                    motor_prueba)
from tests.test_parametrizacion_trd import _armar, _post


def _vigente_y_borrador(cliente, db, fondo, cab):  # noqa: F811
    a = _armar(cliente, cab, fondo)
    v1 = a["version"]["id"]
    cliente.patch(f"/api/trd/versiones/{v1}", headers=cab, json={
        "acto_aprobacion": "Resolución 045", "fecha_aprobacion": "2019-02-15", "vigente_desde": "2019-03-01"})
    _post(cliente, cab, f"/api/trd/versiones/{v1}/aplicar", None, 200)
    v2 = _post(cliente, cab, "/api/trd/versiones", {"fondo_id": str(fondo.id), "acto_aprobacion": "Resolución 210",
                                                   "fecha_aprobacion": "2024-06-01", "vigente_desde": "2024-07-01"})
    return a, v1, v2


def test_comparar_la_nueva_con_la_vigente_y_ver_a_quien_afecta(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab = cabeceras_admin
    a, v1, v2 = _vigente_y_borrador(cliente, db, fondo, cab)
    sub = db.scalar(select(RecursoDocumental).where(RecursoDocumental.codigo_referencia == "110.2.1"))
    ahora = datetime.now(timezone.utc)
    for titulo, fechas in (("Actas 2020", "2020-01-10/2021-11-30"), ("Actas abiertas", "2024-02-01/..")):
        db.add(RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo=titulo, fondo_id=fondo.id,
                                 incluido_en_id=sub.id, fechas_extremas_edtf=fechas, publicado_en=ahora))
    db.commit()
    # Sin cambios todavía: la versión 2 parte de la vigente.
    r = cliente.get(f"/api/trd/versiones/{v2['id']}/comparar", headers=cab).json()
    assert r["comparable"] and r["cambiadas"] == [] and r["sin_cambio"] == 1 and r["afectados"]["total"] == 0

    fila = cliente.get(f"/api/trd/versiones/{v2['id']}/filas", headers=cab).json()[0]
    cliente.put(f"/api/trd/filas/{fila['id']}", headers=cab, json={
        "dependencia_id": fila["dependencia_id"], "serie_id": fila["serie_id"], "subserie_id": fila["subserie_id"],
        "tipos": fila["tipos"][:1], "gestion": 2, "central": 12, "disposicion": "s"})
    r = cliente.get(f"/api/trd/versiones/{v2['id']}/comparar", headers=cab).json()
    assert r["anterior"]["id"] == v1 and len(r["cambiadas"]) == 1
    cambios = {d["campo"]: d for d in r["cambiadas"][0]["diferencias"]}
    assert (cambios["central"]["antes"], cambios["central"]["despues"]) == (8, 12)
    assert cambios["disposicion"]["despues"] == "Selección" and cambios["nombres_tipos"]["quitados"] == ["Acta"]
    af = r["afectados"]
    assert af["total"] == 2 and af["pasan_a_la_nueva"] == 1 and af["conservan_la_anterior"] == 1
    rige = {x["titulo"]: x["rige"] for x in af["series"][0]["registros"]}
    assert rige == {"Actas abiertas": "nueva", "Actas 2020": "anterior"}
    # Versiones de otro fondo no se comparan.
    assert cliente.get(f"/api/trd/versiones/{v2['id']}/comparar", headers=cab,
                       params={"con": str(uuid.uuid4())}).status_code == 404


def test_el_archivo_original_y_la_procedencia_de_cada_fila(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab = cabeceras_admin
    contenido = trd_agn_pdf()
    vista = cliente.post("/api/cuadro/vista-previa", headers=cab, files={"archivo": ("trd-2024.pdf", contenido)}).json()
    original = vista["original"]
    assert original["huella"] == hashlib.sha256(contenido).hexdigest() and original["archivo"] == "trd-2024.pdf"
    r = _post(cliente, cab, "/api/trd/cargar", {"fondo_id": str(fondo.id), "filas": vista["filas"],
                                                 "original": {**{k: original[k] for k in ("huella", "archivo")},
                                                              "origen": vista["origen"]}}, 200)
    version = r["version"]["id"]
    assert r["parametrizacion"]["archivo_original"]["huella"] == original["huella"]
    [carga] = cliente.get(f"/api/trd/versiones/{version}/cargas", headers=cab).json()
    assert carga["filas_cargadas"] == 3 and carga["huella"] == original["huella"]
    matriz = cliente.get(f"/api/trd/versiones/{version}/filas", headers=cab).json()
    assert all(m["procedencia"]["carga"] == carga["id"] and m["procedencia"]["fila"] for m in matriz)
    descarga = cliente.get(f"/api/trd/cargas/{carga['id']}/archivo", headers=cab)
    assert descarga.status_code == 200 and hashlib.sha256(descarga.content).hexdigest() == original["huella"]
    # Una huella que no corresponde a un archivo guardado no se cita.
    otro = _post(cliente, cab, "/api/trd/cargar", {"fondo_id": str(fondo.id), "filas": vista["filas"],
                                                    "original": {"huella": "0" * 64, "archivo": "falso.pdf"}}, 200)
    assert "archivo_original" not in otro["parametrizacion"]


def test_cada_descripcion_guarda_con_que_trd_se_clasifico(cliente, db, fondo, cabeceras_admin, archivista,  # noqa: F811
                                                          motor_prueba):
    a = _armar(cliente, cabeceras_admin, fondo)
    v1 = a["version"]["id"]
    cliente.patch(f"/api/trd/versiones/{v1}", headers=cabeceras_admin, json={
        "acto_aprobacion": "Resolución 045", "fecha_aprobacion": "2019-02-15", "vigente_desde": "2019-03-01"})
    _post(cliente, cabeceras_admin, f"/api/trd/versiones/{v1}/aplicar", None, 200)
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    sub = db.scalar(select(RecursoDocumental).where(RecursoDocumental.codigo_referencia == "110.2.1"))
    datos = aceptar_todo(iniciar(cliente, archivista, [d.id]))
    datos["incluido_en_id"] = str(sub.id)
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 201, r.text
    assert r.json()["clasificado_con"]["id"] == v1 and r.json()["clasificado_con"]["acto"] == "Resolución 045"
