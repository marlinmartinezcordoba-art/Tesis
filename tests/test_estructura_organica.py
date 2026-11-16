"""Estructura orgánica: cada dependencia del cuadro como agente RiC, subordinado a su superior, con vigencia."""

import uuid

from sqlalchemy import select

from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental


def _fondo_con_cuadro(db):
    fondo = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Alcaldía de Tunja")
    fondo.fondo_id = fondo.id
    db.add(fondo)
    db.flush()
    sec = RecursoDocumental(id=uuid.uuid4(), nivel="seccion", titulo="Despacho del Alcalde", fondo_id=fondo.id,
                            incluido_en_id=fondo.id, codigo_referencia="100")
    db.add(sec)
    db.flush()
    sub = RecursoDocumental(id=uuid.uuid4(), nivel="subseccion", titulo="Oficina Jurídica", fondo_id=fondo.id,
                            incluido_en_id=sec.id, codigo_referencia="110")
    prov = RecursoDocumental(id=uuid.uuid4(), nivel="subseccion", titulo="Dependencia 3203", fondo_id=fondo.id,
                             incluido_en_id=sec.id, codigo_referencia="3203")
    db.add_all([sub, prov])
    db.commit()
    return fondo, sec, sub


def test_derivar_crea_agentes_y_subordinacion(cliente, db, cabeceras_admin):
    fondo, sec, sub = _fondo_con_cuadro(db)
    url = f"/api/fondos/{fondo.id}/estructura-organica"
    r = cliente.post(f"{url}/derivar", headers=cabeceras_admin)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["resultado"]["creados"] == 2 and d["resultado"]["omitidos"] == ["Dependencia 3203"]
    filas = {f["titulo"]: f for f in d["dependencias"]}
    assert filas["Oficina Jurídica"]["subordinada_a"]["nombre"] == "Despacho del Alcalde"
    assert filas["Dependencia 3203"]["agente"] is None and filas["Dependencia 3203"]["provisional"]
    # Volver a derivar no duplica nada.
    again = cliente.post(f"{url}/derivar", headers=cabeceras_admin).json()["resultado"]
    assert again["creados"] == 0 and again["subordinados"] == 0
    ag = filas["Oficina Jurídica"]["agente"]["id"]
    r = cliente.put(f"{url}/{ag}/vigencia", headers=cabeceras_admin, json={"vigencia": "1950/1998"})
    assert r.status_code == 200, r.text
    assert {f["titulo"]: f for f in r.json()["dependencias"]}["Oficina Jurídica"]["agente"]["vigencia"] == "1950/1998"
    assert db.scalar(select(Relacion).where(Relacion.origen_id == sub.id, Relacion.codigo_ric == "has_creator"))
