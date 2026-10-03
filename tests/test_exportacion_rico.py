"""
Exportación RiC-O 1.1 (RDF), conformidad (OWL + SHACL) y resolución de URI.
"""

import json
import uuid

import pytest
from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic
from sqlalchemy import select

from app.db.base import ahora
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import EntidadVocabulario, Fecha, Relacion
from app.models.preservacion import DeclaracionDerechos
from app.models.recurso_documental import RecursoDocumental
from app.servicios import autoridad, conformidad_rico, exportacion_rico, parametros, ric_o, vocabulario
from tests.conftest import crear_usuario, ingresar
from tests.test_instrumentos import FRAGMENTO_SECRETO, MOTOR_SECRETO, _recurso, archivista, fondo_descrito  # noqa: F401

RICO = Namespace(ric_o.RICO)
RST = Namespace(ric_o.RST)
SKOS = Namespace(ric_o.SKOS)


def u(ident) -> URIRef:
    return exportacion_rico.uri(ident)


@pytest.fixture()
def fondo_rico(db, fondo_descrito, admin):
    """El fondo descrito de instrumentos, con el contexto que RiC-O permite
    expresar: sección y subserie, parte documental, idioma, lugar con
    coordenadas y tipo, función con su función superior, actividad,
    mandato, hito, otra forma del nombre e identificador de Wikidata."""
    f = fondo_descrito
    fondo, o114 = f["fondo"], f["o114"]
    seccion = _recurso(db, "seccion", "Despacho del alcalde", fondo, fondo)
    subserie = _recurso(db, "subserie", "Oficios", f["serie"], fondo)
    o114.idiomas = ["spa", "lat"]
    o114.condiciones_acceso = "Consulta libre en sala."
    sello = vocabulario.crear(db, fondo_id=fondo.id, clase="tipo_parte", nombre="Sello", subtipo=None,
                              origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    db.flush()
    parte = RecursoDocumental(id=uuid.uuid4(), nivel="parte_documental", titulo="Sello de la Alcaldía", fondo_id=fondo.id,
                              incluido_en_id=o114.id, publicado_en=ahora(), tipo_parte_id=sello.id)
    db.add(parte)
    tunja = vocabulario.crear(db, fondo_id=fondo.id, clase="lugar", nombre="Tunja", subtipo=None, origen="persona",
                              confianza=None, motor=None, usuario_id=admin.id)
    tunja.latitud, tunja.longitud, tunja.tipo_lugar = 5.5353, -73.3678, "municipio"
    funcion = vocabulario.crear(db, fondo_id=fondo.id, clase="tipo_actividad", nombre="Gobierno municipal",
                                subtipo=None, origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    policia = vocabulario.crear(db, fondo_id=fondo.id, clase="tipo_actividad", nombre="Policía local", subtipo=None,
                                origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    actividad = vocabulario.crear(db, fondo_id=fondo.id, clase="actividad", nombre="Expedición de permisos de 1948",
                                  subtipo=None, origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    acuerdo = vocabulario.crear(db, fondo_id=fondo.id, clase="mandato", nombre="Acuerdo 12 de 1946", subtipo="acuerdo",
                                origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    db.flush()
    autoridad.fijar_concepto_superior(db, policia, funcion.id, admin.id)
    alcaldia = f["alcaldia"]
    alcaldia.historia, alcaldia.estatuto_juridico, alcaldia.existencia_edtf = "Creada en 1539.", "publica", "1539/.."
    alcaldia.estructura = "Despacho y secretarías."
    autoridad.agregar_nombre(db, alcaldia, tipo="otra", nombre="Cabildo de Tunja", idioma=None, regla=None,
                             vigencia_edtf="1539/1821", usuario_id=admin.id)
    autoridad.agregar_identificador(db, alcaldia, esquema="wikidata", valor="Q1000000", usuario_id=admin.id)
    autoridad.agregar_hito(db, alcaldia, tipo="reforma", descripcion="Reforma administrativa", edtf="1946",
                           usuario_id=admin.id)
    for origen, o_tipo, destino, d_tipo, codigo in (
            (o114.id, "recurso_documental", actividad.id, "entidad_vocabulario", "documents"),
            (actividad.id, "entidad_vocabulario", policia.id, "entidad_vocabulario", "has_activity_type"),
            (alcaldia.id, "entidad_vocabulario", actividad.id, "entidad_vocabulario", "performs_or_performed"),
            (acuerdo.id, "entidad_vocabulario", actividad.id, "entidad_vocabulario", "regulates_or_regulated"),
            (tunja.id, "entidad_vocabulario", alcaldia.id, "entidad_vocabulario", "is_or_was_location_of")):
        db.add(Relacion(origen_tipo=o_tipo, origen_id=origen, destino_tipo=d_tipo, destino_id=destino,
                        tipo_relacion="asociacion", codigo_ric=codigo, origen="motor", confianza=0.5, motor=MOTOR_SECRETO,
                        fragmento=FRAGMENTO_SECRETO))
    fecha = Fecha(id=uuid.uuid4(), expresion="hacia 1948", edtf="1948~", subtipo="simple", calendario="juliano",
                  origen="persona")
    db.add(fecha)
    db.flush()
    db.add(Relacion(origen_tipo="fecha", origen_id=fecha.id, destino_tipo="recurso_documental", destino_id=f["o115"].id,
                    tipo_relacion="temporal", codigo_ric="is_creation_date_of", origen="persona"))
    # Un mecanismo del fondo: nunca se exporta.
    vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="Motor de análisis", version="gemini-2.5-flash")
    db.commit()
    return f | {"seccion": seccion, "subserie": subserie, "parte": parte, "tunja": tunja, "funcion": funcion,
                "policia": policia, "actividad": actividad, "acuerdo": acuerdo, "fecha": fecha, "sello": sello}


def exportar(db, f, **kw):
    db.expire_all()
    return exportacion_rico.exportar(db, db.get(RecursoDocumental, f["fondo"].id), **kw)


# --- Contenido -----------------------------------------------------------------------------------


def test_cada_nivel_con_su_clase_y_su_tipo_de_agrupacion(db, fondo_rico):
    f = fondo_rico
    g = exportar(db, f).grafo
    assert (u(f["fondo"].id), RDF.type, RICO.RecordSet) in g
    assert (u(f["fondo"].id), RICO.hasRecordSetType, RST.Fonds) in g
    assert (u(f["serie"].id), RICO.hasRecordSetType, RST.Series) in g
    assert (u(f["exp48"].id), RICO.hasRecordSetType, RST.File) in g
    # Sección y subserie: conceptos propios con skos:broadMatch al oficial más cercano.
    tipo_seccion = g.value(u(f["seccion"].id), RICO.hasRecordSetType)
    assert (tipo_seccion, RDF.type, RICO.RecordSetType) in g and (tipo_seccion, SKOS.broadMatch, RST.Fonds) in g
    assert (g.value(u(f["subserie"].id), RICO.hasRecordSetType), SKOS.broadMatch, RST.Series) in g
    assert (u(f["o114"].id), RDF.type, RICO.Record) in g
    assert (u(f["parte"].id), RDF.type, RICO.RecordPart) in g
    # Jerarquía: inclusión (R024) y parte constitutiva (R003), no al revés.
    assert (u(f["serie"].id), RICO.includesOrIncluded, u(f["exp48"].id)) in g
    assert (u(f["exp48"].id), RICO.includesOrIncluded, u(f["o114"].id)) in g
    assert (u(f["o114"].id), RICO.hasOrHadConstituent, u(f["parte"].id)) in g
    assert (u(f["parte"].id), RICO.hasDocumentaryFormType, u(f["sello"].id)) in g
    assert (u(f["o114"].id), RICO.title, Literal("Oficio N.º 114")) in g
    assert (u(f["o114"].id), RICO.identifier, Literal("CO-AM-114")) in g
    assert (u(f["o114"].id), RICO.conditionsOfAccess, Literal("Consulta libre en sala.")) in g


def test_idioma_iso_639_3_con_la_propiedad_de_cada_clase(db, fondo_rico):
    f = fondo_rico
    g = exportar(db, f).grafo
    [espanol] = [i for i in g.objects(u(f["o114"].id), RICO.hasOrHadLanguage)
                 if (i, RICO.identifier, Literal("spa")) in g]
    assert (espanol, RDF.type, RICO.Language) in g
    assert (espanol, SKOS.exactMatch, URIRef("http://lexvo.org/id/iso639-3/spa")) in g
    assert len(set(g.objects(u(f["o114"].id), RICO.hasOrHadLanguage))) == 2


def test_contexto_agentes_lugar_funciones_actividad_mandato(db, fondo_rico):
    f = fondo_rico
    g = exportar(db, f).grafo
    alcaldia = u(f["alcaldia"].id)
    assert (u(f["o114"].id), RICO.hasCreator, alcaldia) in g
    assert (alcaldia, RDF.type, RICO.CorporateBody) in g and (alcaldia, RICO.name, Literal("Alcaldía Municipal")) in g
    assert (alcaldia, RICO.history, Literal("Creada en 1539.")) in g
    assert (alcaldia, OWL.sameAs, URIRef("https://www.wikidata.org/entity/Q1000000")) in g
    nombre = g.value(alcaldia, RICO.hasOrHadAgentName)
    assert (nombre, RDF.type, RICO.AgentName) in g and (nombre, RICO.textualValue, Literal("Cabildo de Tunja")) in g
    inicio = g.value(alcaldia, RICO.hasBeginningDate)
    assert (inicio, RICO.normalizedDateValue, Literal("1539")) in g
    [hito] = list(g.subjects(RICO.affectsOrAffected, alcaldia))
    assert (hito, RDF.type, RICO.Event) in g
    tunja = u(f["tunja"].id)
    assert (tunja, RICO.geographicalCoordinates, Literal("5.535300, -73.367800")) in g
    assert (g.value(tunja, RICO.hasOrHadPlaceType), RDF.type, RICO.PlaceType) in g
    assert (tunja, RICO.isOrWasLocationOf, alcaldia) in g
    actividad, policia, funcion = u(f["actividad"].id), u(f["policia"].id), u(f["funcion"].id)
    assert (u(f["o114"].id), RICO.documents, actividad) in g
    assert (actividad, RICO.hasActivityType, policia) in g and (alcaldia, RICO.performsOrPerformed, actividad) in g
    # El árbol de funciones es SKOS: la función superior también se exporta aunque nadie la cite.
    assert (policia, SKOS.broader, funcion) in g and (funcion, RDF.type, SKOS.Concept) in g
    assert (funcion, SKOS.inScheme, g.value(policia, SKOS.inScheme)) in g
    acuerdo = u(f["acuerdo"].id)
    assert (acuerdo, RICO.regulatesOrRegulated, actividad) in g
    assert (g.value(acuerdo, RICO.hasOrHadMandateType), RDF.type, RICO.MandateType) in g
    fecha = u(f["fecha"].id)
    assert (fecha, RICO.normalizedDateValue, Literal("1948~")) in g and (fecha, RICO.dateQualifier, Literal("aproximada")) in g


def test_no_sale_nada_interno_ni_borradores_ni_mecanismos(db, fondo_rico):
    f = fondo_rico
    ex = exportar(db, f)
    texto = exportacion_rico.serializar(ex.grafo, "turtle").decode()
    assert MOTOR_SECRETO not in texto and FRAGMENTO_SECRETO not in texto
    assert "Borrador" not in texto and "gemini-2.5-flash" not in texto and "Motor de análisis" not in texto
    assert "0.93" not in texto and "0.41" not in texto  # confianzas
    # Lo que RiC-O no puede decir queda contado, no se inventa.
    assert ex.omitidas["borradores sin publicar"] == 1
    assert ex.omitidas["estructura interna de un agente (sin propiedad en RiC-O)"] == 1
    assert ex.omitidas["calendario distinto del gregoriano (sin propiedad en RiC-O)"] == 1
    assert "Despacho y secretarías" not in texto and "juliano" not in texto


def test_lo_clasificado_o_reservado_no_se_exporta_por_defecto(db, fondo_rico, admin):
    f = fondo_rico
    db.add(DeclaracionDerechos(fondo_id=f["fondo"].id, entidad_tipo="recurso_documental", entidad_id=f["exp48"].id,
                               base="estatuto", acceso="reservado", reproduccion="no_permitida",
                               fundamento="Ley 1712 de 2014, art. 19", creada_por_id=admin.id))
    db.commit()
    ex = exportar(db, f)
    assert (u(f["exp48"].id), RDF.type, None) not in ex.grafo
    assert (u(f["o114"].id), RDF.type, None) not in ex.grafo  # hereda la reserva del expediente
    assert (u(f["exp49"].id), RDF.type, RICO.RecordSet) in ex.grafo
    assert ex.omitidas["descripciones con acceso clasificado o reservado"] == 4  # expediente, dos oficios y la parte
    completo = exportar(db, f, incluir_restringidos=True)
    assert (u(f["o114"].id), RDF.type, RICO.Record) in completo.grafo


def test_turtle_y_json_ld_dicen_lo_mismo(db, fondo_rico):
    g = exportar(db, fondo_rico).grafo
    de_turtle = Graph().parse(data=exportacion_rico.serializar(g, "turtle"), format="turtle")
    de_jsonld = Graph().parse(data=exportacion_rico.serializar(g, "jsonld"), format="json-ld")
    assert isomorphic(de_turtle, de_jsonld) and isomorphic(de_turtle, g)


# --- Conformidad ---------------------------------------------------------------------------------


def test_la_exportacion_es_conforme_al_owl_y_al_perfil_shacl(db, fondo_rico):
    reporte = conformidad_rico.reporte(exportar(db, fondo_rico))
    assert reporte["owl"]["problemas"] == []
    assert reporte["shacl"]["conforme"], reporte["shacl"]["resultados"]
    assert reporte["conforme"] and reporte["mapeo"]["problemas"] == []
    assert reporte["por_clase"]["Record"] == 2 and reporte["por_clase"]["RecordPart"] == 1


@pytest.mark.parametrize("romper,esperado", [
    ("sin_titulo", "rico:title"),
    ("relacion_a_clase_ajena", "relacion-has_creator"),
    ("edtf_invalido", "rico:normalizedDateValue"),
    ("idioma_no_iso", "rico:identifier"),
    ("parte_suelta", None),
])
def test_shacl_detecta_lo_que_no_cumple(db, fondo_rico, romper, esperado):
    f = fondo_rico
    g = exportar(db, f).grafo
    if romper == "sin_titulo":
        g.remove((u(f["o115"].id), RICO.title, None))
    elif romper == "relacion_a_clase_ajena":
        g.add((u(f["o115"].id), RICO.hasCreator, u(f["tunja"].id)))  # un lugar no produce documentos
    elif romper == "edtf_invalido":
        g.set((u(f["fecha"].id), RICO.normalizedDateValue, Literal("marzo de 1948")))
    elif romper == "idioma_no_iso":
        idioma = next(g.objects(u(f["o114"].id), RICO.hasOrHadLanguage))
        g.set((idioma, RICO.identifier, Literal("español")))
    elif romper == "parte_suelta":
        g.remove((u(f["o114"].id), RICO.hasOrHadConstituent, u(f["parte"].id)))
    r = conformidad_rico.validar_shacl(g)
    assert not r["conforme"]
    if esperado:
        assert any(esperado in ((x["ruta"] or "") + (x["forma"] or "")) for x in r["resultados"]), r["resultados"]


def test_la_verificacion_owl_es_independiente_del_mapeo(db, fondo_rico):
    f = fondo_rico
    g = exportar(db, f).grafo
    g.add((u(f["tunja"].id), RICO.scopeAndContent, Literal("x")))  # dominio: RecordResource, no Place
    g.add((u(f["o114"].id), RICO.inventadaPorRicora, Literal("x")))
    g.add((u(f["o114"].id), URIRef("https://ricora.local/interno#confianza"), Literal(0.9)))
    problemas = conformidad_rico.verificar_owl(g)
    assert any("scopeAndContent" in p and "dominio" in p for p in problemas)
    assert any("inventadaPorRicora" in p for p in problemas)
    assert any("fuera de los vocabularios" in p for p in problemas)


# --- API y URI ---------------------------------------------------------------------------------------


def test_descarga_del_fondo_queda_en_auditoria(cliente, db, fondo_rico, archivista):
    f = fondo_rico
    r = cliente.get("/api/exportacion/rdf", headers=archivista, params={"fondo_id": str(f["fondo"].id)})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/turtle")
    assert "attachment" in r.headers["content-disposition"]
    Graph().parse(data=r.content, format="turtle")
    r = cliente.get("/api/exportacion/rdf", headers=archivista, params={"fondo_id": str(f["fondo"].id), "formato": "jsonld"})
    assert r.headers["content-type"].startswith("application/ld+json")
    json.loads(r.content)
    eventos = db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "rdf_exportado")).all()
    assert [e.valor_nuevo["formato"] for e in eventos] == ["turtle", "jsonld"]
    rep = cliente.get("/api/exportacion/conformidad", headers=archivista, params={"fondo_id": str(f["fondo"].id)}).json()
    assert rep["conforme"] and rep["uris_publicas"] is False
    assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "conformidad_rico_validada"))


