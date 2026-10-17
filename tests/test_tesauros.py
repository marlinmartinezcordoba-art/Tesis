"""
Tesauros para normalizar las materias de la descripción.

- Importar SKOS (como el Tesauro de la UNESCO) y tablas Excel o CSV (como el
  tesauro ambiental de Minambiente, que no publica SKOS).
- Normalizar: un término no preferente lleva al preferente; sin tildes ni
  mayúsculas; si no coincide, parecidos.
- La materia del fondo es una por concepto: dos documentos con el mismo tema
  escrito distinto quedan en el mismo nodo del grafo, con rico:hasOrHadSubject,
  y la exportación lleva skos:exactMatch al concepto de origen.
"""

import io

from openpyxl import Workbook
from rdflib import RDF, Namespace, URIRef
from sqlalchemy import select

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.tesauro import ConceptoTesauro
from app.servicios import exportacion_rico, tesauros
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import aceptar_todo, documento, eventos, fondo, iniciar, motor_prueba  # noqa: F401
from tests.test_especializacion_ric import exportar_conforme

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")

UNESCO = b"""@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix u: <http://vocabularies.unesco.org/thesaurus/> .
u:scheme a skos:ConceptScheme ; skos:prefLabel "UNESCO Thesaurus"@en .
u:concept1 a skos:Concept ; skos:inScheme u:scheme ;
    skos:prefLabel "Archives"@en, "Archivo hist\xc3\xb3rico"@es ;
    skos:altLabel "Archivos hist\xc3\xb3ricos"@es, "Historical archives"@en ;
    skos:scopeNote "Conjunto de documentos de valor permanente."@es ;
    skos:broader u:concept2 .
u:concept2 a skos:Concept ; skos:prefLabel "Informaci\xc3\xb3n y comunicaci\xc3\xb3n"@es .
u:concept3 a skos:Concept ; skos:prefLabel "Fiestas populares"@es ; skos:altLabel "Festividades"@es .
u:concept4 a skos:Concept ; skos:prefLabel "T\xc3\xa9rmino retirado"@es ; owl:deprecated true .
"""


def _admin_importa(cliente, cab, contenido, archivo, nombre="Tesauro de la UNESCO", **extra):
    return cliente.post("/api/tesauros", headers=cab, files={"archivo": (archivo, contenido)},
                        data={"nombre": nombre, "licencia": "CC BY-SA 3.0 IGO",
                              "fuente": "https://vocabularies.unesco.org/", **extra})


def _excel_ambiental() -> bytes:
    libro = Workbook()
    h = libro.active
    h.append(["Término preferente", "Usado por", "Término general", "Nota de alcance", "Código"])
    h.append(["Recursos hídricos", "Aguas; Recurso hídrico", "", "Agua disponible para uso.", "RH"])
    h.append(["Cuencas hidrográficas", "Cuenca", "Recursos hídricos", None, "RH.1"])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_importar_skos_toma_el_espanol_omite_los_retirados_y_une_el_termino_general(cliente, db, cabeceras_admin):
    r = _admin_importa(cliente, cabeceras_admin, UNESCO, "unesco-thesaurus.ttl")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["conceptos"] == 3 and t["formato"] == "skos" and t["uri_esquema"] == "http://vocabularies.unesco.org/thesaurus/scheme"
    c = db.scalar(select(ConceptoTesauro).where(ConceptoTesauro.uri == "http://vocabularies.unesco.org/thesaurus/concept1"))
    assert c.preferente == "Archivo histórico" and c.nota_alcance.startswith("Conjunto")
    salida = tesauros.concepto_out(db, c)
    assert salida["ruta"] == ["Información y comunicación"] and salida["no_preferentes"] == ["Archivos históricos"]
    # El mismo archivo no se importa dos veces; la archivista no importa.
    assert _admin_importa(cliente, cabeceras_admin, UNESCO, "unesco-thesaurus.ttl").status_code == 409
    crear_usuario(db, "ana@correo.com", "archivista")
    assert _admin_importa(cliente, ingresar(cliente, "ana@correo.com"), UNESCO, "otro.ttl").status_code == 403
    assert len(eventos(db, "tesauro_importado")) == 1


def test_importar_excel_y_csv_de_un_tesauro_sin_skos(cliente, db, cabeceras_admin):
    r = _admin_importa(cliente, cabeceras_admin, _excel_ambiental(), "tesauro-ambiental.xlsx",
                       nombre="Tesauro ambiental (Minambiente)")
    assert r.status_code == 201, r.text
    assert r.json()["formato"] == "excel"
    n = cliente.get("/api/tesauros/normalizar", headers=cabeceras_admin, params={"texto": "cuenca"}).json()
    assert n["exacto"]["preferente"] == "Cuencas hidrográficas" and n["via"] == "no_preferente"
    assert n["exacto"]["ruta"] == ["Recursos hídricos"] and n["exacto"]["notacion"] == "RH.1"
    csv = "Término preferente;Usado por\nPáramos;Páramo\n".encode()
    r = _admin_importa(cliente, cabeceras_admin, csv, "paramos.csv", nombre="Ecosistemas")
    assert r.status_code == 201 and r.json()["conceptos"] == 1
    sin_columna = "Nombre;Otra\nx;y\n".encode()
    r = _admin_importa(cliente, cabeceras_admin, sin_columna, "malo.csv", nombre="Malo")
    assert r.status_code == 422 and "Término preferente" in r.json()["detail"]


