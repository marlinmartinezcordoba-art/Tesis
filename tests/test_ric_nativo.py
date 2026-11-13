"""
RICORA nativo en RiC (documentacion/ric-nativo.md).

Criterio 7 · La historia de la descripción también es RiC: cada relación se
asocia (rico:isAssociatedWithEvent) a la actividad que la produjo. La
propuesta del motor es una rico:Activity que ejerce el motor como
rico:Mechanism con su versión; la validación o la corrección es otra
actividad, ejercida por la archivista: por su cargo (rico:Position) en el
grafo público y, además, por su nombre (rico:Person) en el completo.
Todo pasa la validación OWL y el perfil SHACL, y se consulta con SPARQL.
"""

from rdflib import RDF, Literal

from app.servicios import conformidad_rico, exportacion_rico, mecanismos
from tests.test_especializacion_ric import RICO, agente, documento, exportar_conforme, relacion, u
from tests.test_preservacion import archivista, fondo, herramientas  # noqa: F401  (fixtures)

AUTORIA = """
PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
SELECT ?relacion ?actividad ?nombre ?agente ?clase WHERE {
  ?relacion rico:isAssociatedWithEvent ?actividad .
  ?actividad rico:name ?nombre .
  ?agente rico:performsOrPerformed ?actividad ; a ?clase .
}"""


def test_la_autoria_de_cada_relacion_esta_en_el_grafo(db, fondo, admin):
    doc = documento(db, fondo)
    motor = mecanismos.del_motor(db, fondo.id, "motor-de-prueba-2.0")
    propuesta = relacion(db, doc, agente(db, fondo, "Alcaldía Municipal de Tunja", "entidad_corporativa"), "has_creator",
                         origen="motor", confianza=0.9, motor="motor-de-prueba-2.0", motor_id=motor.id,
                         confirmada_por_id=admin.id)
    corregida = relacion(db, doc, agente(db, fondo, "Concejo Municipal", "entidad_corporativa"), "has_addressee",
                         origen="motor_editado", confianza=0.7, motor="motor-de-prueba-2.0", motor_id=motor.id,
                         confirmada_por_id=admin.id)
    manual = relacion(db, doc, agente(db, fondo, "Personero"), "has_or_had_subject", confirmada_por_id=admin.id)

    g = exportar_conforme(db, fondo).grafo  # público
    # El motor es un rico:Mechanism con su versión, y ejerce la actividad de la propuesta.
    assert (u(motor.id), RDF.type, RICO.Mechanism) in g
    assert (u(motor.id), RICO.technicalCharacteristics, Literal("motor-de-prueba-2.0")) in g  # RiC-A41
    act = u(f"{propuesta.id}/propuesta")
    assert (act, RDF.type, RICO.Activity) in g and (u(motor.id), RICO.performsOrPerformed, act) in g
    assert (act, RICO.affectsOrAffected, u(doc.id)) in g
    assert (u(propuesta.id), RICO.isAssociatedWithEvent, act) in g
    # La validación humana: en el público, por el cargo, sin el nombre de la persona.
    validacion = u(f"{doc.id}/autoria/validacion")
    cargo = u(f"{fondo.id}/cargo/archivista")
    assert (u(propuesta.id), RICO.isAssociatedWithEvent, validacion) in g
    assert (cargo, RDF.type, RICO.Position) in g and (cargo, RICO.performsOrPerformed, validacion) in g
    assert not any(True for _ in g.subjects(RDF.type, RICO.Person) if admin.nombre in str(g.value(_, RICO.name)))
    # La corrección y la descripción manual, cada una con su actividad.
    assert (u(corregida.id), RICO.isAssociatedWithEvent, u(f"{doc.id}/autoria/correccion")) in g
    assert (u(manual.id), RICO.isAssociatedWithEvent, u(f"{doc.id}/autoria/manual")) in g
    assert (u(manual.id), RICO.isAssociatedWithEvent, act) not in g

    # La pregunta que el grafo debe responder: quién afirmó cada relación.
    filas = {(str(r.relacion), str(r.clase).split("#")[-1]) for r in g.query(AUTORIA)}
    assert (str(u(propuesta.id)), "Mechanism") in filas and (str(u(propuesta.id)), "Position") in filas
    assert (str(u(manual.id)), "Position") in filas and (str(u(manual.id)), "Mechanism") not in filas

    # En el completo, la persona que validó, con su nombre y el cargo que ocupa.
    completo = exportacion_rico.exportar(db, fondo, incluir_restringidos=True)
    reporte = conformidad_rico.reporte(completo)
    assert reporte["owl"]["problemas"] == [] and reporte["shacl"]["conforme"], reporte["shacl"]["resultados"]
    gc = completo.grafo
    persona = u(f"persona-del-sistema/{admin.id}")
    assert (persona, RDF.type, RICO.Person) in gc and (persona, RICO.occupiesOrOccupied, cargo) in gc
    assert (persona, RICO.performsOrPerformed, validacion) in gc


