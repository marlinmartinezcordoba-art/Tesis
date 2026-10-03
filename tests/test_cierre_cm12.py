"""
CM-12: el lugar donde se expidió un documento es una relación distinta del
lugar del que trata (RiC-R075 isOrWasLocationOf, desde el lugar).
"""

from rdflib import Namespace
from sqlalchemy import select

from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, ric_o
from tests.test_descripcion import archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_v3 import TEXTO, publicar, sin_motor  # noqa: F401

RICO = Namespace(ric_o.RICO)


def test_lugar_de_expedicion_distinto_del_tema(cliente, db, fondo, archivista, sin_motor):
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "lugar", "valor": "Tunja", "rol": "expedicion", "crear_nueva": True},
        {"tipo": "lugar", "valor": "Boyacá", "crear_nueva": True}])
    assert r.status_code == 201, r.text
    d = r.json()
    lugares = {e["valor"]: e for e in d["entidades"] if e["tipo"] == "lugar"}
    assert lugares["Tunja"]["codigo_ric"] == "is_or_was_location_of" and lugares["Tunja"]["rol"] == "expedicion"
    assert lugares["Boyacá"]["codigo_ric"] == "has_or_had_subject"
    fila = db.scalar(select(Relacion).where(Relacion.codigo_ric == "is_or_was_location_of"))
    assert str(fila.destino_id) == d["id"]  # del lugar al documento, como la propiedad de RiC-O
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    assert (exportacion_rico.uri(fila.origen_id), RICO.isOrWasLocationOf, exportacion_rico.uri(fila.destino_id)) in g
