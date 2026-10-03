"""
Cierre de la auditoría RiC, bloque 2 (RiC-O): O-12, O-26 y O-30.
"""

import pytest
from rdflib import OWL, Literal, URIRef

from app.models.recurso_documental import RecursoDocumental
from app.servicios import autoridad, exportacion_rico
from tests.test_exportacion_rico import RICO, exportar, fondo_rico, u  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


# --- O-26 · idiomas de una agrupación --------------------------------------------------------------


def test_agrupacion_con_un_idioma_dice_todos_sus_miembros(db, fondo_rico):
    f = fondo_rico
    db.get(RecursoDocumental, f["exp48"].id).idiomas = ["spa"]
    db.commit()
    g = exportar(db, f).grafo
    assert len(set(g.objects(u(f["exp48"].id), RICO.hasOrHadAllMembersWithLanguage))) == 1
    assert not set(g.objects(u(f["exp48"].id), RICO.hasOrHadSomeMembersWithLanguage))


def test_agrupacion_con_varios_idiomas_dice_algunos_miembros(db, fondo_rico):
    """Un expediente en español y latín no tiene todos sus documentos en cada idioma."""
    f = fondo_rico
    db.get(RecursoDocumental, f["exp48"].id).idiomas = ["spa", "lat"]
    db.commit()
    g = exportar(db, f).grafo
    assert len(set(g.objects(u(f["exp48"].id), RICO.hasOrHadSomeMembersWithLanguage))) == 2
    assert not set(g.objects(u(f["exp48"].id), RICO.hasOrHadAllMembersWithLanguage))


# --- O-12 · fechas extremas de una agrupación -------------------------------------------------------


def test_fechas_extremas_de_una_agrupacion_son_las_de_sus_miembros(db, fondo_rico):
    f = fondo_rico
    serie = db.get(RecursoDocumental, f["serie"].id)
    serie.fechas_extremas, serie.fechas_extremas_edtf = "1946-1950", "1946/1950"
    db.commit()
    g = exportar(db, f).grafo
    assert g.value(u(f["serie"].id), RICO.hasOrHadAllMembersWithCreationDate) is not None
    assert g.value(u(f["serie"].id), RICO.hasCreationDate) is None


# --- O-30 · URI externas canónicas e idioma BCP 47 --------------------------------------------------


@pytest.mark.parametrize("esquema,valor,esperada", [
    ("wikidata", "Q42", "http://www.wikidata.org/entity/Q42"),
    ("viaf", "113230702", "http://viaf.org/viaf/113230702"),
    ("lcnaf", "n79021164", "http://id.loc.gov/authorities/names/n79021164"),
])
def test_uri_externa_es_la_canonica_de_cada_autoridad(esquema, valor, esperada):
    assert autoridad.URI_EXTERNA[esquema].format(valor) == esperada


@pytest.mark.parametrize("codigo,etiqueta", [("spa", "es"), ("lat", "la"), ("SPA", "es"), ("quc", "quc"),
                                             (None, None), ("", None), ("español", None)])
def test_idioma_iso_639_3_se_convierte_a_bcp47(codigo, etiqueta):
    assert exportacion_rico.bcp47(codigo) == etiqueta


def test_nombre_con_idioma_invalido_se_rechaza(db, fondo_rico, admin):
    alcaldia = fondo_rico["alcaldia"]
    with pytest.raises(autoridad.ErrorAutoridad):
        autoridad.agregar_nombre(db, alcaldia, tipo="otra", nombre="Town hall", idioma="ingles", regla=None,
                                 vigencia_edtf=None, usuario_id=admin.id)


def test_nombre_en_espanol_sale_con_etiqueta_es(db, fondo_rico, admin):
    f = fondo_rico
    autoridad.agregar_nombre(db, f["alcaldia"], tipo="otra", nombre="Municipalidad de Tunja", idioma="spa",
                             regla=None, vigencia_edtf=None, usuario_id=admin.id)
    db.commit()
    g = exportar(db, f).grafo
    assert (None, RICO.textualValue, Literal("Municipalidad de Tunja", lang="es")) in g
    assert (u(f["alcaldia"].id), OWL.sameAs, URIRef("http://www.wikidata.org/entity/Q1000000")) in g