def test_un_motor_sin_version_no_bloquea_la_publicacion(db, fondo):
    doc = documento(db, fondo)
    motor = mecanismos.del_motor(db, fondo.id, "motor-viejo")
    motor.version = None
    relacion(db, doc, agente(db, fondo, "Tesorero"), "has_or_had_subject", origen="motor", confianza=0.8,
             motor="motor-viejo", motor_id=motor.id)
    ex = exportar_conforme(db, fondo)
    assert (u(motor.id), RDF.type, RICO.Mechanism) not in ex.grafo
    assert any("sin su mecanismo" in k for k in ex.omitidas)


# --- Criterio 1 · Lugares, materias y mandatos son autoridades de la institución ------------------------


def test_un_lugar_es_uno_para_toda_la_institucion_y_se_enlaza_con_geonames_y_wikidata(cliente, db, fondo, admin,  # noqa: F811
                                                                                        archivista):
    import uuid

    from app.models.recurso_documental import RecursoDocumental
    from app.servicios import vocabulario

    otro = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Archivo de la Gobernación")
    otro.fondo_id = otro.id
    db.add(otro)
    tunja = vocabulario.crear(db, fondo_id=fondo.id, clase="lugar", nombre="Tunja", subtipo=None, origen="persona",
                              confianza=None, motor=None, usuario_id=admin.id)
    db.commit()
    # GeoNames (solo lugares, numérico; acepta la URL completa) y Wikidata.
    r = cliente.post(f"/api/vocabulario/{tunja.id}/identificadores", headers=archivista,
                     json={"esquema": "geonames", "valor": "https://www.geonames.org/3666640/tunja.html"})
    assert r.status_code == 201, r.text
    assert cliente.post(f"/api/vocabulario/{tunja.id}/identificadores", headers=archivista,
                        json={"esquema": "wikidata", "valor": "Q193288"}).status_code == 201
    assert cliente.post(f"/api/vocabulario/{tunja.id}/identificadores", headers=archivista,
                        json={"esquema": "geonames", "valor": "Tunja"}).status_code == 422
    persona = agente(db, fondo, "Gustavo Rojas Pinilla")
    db.commit()
    assert cliente.post(f"/api/vocabulario/{persona.id}/identificadores", headers=archivista,
                        json={"esquema": "geonames", "valor": "3666640"}).status_code == 422

    # Un documento del otro fondo cita el mismo Tunja: no se duplica, y su grafo lo exporta con la misma URI.
    doc = documento(db, otro, "Oficio de la Gobernación")
    relacion(db, tunja, doc, "is_or_was_location_of", origen_tipo="entidad_vocabulario",
             destino_tipo="recurso_documental")
    g = exportar_conforme(db, otro).grafo
    from rdflib import OWL, URIRef

    assert (u(tunja.id), RDF.type, RICO.Place) in g
    assert (u(tunja.id), OWL.sameAs, URIRef("https://sws.geonames.org/3666640/")) in g
    assert (u(tunja.id), OWL.sameAs, URIRef("http://www.wikidata.org/entity/Q193288")) in g


# --- Criterio 5 · Una pregunta para todo el acervo --------------------------------------------------------


def test_sparql_sobre_todo_el_acervo(cliente, db, admin):
    import uuid

    from app.models.recurso_documental import RecursoDocumental
    from app.servicios import grafo_rdf, parametros
    from tests.test_especializacion_ric import documento as doc_de

    fondos = []
    for titulo, oficio in (("Alcaldía de Tunja", "Oficio de Tunja"), ("Gobernación de Boyacá", "Oficio de Boyacá")):
        f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo=titulo, publicado_en=__import__("app.db.base",
                              fromlist=["ahora"]).ahora())
        f.fondo_id = f.id
        db.add(f)
        db.flush()
        doc_de(db, f, oficio)
        fondos.append(f)
    db.commit()
    consulta = "PREFIX rico: <https://www.ica.org/standards/RiC/ontology#> SELECT ?t WHERE { ?r a rico:Record ; rico:title ?t }"
    # Sin la publicación abierta, la consulta pide sesión, igual que la de un fondo.
    assert cliente.get("/api/publico/sparql", params={"query": consulta}).status_code == 401
    parametros.cambiar(db, "rdf_uris_publicas", True, admin.id, "instrumentos")
    db.commit()
    for f in fondos:
        grafo_rdf.al_dia(db, f, "publico")
    db.commit()
    r = cliente.get("/api/publico/sparql", params={"query": consulta})
    assert r.status_code == 200, r.text
    titulos = {b["t"]["value"] for b in r.json()["results"]["bindings"]}
    assert {"Oficio de Tunja", "Oficio de Boyacá"} <= titulos  # una sola pregunta, los dos fondos
    # Con fondo, como antes: solo el suyo.
    r = cliente.get("/api/publico/sparql", params={"query": consulta, "fondo_id": str(fondos[0].id)})
    assert {b["t"]["value"] for b in r.json()["results"]["bindings"]} == {"Oficio de Tunja"}
    assert cliente.get("/api/publico/sparql", params={"query": "DROP ALL"}).status_code in (400, 403)


