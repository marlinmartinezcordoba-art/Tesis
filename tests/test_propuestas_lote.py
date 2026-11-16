"""Propuestas de descripción en lote: RICORA describe en segundo plano, la archivista revisa y publica."""

from app.models.evidencia_ia import PropuestaIA
from app.servicios import propuestas_lote
from tests.test_descripcion import archivista, documento, fondo, iniciar, motor_prueba  # noqa: F401

TEXTO = "la Alcaldía Municipal informa a su despacho sobre el estado del archivo municipal."


def test_la_propuesta_en_lote_se_usa_al_abrir_el_documento(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    d1, d2 = documento(db, fondo, "uno.pdf", TEXTO), documento(db, fondo, "dos.pdf", TEXTO)
    assert {i.id for i in propuestas_lote.pendientes(db, fondo.id)} == {d1.id, d2.id}
    p = propuestas_lote.proponer(db, fondo.id, d1, None)
    db.commit()
    assert p.origen == "lote" and p.trabajo_id is None and len(motor_prueba.llamadas) == 1
    assert [i.id for i in propuestas_lote.pendientes(db, fondo.id)] == [d2.id]
    cola = {x["id"]: x for x in cliente.get(f"/api/descripcion/cola?fondo_id={fondo.id}", headers=archivista).json()}
    assert cola[str(d1.id)]["propuesta_lista"] and not cola[str(d2.id)]["propuesta_lista"]
    # Al abrirlo no se vuelve a consultar el motor: la propuesta guardada pasa al trabajo.
    espacio = iniciar(cliente, archivista, [d1.id])
    assert len(motor_prueba.llamadas) == 1
    assert espacio["propuesta"]["titulo"].startswith("Oficio de la Alcaldía")
    db.expire_all()
    assert str(p.id) == espacio["propuesta"]["propuesta_id"]
    assert propuestas_lote.vigente(db, d1.id) is None  # ya se usó


def test_pedir_el_lote_lo_lanza_en_segundo_plano_y_dice_cuantos_faltan(cliente, db, fondo, archivista, motor_prueba,  # noqa: F811
                                                                       monkeypatch):
    documento(db, fondo, "uno.pdf", TEXTO)
    lanzados = []
    monkeypatch.setattr(propuestas_lote, "empezar", lambda f, u, total: lanzados.append(total))
    r = cliente.get(f"/api/descripcion/proponer-lote?fondo_id={fondo.id}", headers=archivista)
    assert r.status_code == 200 and r.json()["pendientes"] == 1
    r = cliente.post(f"/api/descripcion/proponer-lote?fondo_id={fondo.id}", headers=archivista)
    assert r.status_code == 200, r.text
    assert lanzados == [1]
