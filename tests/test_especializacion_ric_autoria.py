"""
Brecha 8 de la auditoría de especialización RiC: el autor (RiC-R079,
rico:hasAuthor) y el acumulador (RiC-R028, rico:hasAccumulator) se declaran
al describir, con el dominio y el rango que da el OWL de RiC-O 1.1.
"""

from sqlalchemy import select

from app.models.descripcion import Relacion
from tests.test_descripcion import archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_v3 import TEXTO, publicar, sin_motor  # noqa: F401


def test_autor_y_acumulador_al_describir(cliente, db, fondo, archivista, sin_motor):
    d = documento(db, fondo, "a.pdf", TEXTO)
    espacio = iniciar(cliente, archivista, [d.id])
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "productor", "valor": "Secretaría de Gobierno",
         "crear_nueva": True},
        {"tipo": "agente", "subtipo": "persona", "rol": "autor", "valor": "Pedro Gómez", "crear_nueva": True},
        {"tipo": "agente", "subtipo": "familia", "rol": "acumulador", "valor": "Familia Gómez", "crear_nueva": True}])
    assert r.status_code == 201, r.text
    codigos = {x.codigo_ric for x in db.scalars(select(Relacion).where(
        Relacion.origen_id.in_([__import__("uuid").UUID(r.json()["id"])]), Relacion.estado == "vigente"))}
    assert {"has_creator", "has_author", "has_accumulator"} <= codigos


def test_una_entidad_corporativa_no_es_autora(cliente, db, fondo, archivista, sin_motor):
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "autor", "valor": "Alcaldía", "crear_nueva": True}])
    assert r.status_code == 422 and "persona, un grupo o un cargo" in r.json()["detail"]


def test_el_autor_es_de_un_documento_no_de_un_expediente(cliente, db, fondo, archivista, sin_motor):
    a, b = documento(db, fondo, "a.pdf", TEXTO), documento(db, fondo, "b.pdf", TEXTO)
    espacio = iniciar(cliente, archivista, [a.id, b.id], nivel="expediente")
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "agente", "subtipo": "persona", "rol": "autor", "valor": "Pedro Gómez", "crear_nueva": True}])
    assert r.status_code == 422 and "unidad documental" in r.json()["detail"]
