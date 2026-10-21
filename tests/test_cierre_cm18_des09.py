"""
CM-18 y DES-09: la regla de retención de la TRD es un rico:Rule del
vocabulario, regula la serie y la heredan sus expedientes y documentos.
La regla solo la crea, une y cambia la TRD al aplicarse.
"""

from rdflib import RDF, Namespace
from sqlalchemy import select

from app.models.descripcion import Relacion
from app.models.usuario import Usuario

from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, ric_o
from tests.test_autoridad import archivista, fondo, vincular  # noqa: F401
from tests.test_descripcion_v3 import publicada

RICO = Namespace(ric_o.RICO)


def _regla_de_la_trd(db, fondo, serie, **campos):
    """La regla como la deja la TRD al aplicarse (aquí sin pasar por la versión)."""
    from app.servicios import autoridad, retencion

    usuario = db.scalar(select(Usuario.id).limit(1))
    regla = retencion.crear_regla(db, fondo_id=fondo.id, usuario_id=usuario, **campos)
    autoridad.vincular(db, tipo="regla_serie", desde=regla, con_tipo="recurso_documental", con_id=serie.id,
                       usuario_id=usuario, desde_trd=True)
    db.commit()
    return regla


def test_regla_de_retencion_regula_la_serie_y_se_hereda(cliente, db, fondo, archivista):
    serie = publicada(db, fondo, "Actas", fondo, nivel="serie")
    exp = publicada(db, fondo, "Actas 1948", serie, nivel="expediente")
    acta = publicada(db, fondo, "Acta 12", exp)
    regla = _regla_de_la_trd(db, fondo, serie, nombre="TRD Actas (110.2)", gestion=2, central=18,
                             disposicion="conservacion_total",
                             procedimiento="Se transfiere al archivo histórico por su valor permanente.")
    ficha = cliente.get(f"/api/instrumentos/catalogo/{acta.id}", headers=archivista).json()
    ret = ficha["retencion"]
    assert ret["gestion_anios"] == 2 and ret["central_anios"] == 18 and ret["disposicion_final"] == "conservacion_total"
    assert ret["heredada_de"]["titulo"] == "Actas"
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    u = exportacion_rico.uri
    assert (u(regla.id), RDF.type, RICO.Rule) in g
    assert (u(regla.id), RICO.regulatesOrRegulated, u(serie.id)) in g
    assert (u(regla.id), RICO.generalDescription, None) in g


def test_la_retencion_solo_la_fija_la_trd(cliente, db, fondo, archivista):
    serie = publicada(db, fondo, "Actas", fondo, nivel="serie")
    regla = _regla_de_la_trd(db, fondo, serie, nombre="TRD", gestion=2, central=8, disposicion="seleccion",
                             procedimiento=None)
    # Sin reglas sueltas: no se crean, no se unen a otra serie, no se desunen ni cambian su retención.
    assert cliente.post("/api/vocabulario/reglas", headers=archivista, json={
        "fondo_id": str(fondo.id), "nombre": "Suelta"}).status_code == 405
    otra = publicada(db, fondo, "Correspondencia", fondo, nivel="serie")
    r = vincular(cliente, archivista, regla, "regla_serie", otra, con_tipo="recurso_documental")
    assert r.status_code == 422 and "TRD" in r.json()["detail"]
    r = cliente.patch(f"/api/vocabulario/{regla.id}", headers=archivista, json={"retencion_gestion_anios": "3"})
    assert r.status_code == 422 and "TRD" in r.json()["detail"]
    rel = db.scalar(select(Relacion.id).where(Relacion.origen_id == regla.id, Relacion.rol == "retencion"))
    r = cliente.post(f"/api/vocabulario/{regla.id}/vinculos/{rel}/anular", headers=archivista)
    assert r.status_code == 422 and "TRD" in r.json()["detail"]
    # El procedimiento (texto) sí se completa en la ficha.
    assert cliente.patch(f"/api/vocabulario/{regla.id}", headers=archivista,
                         json={"historia": "Se selecciona una muestra."}).status_code == 200
