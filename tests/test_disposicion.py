"""
Disposición final ejecutada como rico:Activity.

- El calendario dice qué cumplió su retención (fecha final + AG + AC) y qué manda la TRD.
- Solo se dispone lo que la TRD manda y lo que ya cumplió; lo dispuesto no se dispone dos veces.
- Nada se borra: el expediente eliminado sigue descrito y su estado sale de la actividad,
  que en el grafo tiene su tipo, quien la ejerce, su fecha, la regla que la regula y lo que afectó.
- Solo la administración ejecuta.
"""

import uuid

from rdflib import Namespace
from sqlalchemy import select

from app.models.recurso_documental import RecursoDocumental
from app.servicios import cuadro, descripcion, exportacion_rico
from tests.archivos import trd_agn_xlsx
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import eventos
from tests.test_especializacion_ric import exportar_conforme

RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")


def _fondo(cliente, db, cab):
    filas = cuadro.vista_previa(trd_agn_xlsx(), "trd.xlsx")["filas"]
    r = cliente.post("/api/fondos/configurar", headers=cab, json={
        "fondo": {"titulo": "Alcaldía de Tunja"}, "filas": filas, "crear": True,
        "version": {"acto_aprobacion": "Resolución 045", "fecha_aprobacion": "2009-02-15", "vigente_desde": "2009-03-01"}})
    fnd = db.get(RecursoDocumental, uuid.UUID(r.json()["fondo"]["id"]))
    serie = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fnd.id,
                                                      RecursoDocumental.codigo_referencia == "110.15"))
    usuario = fnd.creado_por_id
    viejo = descripcion.crear_agrupacion(db, fondo_id=fnd.id, nivel="expediente", titulo="Correspondencia 2010",
                                         incluido_en_id=serie.id, usuario_id=usuario, fechas_extremas="2010–2012")
    nuevo = descripcion.crear_agrupacion(db, fondo_id=fnd.id, nivel="expediente", titulo="Correspondencia 2024",
                                         incluido_en_id=serie.id, usuario_id=usuario, fechas_extremas="2024")
    db.commit()
    return fnd, viejo, nuevo


def test_calendario_y_eliminacion_como_actividad_de_ric(cliente, db, cabeceras_admin):
    cab = cabeceras_admin
    fnd, viejo, nuevo = _fondo(cliente, db, cab)
    cal = {c["titulo"]: c for c in cliente.get("/api/disposicion/calendario", headers=cab,
                                              params={"fondo_id": str(fnd.id)}).json()}
    # Correspondencia: 2 años en gestión + 3 en central, eliminación.
    assert cal["Correspondencia 2010"]["vence"] == "2017-12-31" and cal["Correspondencia 2010"]["cumplida"]
    assert cal["Correspondencia 2024"]["vence"] == "2029-12-31" and not cal["Correspondencia 2024"]["cumplida"]
    assert cal["Correspondencia 2010"]["disposicion"] == "eliminacion"
    pedido = {"fondo_id": str(fnd.id), "recursos": [str(viejo.id)], "disposicion": "eliminacion",
              "acta_numero": "05", "acta_fecha": "2025-03-10", "ejecutor": "Comité Institucional de Gestión y Desempeño"}
    # Lo que la TRD no manda, o lo que no cumplió, no se dispone.
    r = cliente.post("/api/disposicion/ejecutar", headers=cab, json=pedido | {"disposicion": "conservacion_total"})
    assert r.status_code == 422 and "La TRD dice eliminación" in r.json()["detail"]
    r = cliente.post("/api/disposicion/ejecutar", headers=cab, json=pedido | {"recursos": [str(nuevo.id)]})
    assert r.status_code == 422 and "cumple su retención el 2029-12-31" in r.json()["detail"]
    r = cliente.post("/api/disposicion/ejecutar", headers=cab, json=pedido)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["tipo"] == "eliminacion" and a["elementos"] == 1 and a["ejecutor"].startswith("Comité")
    assert cliente.post("/api/disposicion/ejecutar", headers=cab, json=pedido).status_code == 409
    # Nada se borró: el expediente sigue descrito y dice cómo y cuándo se dispuso.
    assert db.get(RecursoDocumental, viejo.id) is not None
    cal = {c["titulo"]: c for c in cliente.get("/api/disposicion/calendario", headers=cab,
                                              params={"fondo_id": str(fnd.id)}).json()}
    assert cal["Correspondencia 2010"]["ejecutada"]["tipo_nombre"] == "Eliminación documental"
    assert not cal["Correspondencia 2010"]["cumplida"]
    assert len(eventos(db, "disposicion_ejecutada")) == 1
    # En el grafo: la actividad, su tipo, quién la ejerce, su fecha, la regla y lo que afectó.
    g = exportar_conforme(db, fnd).grafo
    u = exportacion_rico.uri
    act = u(a["id"])
    assert (act, RICO.affectsOrAffected, u(viejo.id)) in g
    assert any(True for _ in g.objects(act, RICO.hasActivityType))
    assert any(True for _ in g.subjects(RICO.performsOrPerformed, act))
    assert any(True for _ in g.subjects(RICO.regulatesOrRegulated, act))
    assert any(True for _ in g.subjects(RICO.isDateAssociatedWith, act))


def test_solo_la_administracion_ejecuta(cliente, db, cabeceras_admin):
    fnd, viejo, _ = _fondo(cliente, db, cabeceras_admin)
    crear_usuario(db, "ana@disp.co", "archivista")
    db.commit()
    ana = ingresar(cliente, "ana@disp.co")
    assert cliente.get("/api/disposicion/calendario", headers=ana, params={"fondo_id": str(fnd.id)}).status_code == 200
    assert cliente.post("/api/disposicion/ejecutar", headers=ana, json={
        "fondo_id": str(fnd.id), "recursos": [str(viejo.id)], "disposicion": "eliminacion", "acta_numero": "05",
        "acta_fecha": "2025-03-10", "ejecutor": "Comité"}).status_code == 403
