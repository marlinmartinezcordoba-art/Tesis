"""
Cierre de la auditoría RiC, bloque 4 (vocabularios): VOC-01 a VOC-07 y VOC-09.
"""

import uuid

import pytest
from rdflib import RDF, Literal, Namespace
from sqlalchemy import select, text

from app.db.base import ahora
from app.models.alerta import Alerta
from app.models.descripcion import EntidadVocabulario, IdentificadorEntidad, Relacion, SugerenciaFusion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import autoridad, exportacion_rico, mecanismos, ric_o, vocabulario
from tests.test_autoridad import archivista, ficha, fondo, vincular  # noqa: F401
from tests.test_vocabularios import entidad

RICO = Namespace(ric_o.RICO)
SKOS = Namespace(ric_o.SKOS)


def persona(db, fondo, nombre):
    return entidad(db, fondo, nombre, subtipo="persona")


def exportar(db, fondo, *conectadas):
    """Exporta el fondo con las entidades dadas citadas por un documento publicado."""
    r = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo="Acta", fondo_id=fondo.id,
                          incluido_en_id=fondo.id, publicado_en=ahora())
    db.add(r)
    db.flush()
    for e in conectadas:
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=r.id, destino_tipo="entidad_vocabulario",
                        destino_id=e.id, tipo_relacion="asociacion", codigo_ric="has_or_had_subject", origen="persona"))
    db.commit()
    db.expire_all()
    return exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo


# --- VOC-01 · área de control de ISAAR y nivel de detalle en tres valores ----------------------------


