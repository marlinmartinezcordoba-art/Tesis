"""
CM-02, CM-21 y DES-08: Record Sets que existen porque agrupan (una serie
sin archivos propios, una sección, una subsección), inclusión orgánica
única más inclusiones adicionales, y fechas extremas en EDTF.
"""

from rdflib import Namespace
from sqlalchemy import select

from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, ric_o
from tests.test_descripcion import archivista, fondo  # noqa: F401
from tests.test_vocabularios import entidad

RICO = Namespace(ric_o.RICO)


def crear(cliente, cab, fondo, nivel, titulo, superior=None, **extra):
    return cliente.post("/api/descripcion/agrupaciones", headers=cab, json={
        "fondo_id": str(fondo.id), "nivel": nivel, "titulo": titulo,
        "incluido_en_id": str(superior) if superior else None, **extra})


def test_cuadro_de_clasificacion_sin_archivos_propios(cliente, db, fondo, archivista):
    alcaldia = entidad(db, fondo, "Alcaldía de Tunja")
    db.commit()
    seccion = crear(cliente, archivista, fondo, "seccion", "Despacho del Alcalde", codigo_referencia="100")
    assert seccion.status_code == 201, seccion.text
    sub = crear(cliente, archivista, fondo, "subseccion", "Oficina Jurídica", seccion.json()["id"], codigo_referencia="110")
    assert sub.status_code == 201, sub.text
    serie = crear(cliente, archivista, fondo, "serie", "Actas", sub.json()["id"], codigo_referencia="110.2",
                  fechas_extremas="1930–1955", productor_id=str(alcaldia.id))
    assert serie.status_code == 201, serie.text
    s = db.get(RecursoDocumental, __import__("uuid").UUID(serie.json()["id"]))
    assert s.fechas_extremas == "1930–1955" and s.fechas_extremas_edtf == "1930/1955"
    assert db.scalar(select(Relacion).where(Relacion.origen_id == s.id, Relacion.codigo_ric == "has_creator"))
    # Ninguna instanciación: la serie existe porque agrupa.
    assert not db.scalar(select(Relacion).where(Relacion.origen_id == s.id,
                                                Relacion.codigo_ric == "has_or_had_instantiation"))
    # Código duplicado, orden de niveles y fechas no interpretables se rechazan.
    assert crear(cliente, archivista, fondo, "serie", "Otra", sub.json()["id"], codigo_referencia="110.2").status_code == 409
    assert crear(cliente, archivista, fondo, "seccion", "Mal", serie.json()["id"]).status_code == 422
    assert crear(cliente, archivista, fondo, "serie", "Fechas", sub.json()["id"],
                 fechas_extremas="hacia los treinta").status_code == 422
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    u = exportacion_rico.uri
    assert (u(sub.json()["id"]), RICO.includesOrIncluded, u(s.id)) in g


def test_inclusion_adicional_sin_tocar_la_organica(cliente, db, fondo, archivista):
    serie = crear(cliente, archivista, fondo, "serie", "Correspondencia").json()
    exp = crear(cliente, archivista, fondo, "expediente", "Correspondencia 1948", serie["id"]).json()
    coleccion = crear(cliente, archivista, fondo, "serie", "Colección facticia: centenario").json()
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
    from tests.conftest import ingresar

    cab = ingresar(cliente, admin.correo)
    r = cliente.post("/api/fondos", headers=cab, json={"titulo": "Fondo Notarial", "fechas_extremas": "1890 a 1960"})
    assert r.status_code == 201, r.text
    f = db.get(RecursoDocumental, __import__("uuid").UUID(r.json()["id"]))
    assert f.fechas_extremas_edtf == "1890/1960"
    assert cliente.post("/api/fondos", headers=cab, json={"titulo": "Otro", "fechas_extremas": "siglo XIX"}).status_code == 422


def test_el_codigo_de_la_serie_se_compone_desde_su_superior(cliente, db, fondo, archivista):
    """DES-08: «CO» y «100.12» ya no pueden convivir como textos libres bajo el mismo superior."""
    sub = crear(cliente, archivista, fondo, "seccion", "Despacho", codigo_referencia="100").json()
    assert crear(cliente, archivista, fondo, "serie", "Actas", sub["id"], codigo_referencia="CO").status_code == 422
    serie = crear(cliente, archivista, fondo, "serie", "Actas", sub["id"], codigo_referencia="100.2")
    assert serie.status_code == 201, serie.text
    assert crear(cliente, archivista, fondo, "subserie", "Actas de junta", serie.json()["id"],
                 codigo_referencia="100.2.1").status_code == 201
