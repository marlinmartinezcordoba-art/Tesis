"""
Corregir el nombre de una agrupación del cuadro («Dependencia 3203», el nombre provisional que pone la carga
de la TRD cuando trae el código sin el nombre). Se corrige en el cuadro y en la dependencia de la TRD con el
mismo código, queda en la auditoría y solo lo hace la administración.
"""

import uuid

from sqlalchemy import select

from app.models.auditoria import RegistroAuditoria
from app.models.recurso_documental import RecursoDocumental
from app.models.trd import DependenciaTrd
from tests.conftest import crear_usuario, ingresar


def _cuadro(db):
    fondo = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Ministerio de Ambiente")
    fondo.fondo_id = fondo.id
    db.add(fondo)
    db.flush()
    seccion = RecursoDocumental(id=uuid.uuid4(), nivel="seccion", titulo="Dependencia 3203", codigo_referencia="3203",
                                fondo_id=fondo.id, incluido_en_id=fondo.id)
    db.add(seccion)
    db.add(DependenciaTrd(fondo_id=fondo.id, codigo="3203", nombre="Dependencia 3203"))
    db.commit()
    return fondo, seccion


def test_el_nombre_se_corrige_en_el_cuadro_y_en_la_trd(cliente, db, cabeceras_admin):
    fondo, seccion = _cuadro(db)
    r = cliente.patch(f"/api/cuadro/agrupaciones/{seccion.id}", headers=cabeceras_admin,
                      json={"nombre": "Dirección de Bosques, Biodiversidad y Servicios Ecosistémicos"})
    assert r.status_code == 200, r.text
    assert r.json()["dependencias_trd_corregidas"] == 1
    db.expire_all()
    assert db.get(RecursoDocumental, seccion.id).titulo.startswith("Dirección de Bosques")
    dep = db.scalar(select(DependenciaTrd).where(DependenciaTrd.fondo_id == fondo.id))
    assert dep.nombre.startswith("Dirección de Bosques")
    evento = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "agrupacion_renombrada"))
    assert evento is not None and "Dependencia 3203" in evento.detalle


def test_no_acepta_otro_nombre_provisional_ni_el_fondo(cliente, db, cabeceras_admin):
    fondo, seccion = _cuadro(db)
    for nombre in ("3203", "Dependencia 3204", "Serie 1"):
        r = cliente.patch(f"/api/cuadro/agrupaciones/{seccion.id}", headers=cabeceras_admin, json={"nombre": nombre})
        assert r.status_code == 422, (nombre, r.text)
    r = cliente.patch(f"/api/cuadro/agrupaciones/{fondo.id}", headers=cabeceras_admin, json={"nombre": "Otro fondo"})
    assert r.status_code == 422


def test_solo_la_administracion_lo_corrige(cliente, db):
    _, seccion = _cuadro(db)
    crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana")
    r = cliente.patch(f"/api/cuadro/agrupaciones/{seccion.id}", headers=ingresar(cliente, "ana@correo.com"),
                      json={"nombre": "Dirección de Bosques"})
    assert r.status_code == 403
