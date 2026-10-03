"""
Clasificación del acceso (Ley 1712 de 2014) al describir: la archivista
dice si la descripción es pública, clasificada o reservada en el mismo
formulario. Se guarda como la declaración de derechos del Record Resource
(la que gobierna el catálogo, la guía, los datos abiertos y el DIP) y se
puede cambiar al corregir la descripción, sin borrar la anterior.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.models.preservacion import DeclaracionDerechos
from app.servicios import derechos
from tests.test_descripcion import archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_v3 import TEXTO, publicar, sin_motor  # noqa: F401


def abrir(cliente, db, fondo, archivista):
    return iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])


def declaraciones(db, recurso_id):
    return db.scalars(select(DeclaracionDerechos).where(DeclaracionDerechos.entidad_id == recurso_id)
                      .order_by(DeclaracionDerechos.creada_en)).all()


def test_publicar_como_reservada_crea_la_declaracion(cliente, db, fondo, archivista, sin_motor):
    hasta = (date.today() + timedelta(days=365 * 5)).isoformat()
    r = publicar(cliente, archivista, abrir(cliente, db, fondo, archivista), clasificacion={
        "acceso": "reservado", "fundamento": "Ley 1712 de 2014, art. 19, literal f", "vigente_hasta": hasta,
        "reproduccion": "no_permitida"})
    assert r.status_code == 201, r.text
    recurso_id = uuid.UUID(r.json()["id"])
    [d] = declaraciones(db, recurso_id)
    assert (d.acceso, d.base, d.reproduccion, d.vigente_hasta.isoformat()) == ("reservado", "estatuto", "no_permitida", hasta)
    assert r.json()["clasificacion"]["acceso"] == "reservado"
    from app.models.recurso_documental import RecursoDocumental
    assert derechos.restringe(derechos.declaracion_de_recurso(db, db.get(RecursoDocumental, recurso_id)))


def test_sin_fundamento_o_sin_plazo_no_se_publica(cliente, db, fondo, archivista, sin_motor):
    espacio = abrir(cliente, db, fondo, archivista)
    r = publicar(cliente, archivista, espacio, clasificacion={"acceso": "clasificado"})
    assert r.status_code == 422 and "fundamento" in r.json()["detail"]
    r = publicar(cliente, archivista, espacio, clasificacion={"acceso": "reservado", "fundamento": "Ley 1712, art. 19"})
    assert r.status_code == 422 and "plazo" in r.json()["detail"]
    lejos = (date.today() + timedelta(days=365 * 16)).isoformat()
    r = publicar(cliente, archivista, espacio, clasificacion={"acceso": "reservado", "fundamento": "Ley 1712, art. 19",
                                                               "vigente_hasta": lejos})
    assert r.status_code == 422 and "15 años" in r.json()["detail"]
    # Nada quedó a medias: ni la descripción ni una declaración suelta.
    assert db.scalar(select(DeclaracionDerechos).where(DeclaracionDerechos.fondo_id == fondo.id)) is None


def test_sin_clasificar_hereda_y_la_ficha_dice_de_donde(cliente, db, fondo, archivista, sin_motor):
    cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "recurso_documental", "entidad_id": str(fondo.id), "base": "estatuto", "acceso": "clasificado",
        "reproduccion": "condicionada", "fundamento": "Ley 1712 de 2014, art. 18, literal a"})
    r = publicar(cliente, archivista, abrir(cliente, db, fondo, archivista))
    assert r.status_code == 201, r.text
    assert r.json()["clasificacion"] is None
    assert r.json()["clasificacion_heredada"]["acceso"] == "clasificado"
    assert r.json()["clasificacion_heredada"]["de"] == fondo.titulo


def test_corregir_la_clasificacion_y_volver_a_heredar_sin_borrar_la_historia(cliente, db, fondo, archivista, sin_motor):
    r = publicar(cliente, archivista, abrir(cliente, db, fondo, archivista), clasificacion={
        "acceso": "clasificado", "fundamento": "Ley 1712 de 2014, art. 18, literal a"})
    recurso_id = r.json()["id"]
    trabajo = cliente.post(f"/api/descripcion/registros/{recurso_id}/reabrir", headers=archivista)
    assert trabajo.status_code in (200, 201), trabajo.text
    trabajo_id = trabajo.json()["trabajo_id"]
    r = cliente.patch(f"/api/descripcion/{recurso_id}", headers=archivista,
                      json={"trabajo_id": trabajo_id, "clasificacion": {"acceso": "publico"}})
    assert r.status_code == 200, r.text
    assert r.json()["clasificacion"]["acceso"] == "publico"
    # Cada corrección libera la marca: se reabre para la siguiente.
    trabajo_id = cliente.post(f"/api/descripcion/registros/{recurso_id}/reabrir", headers=archivista).json()["trabajo_id"]
    r = cliente.patch(f"/api/descripcion/{recurso_id}", headers=archivista,
                      json={"trabajo_id": trabajo_id, "clasificacion_hereda": True})
    assert r.status_code == 200, r.text
    assert r.json()["clasificacion"] is None
    historia = declaraciones(db, uuid.UUID(recurso_id))
    assert [d.acceso for d in historia] == ["clasificado", "publico"] and not any(d.vigente for d in historia)
