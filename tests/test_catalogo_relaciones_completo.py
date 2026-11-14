"""
Catálogo de relaciones completo (14-11-2026): toda relación de RiC-CM 1.0 que RiC-O 1.1 implementa
está en el catálogo único, se nombra en español y se exporta conforme al OWL oficial y al perfil
SHACL. Las que no tenían dónde declararse ahora se declaran en Autoridades (asociada a un evento, un
lugar o una regla; parte de; procedencia orgánica) o en Descripción (documento asociado, vínculo
genético); el parentesco tipado sale además con su propiedad específica (hijo, hermano, cónyuge).
"""

from rdflib import Namespace

from app.models.descripcion import Relacion
from app.servicios import ric_o
from tests.test_autoridad import vincular
from tests.test_especializacion_ric import agente, documento, exportar_conforme, relacion, u
from tests.test_preservacion import archivista, fondo  # noqa: F401  (fixtures)
from tests.test_vocabularios import entidad

RICO = Namespace(ric_o.RICO)


def test_las_relaciones_generales_se_declaran_en_autoridades_y_se_exportan_conformes(cliente, db, fondo,  # noqa: F811
                                                                                   archivista):
    alcaldia = agente(db, fondo, "Alcaldía de Tunja", "entidad_corporativa")
    tunja = entidad(db, fondo, "Tunja", clase="lugar")
    fiestas = entidad(db, fondo, "Fiestas patronales de 1948", clase="actividad")
    acuerdo = entidad(db, fondo, "Acuerdo 12 de 1946", clase="mandato")
    db.commit()
    for desde, tipo, con, con_tipo in ((tunja, "lugar_asociado", fiestas, "entidad_vocabulario"),
                                       (fiestas, "evento_asociado", alcaldia, "entidad_vocabulario"),
                                       (acuerdo, "regla_asociada", fiestas, "entidad_vocabulario"),
                                       (acuerdo, "aplicada_por", alcaldia, "entidad_vocabulario"),
                                       (alcaldia, "procedencia_organica", fondo, "recurso_documental")):
        r = vincular(cliente, archivista, desde, tipo, con, con_tipo)
        assert r.status_code == 201, (tipo, r.text)
    # Una que no corresponde se rechaza: un lugar no es una actividad.
    assert vincular(cliente, archivista, tunja, "evento_asociado", alcaldia).status_code == 422
    g = exportar_conforme(db, fondo).grafo
    assert (u(tunja.id), RICO.isPlaceAssociatedWith, u(fiestas.id)) in g
    assert (u(fiestas.id), RICO.isEventAssociatedWith, u(alcaldia.id)) in g
    assert (u(acuerdo.id), RICO.isRuleAssociatedWith, u(fiestas.id)) in g
    assert (u(acuerdo.id), RICO.isOrWasEnforcedBy, u(alcaldia.id)) in g
    assert (u(fondo.id), RICO.hasOrganicProvenance, u(alcaldia.id)) in g


def test_el_parentesco_tipado_sale_con_su_propiedad_especifica(db, fondo):  # noqa: F811
    padre, hija, hermana, esposa = (agente(db, fondo, n) for n in ("Pedro Ruiz", "Ana Ruiz", "Luz Ruiz", "Rosa Díaz"))
    carta = documento(db, fondo, "Carta familiar")
    for persona in (padre, hija, hermana, esposa):  # la exportación recorre lo que cuelga de los documentos
        relacion(db, carta, persona, "has_or_had_subject")
    for de, a, rol in ((padre, hija, "progenitor"), (hija, hermana, "hermano"), (padre, esposa, "conyuge")):
        relacion(db, de, a, "has_family_association_with", origen_tipo="entidad_vocabulario", rol=rol)
    g = exportar_conforme(db, fondo).grafo
    assert (u(padre.id), RICO.hasChild, u(hija.id)) in g
    assert (u(hija.id), RICO.hasSibling, u(hermana.id)) in g
    assert (u(padre.id), RICO.hasOrHadSpouse, u(esposa.id)) in g
    assert (u(padre.id), RICO.hasFamilyAssociationWith, u(hija.id)) in g  # la general sigue


def test_documento_asociado_y_vinculo_genetico_entre_documentos(db, fondo):  # noqa: F811
    from app.servicios import descripcion

    recurso, citado, version = documento(db, fondo, "Resolución 1919"), documento(db, fondo, "Resolución 0818"), \
        documento(db, fondo, "Proyecto de resolución")
    descripcion._vinculo(db, recurso, citado.id, "asociado_a", None)
    descripcion._vinculo(db, recurso, version.id, "vinculo_genetico_con", None)
    codigos = {r.codigo_ric for r in db.query(Relacion).filter(Relacion.origen_id == recurso.id)}
    assert {"is_record_resource_associated_with_record_resource", "has_genetic_link_to_record_resource"} <= codigos
    g = exportar_conforme(db, fondo).grafo
    assert (u(recurso.id), RICO.isRecordResourceAssociatedWithRecordResource, u(citado.id)) in g
    assert (u(recurso.id), RICO.hasGeneticLinkToRecordResource, u(version.id)) in g