def test_area_de_control_isaar_completa_y_validada(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Secretaría de Gobierno")
    r = cliente.patch(f"/api/vocabulario/{a.id}", headers=archivista, json={
        "estado_elaboracion": "revisado", "institucion_responsable": "Archivo Histórico de Tunja",
        "lenguas": "spa, lat", "escrituras": "Latn", "notas_mantenimiento": "Revisada contra la Gaceta de 1948."})
    assert r.status_code == 200, r.text
    control = ficha(cliente, archivista, a)["ficha"]["control"]
    assert control["estado_elaboracion"] == "revisado" and control["institucion_responsable"].startswith("Archivo")
    assert control["lenguas"] == ["spa", "lat"] and control["escrituras"] == ["Latn"]
    assert control["notas_mantenimiento"].startswith("Revisada")
    for malo in ({"estado_elaboracion": "casi listo"}, {"lenguas": "español"}, {"escrituras": "Latin"}):
        assert cliente.patch(f"/api/vocabulario/{a.id}", headers=archivista, json=malo).status_code == 422, malo


def test_la_base_restringe_estado_de_elaboracion_y_tipo_de_funcion(db, fondo):
    """La lista controlada no vive solo en la API (prueba de profundidad de VOC-01)."""
    a = entidad(db, fondo, "Concejo")
    from sqlalchemy.exc import IntegrityError

    for columna, valor in (("estado_elaboracion", "casi listo"), ("tipo_funcion", "tramite")):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(text(f"UPDATE entidades_vocabulario SET {columna} = :v WHERE id = :i"), {"v": valor, "i": a.id})


# --- VOC-02 · parentesco tipado ----------------------------------------------------------------------


def test_parentesco_tipado_entre_personas_y_su_relacion_en_rico(cliente, db, fondo, archivista):
    padre, hija, hermano = persona(db, fondo, "José Ruiz"), persona(db, fondo, "Ana Ruiz"), persona(db, fondo, "Luis Ruiz")
    alcaldia = entidad(db, fondo, "Alcaldía")
    assert vincular(cliente, archivista, padre, "progenitor_de", hija, fecha_edtf="1920/").status_code == 201
    assert vincular(cliente, archivista, hija, "hermano_de", hermano).status_code == 201
    # El hermano no se declara dos veces al revés; una institución no tiene parientes.
    assert vincular(cliente, archivista, hermano, "hermano_de", hija).status_code == 422
    assert vincular(cliente, archivista, alcaldia, "progenitor_de", hija).status_code == 422
    filas = {r.rol: r for r in db.scalars(select(Relacion).where(Relacion.codigo_ric == "has_family_association_with"))}
    assert set(filas) == {"progenitor", "hermano"}
    g = exportar(db, fondo, padre, hija, hermano)
    u = exportacion_rico.uri
    assert (u(padre.id), RICO.hasFamilyAssociationWith, u(hija.id)) in g
    nodo = u(filas["progenitor"].id)
    assert (nodo, RDF.type, RICO.ChildRelation) in g
    assert (nodo, RICO.relationHasSource, u(padre.id)) in g and (nodo, RICO.relationHasTarget, u(hija.id)) in g
    assert g.value(nodo, RICO.hasBeginningDate) is not None
    assert (u(filas["hermano"].id), RDF.type, RICO.SiblingRelation) in g


# --- VOC-03 y VOC-04 · función ISDF y SKOS completo ------------------------------------------------------


def test_funcion_isdf_con_tipo_codigo_formas_y_control(cliente, db, fondo, archivista):
    gobierno = entidad(db, fondo, "Gobierno municipal", clase="tipo_actividad")
    permisos = entidad(db, fondo, "Gestión de permisos", clase="tipo_actividad")
    autoridad.fijar_concepto_superior(db, permisos, gobierno.id, None)
    db.commit()
    r = cliente.patch(f"/api/vocabulario/{permisos.id}", headers=archivista, json={
        "tipo_funcion": "proceso", "codigo_clasificacion": "200.12", "existencia_edtf": "1946/",
        "historia": "Expedición de permisos de funcionamiento.", "fuentes": "Acuerdo 12 de 1946.",
        "estado_elaboracion": "definitivo"})
    assert r.status_code == 200, r.text
    assert cliente.post(f"/api/vocabulario/{permisos.id}/nombres", headers=archivista,
                        json={"tipo": "otra", "nombre": "Licencias"}).status_code == 201
    assert cliente.patch(f"/api/vocabulario/{permisos.id}", headers=archivista,
                         json={"tipo_funcion": "tramite"}).status_code == 422
    f = ficha(cliente, archivista, permisos)["ficha"]
    assert f["campos"]["codigo_clasificacion"] == "200.12" and f["control"]["nivel_detalle"] == "completo"
    assert f["control"]["reglas"].startswith("ISDF")
    g = exportar(db, fondo, gobierno, permisos)
    s, sup = exportacion_rico.uri(permisos.id), exportacion_rico.uri(gobierno.id)
    assert (s, SKOS.notation, Literal("200.12")) in g
    assert (s, SKOS.scopeNote, Literal("Expedición de permisos de funcionamiento.")) in g
    assert (s, SKOS.altLabel, Literal("Licencias")) in g
    assert (sup, SKOS.narrower, s) in g and (s, SKOS.broader, sup) in g  # narrower explícito


def test_formas_documentales_y_tipos_de_parte_en_su_esquema_skos(db, fondo):
    oficio = entidad(db, fondo, "Oficio", clase="forma_documental")
    sello = entidad(db, fondo, "Sello", clase="tipo_parte")
    g = exportar(db, fondo, oficio, sello)
    for e, clave in ((oficio, "formas-documentales"), (sello, "tipos-de-parte")):
        esquema = exportacion_rico.uri(fondo.id, clave)
        assert (exportacion_rico.uri(e.id), SKOS.inScheme, esquema) in g
        assert (esquema, RDF.type, SKOS.ConceptScheme) in g


# --- VOC-05 · duplicados por otra forma del nombre y por identificador ------------------------------------


def test_mismo_identificador_externo_se_sugiere_aunque_el_nombre_no_se_parezca(db, fondo, admin):
    a = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    b = entidad(db, fondo, "Municipio de Tunja, Boyacá")
    for e in (a, b):
        autoridad.agregar_identificador(db, e, esquema="wikidata", valor="Q1000000", usuario_id=admin.id)
    db.commit()
    assert vocabulario.detectar_candidatos(db, fondo.id) >= 1
    [s] = db.scalars(select(SugerenciaFusion).where(SugerenciaFusion.motivo == "identificador")).all()
    assert {s.entidad_a_id, s.entidad_b_id} == {a.id, b.id} and s.similitud == 1.0


def test_otra_forma_del_nombre_lleva_a_sugerir_la_fusion(db, fondo, admin):
    a = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    b = entidad(db, fondo, "Cabildo de Tunja")
    autoridad.agregar_nombre(db, a, tipo="otra", nombre="Cabildo de Tunja", idioma=None, regla=None,
                             vigencia_edtf=None, usuario_id=admin.id)
    db.commit()
    vocabulario.detectar_candidatos(db, fondo.id)
    [s] = db.scalars(select(SugerenciaFusion)).all()
    assert s.motivo == "otra_forma" and s.similitud == 1.0


@pytest.mark.parametrize("clase", ["agente", "lugar", "tipo_actividad", "actividad", "mandato", "forma_documental"])
def test_verificacion_y_deteccion_en_cada_uno_de_los_seis_tipos(db, fondo, clase):
    """VOC-09: el prompt pide cubrir los seis tipos reutilizables, no solo agentes."""
    a = entidad(db, fondo, "Expedición de licencias de construcción", clase=clase)
    b = entidad(db, fondo, "Expedicion de licencias de construccion", clase=clase)  # sin tildes: la misma
    otra = entidad(db, fondo, "Archivo general", clase=clase)
    vistas = {x.id for x in vocabulario.verificar(db, fondo.id, clase, "Expedición de licencias de construcción")}
    assert {a.id, b.id} <= vistas and otra.id not in vistas
    assert vocabulario.detectar_candidatos(db, fondo.id) == 1
    [s] = db.scalars(select(SugerenciaFusion)).all()
    assert s.clase == clase


# --- VOC-06 · relaciones con vigencia, nota y rol en el RDF --------------------------------------------


def test_relaciones_fechadas_salen_como_nodo_de_relacion_con_su_clase(cliente, db, fondo, archivista):
    alcaldia, secretaria = entidad(db, fondo, "Alcaldía"), entidad(db, fondo, "Secretaría de Gobierno")
    ley = entidad(db, fondo, "Ley 4 de 1913", clase="mandato")
    decreto = entidad(db, fondo, "Decreto 12 de 1948", clase="mandato")
    assert vincular(cliente, archivista, alcaldia, "subordinado", secretaria, fecha_edtf="1948/1990",
                    nota="Por el Acuerdo 12.").status_code == 201
    assert vincular(cliente, archivista, decreto, "mandato_superior", ley).status_code == 201
    assert vincular(cliente, archivista, alcaldia, "creado_por", ley).status_code == 201
    filas = {(r.codigo_ric, r.rol): r for r in db.scalars(select(Relacion).where(Relacion.estado == "vigente"))}
    g = exportar(db, fondo, alcaldia, secretaria, ley, decreto)
    u = exportacion_rico.uri
    sub = u(filas[("has_or_had_subordinate", None)].id)
    assert (sub, RDF.type, RICO.AgentHierarchicalRelation) in g
    assert g.value(sub, RICO.hasBeginningDate) is not None and g.value(sub, RICO.hasEndDate) is not None
    assert (sub, RICO.generalDescription, Literal("Por el Acuerdo 12.")) in g
    jer = u(filas[("regulates_or_regulated", "jerarquia_normativa")].id)
    assert (jer, RDF.type, RICO.RuleRelation) in g
    assert (jer, RICO.generalDescription, Literal("Rol: jerarquia normativa")) in g
    assert (u(filas[("authorizes", "creacion")].id), RDF.type, RICO.MandateRelation) in g
    assert ric_o.verificar_contra_owl() == []


# --- VOC-07 · mecanismo sin versión: no se inventa ---------------------------------------------------------


def test_mecanismo_sin_version_queda_vacio_marcado_y_con_alerta(cliente, db, fondo, archivista):
    m = mecanismos.obtener(db, fondo.id, "Conversor X", None)
    otra = mecanismos.obtener(db, fondo.id, "Conversor X", "")
    db.commit()
    assert m.id == otra.id and m.version is None and m.nombre == "Conversor X"
    assert ficha(cliente, archivista, m)["ficha"]["falta_version"] is True
    assert db.scalar(select(Alerta).where(Alerta.tipo == "mecanismo_sin_version", Alerta.entidad_id == str(m.id)))
    assert mecanismos.version_siegfried("salida inesperada") == ("Siegfried", "salida inesperada")
    assert mecanismos.version_siegfried("") == ("Siegfried", None)
    # Con versión, es otro mecanismo.
    assert mecanismos.obtener(db, fondo.id, "Conversor X", "2.1").id != m.id
