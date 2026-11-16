"""Devolver una descripción publicada para redescribirla: solo la administración,
sin despublicar ni cambiar el identificador; la corrección levanta la marca."""

import uuid

from app.models.recurso_documental import RecursoDocumental
from tests.test_descripcion import archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_v3 import TEXTO, publicar, sin_motor  # noqa: F401


def _publicada(cliente, db, fondo, archivista):  # noqa: F811
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "dev.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, titulo="Oficio para devolver")
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_solo_la_administracion_devuelve_y_la_correccion_la_levanta(cliente, db, fondo, archivista, cabeceras_admin,  # noqa: F811
                                                                    sin_motor):  # noqa: F811
    rid = _publicada(cliente, db, fondo, archivista)
    url = f"/api/descripcion/registros/{rid}/devolver"
    assert cliente.post(url, headers=archivista, json={"motivo": "Cambió la TRD"}).status_code == 403
    assert cliente.post(url, headers=cabeceras_admin, json={"motivo": "x"}).status_code == 422
    r = cliente.post(url, headers=cabeceras_admin, json={"motivo": "Se ajustó la TCA y la TRD"})
    assert r.status_code == 200, r.text
    lista = cliente.get("/api/descripcion/devueltas", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert [d["id"] for d in lista] == [rid] and lista[0]["motivo"] == "Se ajustó la TCA y la TRD"
    # Sigue publicada con el mismo identificador.
    recurso = db.get(RecursoDocumental, uuid.UUID(rid))
    db.refresh(recurso)
    assert recurso.publicado_en is not None
    detalle = cliente.get(f"/api/descripcion/registros/{rid}", headers=archivista).json()
    assert detalle["devuelta"]["motivo"] == "Se ajustó la TCA y la TRD"
    # La persona la reabre, pide la propuesta nueva y guarda la corrección.
    trabajo = cliente.post(f"/api/descripcion/registros/{rid}/reabrir", headers=archivista).json()["trabajo_id"]
    p = cliente.post(f"/api/descripcion/registros/{rid}/propuesta", headers=archivista, params={"trabajo_id": trabajo})
    assert p.status_code == 200, p.text
    assert p.json()["aviso"]  # sin motor configurado lo dice; no inventa
    g = cliente.patch(f"/api/descripcion/{rid}", headers=archivista, json={"trabajo_id": trabajo, "titulo": "Oficio redescrito"})
    assert g.status_code == 200, g.text
    assert g.json()["devuelta"] is None
    assert cliente.get("/api/descripcion/devueltas", headers=archivista, params={"fondo_id": str(fondo.id)}).json() == []
