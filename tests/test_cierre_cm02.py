"""
CM-02, CM-21 y DES-08: Record Sets que existen porque agrupan (una serie
sin archivos propios, una sección, una subsección), inclusión orgánica
única más inclusiones adicionales, y fechas extremas en EDTF.

Las secciones, subsecciones, series y subseries solo las crea la TRD al
aplicarse (el servicio con `desde_trd`); por la API de descripción se
crean expedientes y colecciones.
"""

import pytest

from rdflib import Namespace
from sqlalchemy import select

from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import descripcion, exportacion_rico, ric_o
from tests.test_descripcion import archivista, fondo  # noqa: F401
from tests.test_vocabularios import entidad

RICO = Namespace(ric_o.RICO)


def crear(cliente, cab, fondo, nivel, titulo, superior=None, **extra):
    return cliente.post("/api/descripcion/agrupaciones", headers=cab, json={
        "fondo_id": str(fondo.id), "nivel": nivel, "titulo": titulo,
        "incluido_en_id": str(superior) if superior else None, **extra})


def del_cuadro(db, fondo, nivel, titulo, superior=None, **extra):
    """Un nivel del cuadro como lo crea la TRD al aplicarse (aquí sin pasar por la versión)."""
    usuario = db.scalar(select(RecursoDocumental.creado_por_id).where(RecursoDocumental.id == fondo.id))
    r = descripcion.crear_agrupacion(db, fondo_id=fondo.id, nivel=nivel, titulo=titulo,
                                     incluido_en_id=__import__("uuid").UUID(str(superior)) if superior else None,
                                     usuario_id=usuario, desde_trd=True, **extra)
    db.commit()
    return {"id": str(r.id)}


def test_ningun_nivel_del_cuadro_se_crea_suelto(cliente, db, fondo, archivista, admin):
    from tests.conftest import ingresar

    for cab in (archivista, ingresar(cliente, admin.correo)):
        for nivel in ("seccion", "subseccion", "serie", "subserie"):
            r = crear(cliente, cab, fondo, nivel, f"Suelta {nivel}")
            assert r.status_code == 409 and "TRD" in r.json()["detail"], r.text
    # Varios documentos se describen como expediente, no como serie.
    r = cliente.post("/api/descripcion/iniciar", headers=archivista, json={
        "instanciacion_ids": [str(__import__("uuid").uuid4()), str(__import__("uuid").uuid4())], "nivel": "serie"})
    assert r.status_code in (409, 422) and "TRD" in r.json()["detail"], r.text


def test_cuadro_de_clasificacion_sin_archivos_propios(cliente, db, fondo, archivista):
    alcaldia = entidad(db, fondo, "Alcaldía de Tunja")
    db.commit()
    seccion = del_cuadro(db, fondo, "seccion", "Despacho del Alcalde", codigo_referencia="100")
    sub = del_cuadro(db, fondo, "subseccion", "Oficina Jurídica", seccion["id"], codigo_referencia="110")
    serie = del_cuadro(db, fondo, "serie", "Actas", sub["id"], codigo_referencia="110.2",
                       fechas_extremas="1930–1955", productor_id=alcaldia.id)
    s = db.get(RecursoDocumental, __import__("uuid").UUID(serie["id"]))
    assert s.fechas_extremas == "1930–1955" and s.fechas_extremas_edtf == "1930/1955"
    assert db.scalar(select(Relacion).where(Relacion.origen_id == s.id, Relacion.codigo_ric == "has_creator"))
    # Ninguna instanciación: la serie existe porque agrupa.
    assert not db.scalar(select(Relacion).where(Relacion.origen_id == s.id,
                                                Relacion.codigo_ric == "has_or_had_instantiation"))
    # Código duplicado, orden de niveles y fechas no interpretables se rechazan.
    with pytest.raises(descripcion.ErrorDescripcion) as exc:
        del_cuadro(db, fondo, "serie", "Otra", sub["id"], codigo_referencia="110.2")
    assert exc.value.codigo == 409
    db.rollback()
    with pytest.raises(descripcion.ErrorDescripcion):
        del_cuadro(db, fondo, "seccion", "Mal", serie["id"])
    db.rollback()
    with pytest.raises(descripcion.ErrorDescripcion):
        del_cuadro(db, fondo, "serie", "Fechas", sub["id"], fechas_extremas="hacia los treinta")
    db.rollback()
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    u = exportacion_rico.uri
    assert (u(sub["id"]), RICO.includesOrIncluded, u(s.id)) in g