def test_normalizar_lleva_el_no_preferente_al_preferente_y_ofrece_parecidos(cliente, db, cabeceras_admin):
    _admin_importa(cliente, cabeceras_admin, UNESCO, "unesco.ttl")
    q = lambda t: cliente.get("/api/tesauros/normalizar", headers=cabeceras_admin, params={"texto": t}).json()  # noqa: E731
    assert q("ARCHIVO HISTORICO")["via"] == "preferente"  # sin tildes ni mayúsculas
    n = q("archivos históricos")
    assert n["via"] == "no_preferente" and n["exacto"]["preferente"] == "Archivo histórico"
    assert n["exacto"]["etiqueta_coincidente"] == "Archivos históricos"
    n = q("fiestas popular")
    assert n["exacto"] is None and n["parecidos"][0]["preferente"] == "Fiestas populares"
    assert q("término retirado")["exacto"] is None  # los retirados no se importan


def _publicar_con_materia(cliente, db, fondo, cab, nombre, texto, **materia):  # noqa: F811
    d = documento(db, fondo, nombre, "Oficio 114 de 1948. Informe de las fiestas populares de Tunja.")
    espacio = iniciar(cliente, cab, [d.id])
    datos = aceptar_todo(espacio)
    datos["entidades"].append({"tipo": "materia", "valor": texto, **materia})
    r = cliente.post("/api/descripcion/publicar", headers=cab, json=datos)
    assert r.status_code == 201, r.text
    return r.json()


def test_la_materia_se_normaliza_al_publicar_y_dos_documentos_comparten_el_nodo(cliente, db, fondo, cabeceras_admin,
                                                                               motor_prueba):  # noqa: F811
    _admin_importa(cliente, cabeceras_admin, UNESCO, "unesco.ttl")
    crear_usuario(db, "ana@correo.com", "archivista")
    ana = ingresar(cliente, "ana@correo.com")
    a = _publicar_con_materia(cliente, db, fondo, ana, "a.pdf", "festividades")
    b = _publicar_con_materia(cliente, db, fondo, ana, "b.pdf", "Fiestas Populares")
    materias = db.scalars(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fondo.id,
                                                           EntidadVocabulario.clase == "materia")).all()
    assert len(materias) == 1 and materias[0].nombre == "Fiestas populares" and materias[0].concepto_tesauro_id
    for registro in (a, b):
        rel = db.scalar(select(Relacion).where(Relacion.origen_id == registro["id"], Relacion.destino_id == materias[0].id))
        assert rel.codigo_ric == "has_or_had_subject" and rel.rol == "materia"
    # «festividades» (no preferente) quedó registrado como normalización.
    [ev] = eventos(db, "materia_normalizada")
    assert ev.valor_anterior["termino"] == "festividades" and ev.valor_nuevo["preferente"] == "Fiestas populares"
    # Un tema que no está en ningún tesauro queda como término local, sin concepto.
    _publicar_con_materia(cliente, db, fondo, ana, "c.pdf", "Alumbrado público")
    local = db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.nombre == "Alumbrado público"))
    assert local.clase == "materia" and local.concepto_tesauro_id is None

    # Exportación RiC-O conforme: rico:Concept + skos:Concept con exactMatch al concepto de la UNESCO.
    ex = exportar_conforme(db, fondo)
    s = exportacion_rico.uri(materias[0].id)
    assert (s, RDF.type, RICO.Concept) in ex.grafo and (s, RDF.type, SKOS.Concept) in ex.grafo
    assert (s, SKOS.exactMatch, URIRef("http://vocabularies.unesco.org/thesaurus/concept3")) in ex.grafo
    assert (exportacion_rico.uri(a["id"]), RICO.hasOrHadSubject, s) in ex.grafo


def test_elegir_el_concepto_y_anular_el_tesauro_no_cambia_lo_descrito(cliente, db, fondo, cabeceras_admin,
                                                                       motor_prueba):  # noqa: F811
    t = _admin_importa(cliente, cabeceras_admin, UNESCO, "unesco.ttl").json()
    c = db.scalar(select(ConceptoTesauro).where(ConceptoTesauro.preferente == "Archivo histórico"))
    m = cliente.post("/api/tesauros/materias", headers=cabeceras_admin,
                     json={"fondo_id": str(fondo.id), "concepto_id": str(c.id)}).json()
    assert m["nombre"] == "Archivo histórico" and m["concepto"]["tesauro"]["nombre"] == "Tesauro de la UNESCO"
    otra = cliente.post("/api/tesauros/materias", headers=cabeceras_admin,
                        json={"fondo_id": str(fondo.id), "concepto_id": str(c.id)}).json()
    assert otra["id"] == m["id"]  # una sola materia por concepto y fondo
    _publicar_con_materia(cliente, db, fondo, cabeceras_admin, "a.pdf", "lo que escribió", concepto_id=str(c.id))
    r = cliente.post(f"/api/tesauros/{t['id']}/anular", headers=cabeceras_admin, json={"motivo": "Versión nueva"})
    assert r.status_code == 200 and r.json()["estado"] == "anulado"
    # Anulado: ya no normaliza, pero la materia conserva su concepto.
    n = cliente.get("/api/tesauros/normalizar", headers=cabeceras_admin, params={"texto": "archivo historico"}).json()
    assert n["exacto"] is None
    assert db.get(EntidadVocabulario, __import__("uuid").UUID(m["id"])).concepto_tesauro_id == c.id
