"""
CM-03: cada documento de un expediente puede tener su propio Record.
CM-04: el original físico es una Instantiation con su soporte, del que
derivan las digitalizaciones; el recorte deriva de su archivo de origen.
"""

import uuid

from rdflib import Namespace
from sqlalchemy import select

from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, preservacion, ric_o
from tests.test_descripcion import aceptar_todo, archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_v3 import TEXTO, publicar, sin_motor  # noqa: F401

RICO = Namespace(ric_o.RICO)


def test_un_oficio_del_expediente_pasa_a_ser_su_propio_record(cliente, db, fondo, archivista, sin_motor):
    a, b = documento(db, fondo, "oficio_114.pdf", TEXTO), documento(db, fondo, "oficio_115.pdf", TEXTO)
    espacio = iniciar(cliente, archivista, [a.id, b.id], nivel="expediente")
    exp = publicar(cliente, archivista, espacio, titulo="Correspondencia 1948")
    assert exp.status_code == 201, exp.text
    exp_id = exp.json()["id"]
    r = cliente.post(f"/api/descripcion/registros/{exp_id}/individualizar", headers=archivista,
                     json={"instanciacion_id": str(a.id), "titulo": "Oficio 114"})
    assert r.status_code == 201, r.text
    oficio = r.json()
    assert oficio["nivel"] == "unidad_documental" and oficio["incluido_en"]["id"] == exp_id
    assert [i["nombre"] for i in oficio["instanciaciones"]] == ["oficio_114.pdf"]
    # El expediente ya no lo tiene como instanciación propia; la fila vieja quedó anulada, no borrada.
    detalle_exp = cliente.get(f"/api/descripcion/registros/{exp_id}", headers=archivista).json()
    assert [i["nombre"] for i in detalle_exp["instanciaciones"]] == ["oficio_115.pdf"]
    anulada = db.scalar(select(Relacion).where(Relacion.destino_id == a.id, Relacion.estado == "anulada"))
    assert str(anulada.origen_id) == exp_id
    # Ahora el oficio puede tener su propio productor: se reabre y se describe.
    assert cliente.post(f"/api/descripcion/registros/{oficio['id']}/reabrir", headers=archivista).status_code == 200


def test_original_fisico_con_soporte_y_digitalizacion_derivada(cliente, db, fondo, archivista, sin_motor):
    d = documento(db, fondo, "acta.pdf", TEXTO)
    espacio = iniciar(cliente, archivista, [d.id])
    acta = publicar(cliente, archivista, espacio, titulo="Acta 12").json()
    r = cliente.post(f"/api/descripcion/registros/{acta['id']}/original-fisico", headers=archivista,
                     json={"soporte": "papel", "ubicacion": "Caja 3, carpeta 2"})
    assert r.status_code == 201, r.text
    [fisico] = [i for i in r.json()["instanciaciones"] if i.get("fisica")]
    assert fisico["soporte"] == "papel" and fisico["ubicacion"] == "Caja 3, carpeta 2"
    fila = db.scalar(select(Relacion).where(Relacion.codigo_ric == "has_or_had_derived_instantiation"))
    assert str(fila.origen_id) == fisico["id"] and fila.destino_id == d.id
    # El original físico no entra a la fijeza ni a la cola: no tiene archivo.
    assert uuid.UUID(fisico["id"]) not in set(db.scalars(preservacion._verificables(db).with_only_columns(Instanciacion.id)))
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    u = exportacion_rico.uri
    assert (u(fisico["id"]), RICO.hasOrHadDerivedInstantiation, u(d.id)) in g
    assert next(g.objects(u(fisico["id"]), RICO.hasCarrierType), None) is not None
    assert cliente.post(f"/api/descripcion/registros/{acta['id']}/original-fisico", headers=archivista,
                        json={"soporte": "arcilla"}).status_code == 422
