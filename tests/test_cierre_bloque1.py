"""
Cierre del bloque 1 (RiC-CM) de la auditoría RiC: persona, cargo, grupo y
familia con sus relaciones propias; lugar con varios superiores en el
tiempo y lugar de expedición; integridad de la tabla de relaciones.
"""

import uuid

import pytest
from rdflib import RDF, Namespace
from sqlalchemy import select, text

from app.models.descripcion import Relacion
from app.servicios import exportacion_rico, ric_o, vocabulario
from app.servicios.integridad_ric import RelacionNoConforme
from tests.test_autoridad import archivista, entidad, ficha, fondo, vincular  # noqa: F401

RICO = Namespace(ric_o.RICO)


def test_persona_ocupa_un_cargo_con_vigencia_y_el_cargo_existe_en_la_alcaldia(cliente, db, fondo, archivista):
    """CM-06 y CM-10: «Juan Pérez» ocupó «Secretario de Gobierno» de 1948 a 1950,
    cargo que existe en la Alcaldía. Antes eran dos etiquetas sin relación."""
    juan = entidad(db, fondo, "Juan Pérez", subtipo="persona")
    secretario = entidad(db, fondo, "Secretario de Gobierno", subtipo="cargo")
    alcaldia = entidad(db, fondo, "Alcaldía de Tunja", subtipo="entidad_corporativa")
    r = vincular(cliente, archivista, juan, "ocupa_cargo", secretario, fecha_edtf="1948/1950")
    assert r.status_code == 201, r.text
    assert vincular(cliente, archivista, secretario, "cargo_en", alcaldia).status_code == 201
    [v] = [x for x in ficha(cliente, archivista, secretario)["ficha"]["vinculos"] if x["vinculo"] == "ocupa_cargo"]
    assert v["propiedad_rico"] == "rico:isOrWasOccupiedBy" and v["vigencia"] == "1948/1950"
    [c] = [x for x in ficha(cliente, archivista, alcaldia)["ficha"]["vinculos"] if x["vinculo"] == "cargo_en"]
    assert c["propiedad_rico"] == "rico:hasOrHadPosition"
    # Validado por subtipo, no solo por clase: un cargo no «ocupa» otro cargo.
    alcalde = entidad(db, fondo, "Alcalde", subtipo="cargo")
    assert vincular(cliente, archivista, alcalde, "ocupa_cargo", secretario).status_code == 422


def test_grupo_y_familia_con_miembros_subdivision_y_direccion(cliente, db, fondo, archivista):
    """CM-07 y CM-09: quién compone una junta, una familia, y sus subdivisiones."""
    junta = entidad(db, fondo, "Junta de Ornato", subtipo="grupo")
    comite = entidad(db, fondo, "Comité de Parques", subtipo="grupo")
    familia = entidad(db, fondo, "Familia Suárez Rendón", subtipo="familia")
    ana = entidad(db, fondo, "Ana Suárez", subtipo="persona")
    assert vincular(cliente, archivista, junta, "miembro", ana, fecha_edtf="1950").status_code == 201
    assert vincular(cliente, archivista, familia, "miembro", ana).status_code == 201
    assert vincular(cliente, archivista, ana, "dirige", junta).status_code == 201
    assert vincular(cliente, archivista, junta, "subdivision", comite).status_code == 201
    assert vincular(cliente, archivista, comite, "subdivision", junta).status_code == 422  # sin ciclos
    assert vincular(cliente, archivista, ana, "miembro", junta).status_code == 422  # una persona no tiene miembros
    lectura = {x["propiedad_rico"] for x in ficha(cliente, archivista, ana)["ficha"]["vinculos"]}
    assert {"rico:isOrWasMemberOf", "rico:isOrWasLeaderOf"} <= lectura


def test_la_familia_y_el_cargo_se_exportan_con_su_clase_y_relaciones(cliente, db, fondo, archivista):
    from app.models.recurso_documental import RecursoDocumental
    from app.db.base import ahora

    familia = entidad(db, fondo, "Familia Suárez Rendón", subtipo="familia")
    ana = entidad(db, fondo, "Ana Suárez", subtipo="persona")
    cargo = entidad(db, fondo, "Escribano", subtipo="cargo")
    vincular(cliente, archivista, familia, "miembro", ana)
    vincular(cliente, archivista, ana, "ocupa_cargo", cargo)
    doc = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo="Testamento", fondo_id=fondo.id,
                            incluido_en_id=fondo.id, publicado_en=ahora())
    db.add(doc)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=doc.id, destino_tipo="entidad_vocabulario",
                    destino_id=familia.id, tipo_relacion="procedencia", codigo_ric="has_creator", origen="persona"))
    db.commit()
    g = exportacion_rico.exportar(db, fondo).grafo
    u = exportacion_rico.uri
    assert (u(familia.id), RDF.type, RICO.Family) in g
    assert (u(familia.id), RICO.hasOrHadMember, u(ana.id)) in g
    assert (u(ana.id), RICO.occupiesOrOccupied, u(cargo.id)) in g
    assert (u(cargo.id), RDF.type, RICO.Position) in g


def test_lugar_con_dos_superiores_en_el_tiempo_sin_solape(cliente, db, fondo, archivista):
    """CM-12: Tunja en el Estado Soberano de Boyacá hasta 1885 y en el departamento desde 1886."""
    tunja = entidad(db, fondo, "Tunja", clase="lugar")
    estado = entidad(db, fondo, "Estado Soberano de Boyacá", clase="lugar")
    depto = entidad(db, fondo, "Departamento de Boyacá", clase="lugar")
    provincia = entidad(db, fondo, "Provincia de Tunja", clase="lugar")
    assert vincular(cliente, archivista, tunja, "lugar_superior", estado, fecha_edtf="1857/1885").status_code == 201
    assert vincular(cliente, archivista, tunja, "lugar_superior", depto, fecha_edtf="1886/").status_code == 201
    r = vincular(cliente, archivista, tunja, "lugar_superior", provincia, fecha_edtf="1880/1890")
    assert r.status_code == 422 and "se cruza" in r.text
    superiores = db.scalars(select(Relacion).where(Relacion.codigo_ric == "contains_or_contained",
                                                   Relacion.destino_id == tunja.id)).all()
    assert len(superiores) == 2


def test_el_guardian_rechaza_una_relacion_que_ric_o_no_admite(db, fondo, admin):
    """CM-19: ninguna ruta puede escribir una fila con dominio o rango ajenos."""
    lugar = vocabulario.crear(db, fondo_id=fondo.id, clase="lugar", nombre="Tunja", subtipo=None, origen="persona",
                              confianza=None, motor=None, usuario_id=admin.id)
    persona = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Ana", subtipo="persona",
                                origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    db.flush()
    db.add(Relacion(origen_tipo="entidad_vocabulario", origen_id=lugar.id, destino_tipo="entidad_vocabulario",
                    destino_id=persona.id, tipo_relacion="procedencia", codigo_ric="has_successor", origen="persona"))
    with pytest.raises(RelacionNoConforme, match="hasSuccessor no admite Place"):
        db.flush()
    db.rollback()


def test_un_subtipo_de_agente_desconocido_se_rechaza_en_la_base(db, fondo, admin):
    """CM-05: la jerarquía de subtipos es una restricción de la base, no solo una tupla de Python."""
    from sqlalchemy.exc import IntegrityError

    vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="X", subtipo="robot", origen="persona",
                      confianza=None, motor=None, usuario_id=admin.id)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