def test_inclusion_adicional_sin_tocar_la_organica(cliente, db, fondo, archivista):
    serie = del_cuadro(db, fondo, "serie", "Correspondencia")
    exp = crear(cliente, archivista, fondo, "expediente", "Correspondencia 1948", serie["id"]).json()
    coleccion = crear(cliente, archivista, fondo, "coleccion", "Colección facticia: centenario").json()
    r = cliente.post(f"/api/descripcion/registros/{exp['id']}/inclusiones", headers=archivista,
                     json={"conjunto_id": coleccion["id"]})
    assert r.status_code == 201, r.text
    e = db.get(RecursoDocumental, __import__("uuid").UUID(exp["id"]))
    assert str(e.incluido_en_id) == serie["id"]  # la orgánica no cambia
    filas = db.scalars(select(Relacion).where(Relacion.destino_id == e.id,
                                              Relacion.codigo_ric == "includes_or_included")).all()
    assert sorted((f.rol or "organica") for f in filas) == ["adicional", "organica"]
    # Sin ciclos ni repetidas.
    assert cliente.post(f"/api/descripcion/registros/{serie['id']}/inclusiones", headers=archivista,
                        json={"conjunto_id": exp["id"]}).status_code == 422
    assert cliente.post(f"/api/descripcion/registros/{exp['id']}/inclusiones", headers=archivista,
                        json={"conjunto_id": coleccion["id"]}).status_code == 409


def test_fondo_registra_sus_fechas_extremas_en_edtf(cliente, db, admin):
    from app.servicios import cuadro
    from tests.archivos import trd_agn_xlsx
    from tests.conftest import ingresar

    cab = ingresar(cliente, admin.correo)
    filas = cuadro.vista_previa(trd_agn_xlsx(), "trd.xlsx")["filas"]
    # Un fondo solo se registra con su cuadro de clasificación.
    assert cliente.post("/api/fondos", headers=cab, json={"titulo": "Fondo suelto"}).status_code == 405
    r = cliente.post("/api/fondos/configurar", headers=cab, json={
        "fondo": {"titulo": "Fondo Notarial", "fechas_extremas": "1890 a 1960"}, "filas": filas, "crear": True})
    assert r.status_code == 200 and r.json()["creado"], r.text
    f = db.get(RecursoDocumental, __import__("uuid").UUID(r.json()["fondo"]["id"]))
    assert f.fechas_extremas_edtf == "1890/1960"
    assert cliente.post("/api/fondos/configurar", headers=cab, json={
        "fondo": {"titulo": "Otro", "fechas_extremas": "siglo XIX"}, "filas": filas}).status_code == 422


def test_el_codigo_de_la_serie_se_compone_desde_su_superior(cliente, db, fondo, archivista):
    """DES-08: «CO» y «100.12» ya no pueden convivir como textos libres bajo el mismo superior."""
    sub = del_cuadro(db, fondo, "seccion", "Despacho", codigo_referencia="100")
    with pytest.raises(descripcion.ErrorDescripcion):
        del_cuadro(db, fondo, "serie", "Actas", sub["id"], codigo_referencia="CO")
    db.rollback()
    serie = del_cuadro(db, fondo, "serie", "Actas", sub["id"], codigo_referencia="100.2")
    del_cuadro(db, fondo, "subserie", "Actas de junta", serie["id"], codigo_referencia="100.2.1")
