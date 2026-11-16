"""Trazabilidad de cada relación en la vista interna de la descripción: además de origen, certeza,
motor y evidencia, cuándo se registró y quién la confirmó. El grafo, que también ve el rol de
consulta, sigue sin mostrar nada de esto."""

from sqlalchemy import select

from app.models.descripcion import Relacion
from app.servicios import descripcion
from tests.test_instrumentos import MOTOR_SECRETO, _sin_nada_interno, archivista, fondo_descrito  # noqa: F401


def test_vista_interna_dice_quien_confirmo_y_cuando(db, fondo_descrito, admin):
    o114 = fondo_descrito["o114"]
    rel = db.scalars(select(Relacion).where(Relacion.origen_id == o114.id, Relacion.motor == MOTOR_SECRETO)).first()
    rel.confirmada_por_id = admin.id
    db.commit()
    datos = descripcion.detalle(db, o114)
    fila = next(e for e in datos["entidades"] if e["relacion_id"] == str(rel.id))
    assert fila["responsable"] == admin.nombre and fila["motor"] == MOTOR_SECRETO
    assert fila["registrada"].startswith(rel.creado_en.date().isoformat())


def test_el_grafo_no_muestra_la_procedencia(cliente, db, fondo_descrito, archivista, admin):  # noqa: F811
    o114 = fondo_descrito["o114"]
    for r in db.scalars(select(Relacion).where(Relacion.origen_id == o114.id)):
        r.confirmada_por_id = admin.id
    db.commit()
    ficha = cliente.get(f"/api/grafo/recurso_documental/{o114.id}/ficha", headers=archivista).json()
    _sin_nada_interno(ficha)
    assert admin.nombre not in str(ficha)