# --- La URI de una entidad, legible para una persona ------------------------------------------------------


def test_la_uri_entrega_una_pagina_web_a_una_persona_y_rico_a_una_maquina(cliente, db, fondo, admin, cabeceras_admin):
    doc = documento(db, fondo, "Oficio 301 de 1949")
    motor = mecanismos.del_motor(db, fondo.id, "motor-de-prueba-2.0")
    alcaldia = agente(db, fondo, "Alcaldía Municipal de Tunja", "entidad_corporativa")
    relacion(db, doc, alcaldia, "has_creator", origen="motor", confianza=0.9, motor="motor-de-prueba-2.0",
             motor_id=motor.id, confirmada_por_id=admin.id)
    db.commit()
    from app.servicios import grafo_rdf

    grafo_rdf.al_dia(db, fondo, "publico")
    db.commit()
    r = cliente.get(f"/id/{doc.id}", headers=cabeceras_admin | {"Accept": "text/html,application/xhtml+xml"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), r.text[:300]
    pagina = r.text
    assert "Oficio 301 de 1949" in pagina and "rico:Record" in pagina
    assert "Alcaldía Municipal de Tunja" in pagina and f'href="{exportacion_rico.base()}{alcaldia.id}"' in pagina
    assert "Quién afirmó cada relación" in pagina and "Motor de análisis" in pagina
    assert "tiene como creador a" in pagina and "Relación rico:hasCreator" not in pagina  # legible, no el código
    assert ".ttl" in pagina and ".jsonld" in pagina
    # La misma URI, para una máquina, sigue siendo RiC-O.
    r = cliente.get(f"/id/{doc.id}", headers=cabeceras_admin | {"Accept": "text/turtle"})
    assert r.headers["content-type"].startswith("text/turtle") and "rico:Record" in r.text
    assert cliente.get(f"/id/{doc.id}.jsonld", headers=cabeceras_admin | {"Accept": "text/html"}).headers[
        "content-type"].startswith("application/ld+json")


# --- El sistema demuestra su nivel ------------------------------------------------------------------------


def test_el_panel_de_adopcion_evalua_los_siete_criterios(cliente, db, fondo, admin, cabeceras_admin):
    doc = documento(db, fondo)
    motor = mecanismos.del_motor(db, fondo.id, "motor-de-prueba-2.0")
    relacion(db, doc, agente(db, fondo, "Alcaldía", "entidad_corporativa"), "has_creator", origen="motor",
             confianza=0.9, motor="motor-de-prueba-2.0", motor_id=motor.id, confirmada_por_id=admin.id)
    db.commit()
    r = cliente.get("/api/exportacion/adopcion-ric", headers=cabeceras_admin)
    assert r.status_code == 200, r.text
    a = r.json()
    assert [c["numero"] for c in a["criterios"]] == [1, 2, 3, 4, 5, 6, 7]
    assert a["cumplidos"] == 7 and a["nivel"]["codigo"] == 3 and a["nivel"]["nombre"] == "Sistema nativo en RiC"
    c7 = a["criterios"][6]
    assert "con su mecanismo y su versión: 1" in c7["evidencia"][0] and c7["prueba"].startswith("tests/")
    assert a["cobertura"]["atributos"]["total"] == 42 and a["perfil_agn"]["total"] == 57
    assert len(a["consultas"]) >= 4
    # Cumplir (la capacidad, con su prueba) no es lo mismo que tener casos en el acervo.
    en_uso = {c["numero"]: c["en_uso"] for c in a["criterios"]}
    assert en_uso[2] and en_uso[7] and not en_uso[3] and not en_uso[4]
    # Una relación del motor sin mecanismo registrado deja el criterio 7 parcial, y el nivel baja a conforme.
    motor.version = None
    db.commit()
    a = cliente.get("/api/exportacion/adopcion-ric", headers=cabeceras_admin).json()
    assert a["criterios"][6]["estado"] == "parcial" and a["nivel"]["codigo"] == 2 and a["criterios"][6]["motivo"]