def test_incluir_lo_reservado_exige_permiso_de_escritura(cliente, db, fondo_rico):
    crear_usuario(db, "revisor@correo.com", "revisor")
    revisor = ingresar(cliente, "revisor@correo.com")
    r = cliente.get("/api/exportacion/rdf", headers=revisor,
                    params={"fondo_id": str(fondo_rico["fondo"].id), "incluir_restringidos": True})
    assert r.status_code == 403


def test_las_uri_se_resuelven_con_negociacion_de_contenido(cliente, db, fondo_rico, archivista, cabeceras_admin):
    f = fondo_rico
    ruta = f"/id/{f['o114'].id}"
    # Apagado por defecto: sin sesión, 401; con sesión, la descripción.
    assert cliente.get(ruta).status_code == 401
    r = cliente.get(ruta, headers=archivista | {"Accept": "text/turtle"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/turtle")
    g = Graph().parse(data=r.content, format="turtle")
    assert (u(f["o114"].id), RICO.hasCreator, u(f["alcaldia"].id)) in g
    assert (u(f["alcaldia"].id), RDFS.label, Literal("Alcaldía Municipal")) in g  # la etiqueta del nodo citado
    assert (u(f["exp48"].id), RICO.includesOrIncluded, u(f["o114"].id)) in g  # lo que apunta a él
    # Solo el administrador lo enciende.
    assert cliente.put("/api/exportacion/uris-publicas", headers=archivista, json={"publicas": True}).status_code == 403
    assert cliente.put("/api/exportacion/uris-publicas", headers=cabeceras_admin, json={"publicas": True}).status_code == 200
    r = cliente.get(ruta, headers={"Accept": "application/ld+json"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/ld+json")
    assert isomorphic(Graph().parse(data=r.content, format="json-ld"), g)
    assert cliente.get(ruta + ".ttl").headers["content-type"].startswith("text/turtle")
    # Un nodo de apoyo (otra forma del nombre) y un concepto del fondo también se resuelven.
    nombre = next(Graph().parse(data=cliente.get(f"/id/{f['alcaldia'].id}").content, format="turtle")
                  .objects(u(f["alcaldia"].id), RICO.hasOrHadAgentName))
    assert cliente.get(str(nombre).replace(exportacion_rico.base(), "/id/")).status_code == 200
    # Lo no publicado, lo inexistente y el mecanismo: 404.
    borrador = db.scalar(select(RecursoDocumental).where(RecursoDocumental.titulo == "Borrador"))
    mecanismo = db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.subtipo == "mecanismo"))
    for ident in (borrador.id, uuid.uuid4(), mecanismo.id):
        assert cliente.get(f"/id/{ident}").status_code == 404
    assert cliente.get("/id/no-es-un-uuid").status_code == 404
    assert parametros.leer(db, "rdf_uris_publicas") is True


def test_con_uris_publicas_lo_reservado_sigue_sin_resolverse(cliente, db, fondo_rico, admin):
    f = fondo_rico
    parametros.cambiar(db, "rdf_uris_publicas", True, admin.id, "instrumentos")
    db.add(DeclaracionDerechos(fondo_id=f["fondo"].id, entidad_tipo="recurso_documental", entidad_id=f["o114"].id,
                               base="estatuto", acceso="clasificado", reproduccion="no_permitida",
                               fundamento="Ley 1712 de 2014, art. 18", creada_por_id=admin.id))
    db.commit()
    assert cliente.get(f"/id/{f['o114'].id}").status_code == 404
    assert cliente.get(f"/id/{f['o115'].id}").status_code == 200


def test_la_uri_de_una_entidad_fusionada_redirige_a_la_definitiva(cliente, db, fondo_rico, archivista, admin):
    f = fondo_rico
    duplicada = vocabulario.crear(db, fondo_id=f["fondo"].id, clase="agente", nombre="Alcaldía Mpal.",
                                  subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None,
                                  usuario_id=admin.id)
    db.commit()
    vocabulario.fusionar(db, definitiva=f["alcaldia"], absorbida=duplicada, usuario_id=admin.id)
    db.commit()
    r = cliente.get(f"/id/{duplicada.id}.jsonld", headers=archivista, follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/id/{f['alcaldia'].id}.jsonld"
