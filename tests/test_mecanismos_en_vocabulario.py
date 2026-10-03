"""
Los mecanismos (software, RiC-E13) en Vocabularios: son agentes en RiC y se
exportan como rico:Mechanism, pero no son autoridades ISAAR. No se mezclan
con personas e instituciones en la lista, tienen su propio filtro, dicen
sobre cuántos archivos actuaron y son de solo consulta: lo único que una
persona completa es la versión que llegó vacía (VOC-07).
"""

from rdflib import RDF, Namespace, URIRef

from app.models.descripcion import EntidadVocabulario
from app.servicios import exportacion_rico, mecanismos, vocabulario
from tests import archivos
from tests.test_preservacion import archivista, fondo, herramientas, ingresar_archivo  # noqa: F401

RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")


def listar(cliente, cab, fondo, **params):
    r = cliente.get("/api/vocabulario", headers=cab, params={"fondo_id": str(fondo.id), **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_los_mecanismos_tienen_su_propio_filtro_y_cuentan_archivos(cliente, db, fondo, archivista):
    a = ingresar_archivo(cliente, db, archivista, fondo, "a.pdf", archivos.pdf_con_texto())
    ingresar_archivo(cliente, db, archivista, fondo, "b.pdf", archivos.pdf_con_texto("Otro oficio de 1949."))
    persona = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Jorge Eliécer Gaitán", subtipo="persona",
                                origen="persona", confianza=None, motor=None, usuario_id=None)
    db.commit()
    # Por defecto, ni en «Todos» ni en «Agentes» aparecen los programas.
    for params in ({}, {"clase": "agente"}):
        subtipos = {e["subtipo"] for e in listar(cliente, archivista, fondo, **params)}
        assert "mecanismo" not in subtipos and "persona" in subtipos
    solo = listar(cliente, archivista, fondo, clase="agente", mecanismos="solo")
    assert solo and {e["subtipo"] for e in solo} == {"mecanismo"} and persona.nombre not in {e["nombre"] for e in solo}
    siegfried = next(e for e in solo if e["id"] == str(a.mecanismo_identificacion_id))
    # Actuó sobre los dos archivos: ya no dice «0 documentos».
    assert siegfried["archivos"] == 2 and siegfried["acciones"] == {"identificación de formato": 2}
    # Cada archivo cuenta para el programa que le extrajo el texto (capa del PDF u OCR, según el caso).
    assert sum((e["acciones"] or {}).get("extracción de texto", 0) for e in solo) == 2
    # Siguen siendo agentes en RiC: el grafo exportado los trae como rico:Mechanism.
    from app.models.recurso_documental import RecursoDocumental
    from tests.test_especializacion_ric import documento, relacion
    doc = documento(db, fondo)
    relacion(db, doc, a, "has_or_had_instantiation", destino_tipo="instanciacion")
    db.commit()
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    assert (URIRef(exportacion_rico.base() + siegfried["id"]), RDF.type, RICO.Mechanism) in g


def test_un_mecanismo_es_de_solo_consulta(cliente, db, fondo, archivista):
    gs = vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="Ghostscript", version="10.05.1")
    db.commit()
    base = f"/api/vocabulario/{gs.id}"
    assert cliente.patch(base, headers=archivista, json={"historia": "Programa libre."}).status_code == 422
    assert cliente.patch(base, headers=archivista, json={"version": "10.06.0"}).status_code == 422  # no se cambia
    for ruta, cuerpo in (("nombres", {"tipo": "otra", "nombre": "gs"}),
                         ("identificadores", {"esquema": "wikidata", "valor": "Q1"}),
                         ("hitos", {"tipo": "creacion", "descripcion": "x", "edtf": "1988"})):
        assert cliente.post(f"{base}/{ruta}", headers=archivista, json=cuerpo).status_code == 409, ruta
    db.refresh(gs)
    assert gs.version == "10.05.1" and gs.nombre == "Ghostscript 10.05.1"


def test_la_version_que_falta_si_se_completa(cliente, db, fondo, archivista):
    m = mecanismos.obtener(db, fondo.id, "Conversor X", None)
    db.commit()
    r = cliente.patch(f"/api/vocabulario/{m.id}", headers=archivista, json={"version": "2.1"})
    assert r.status_code == 200, r.text
    db.refresh(m)
    assert m.version == "2.1"


def test_fusionar_conserva_las_acciones_de_texto_y_validacion(cliente, db, fondo, archivista, admin):
    """Las columnas del bloque 5 (texto, recortes, comprobaciones) también pasan a la definitiva."""
    inst = ingresar_archivo(cliente, db, archivista, fondo, "a.pdf", archivos.pdf_con_texto())
    texto = db.get(EntidadVocabulario, inst.mecanismo_texto_id)
    a_mano = vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="pypdfium2 (a mano)", version=texto.version)
    db.commit()
    vocabulario.fusionar(db, definitiva=a_mano, absorbida=texto, usuario_id=admin.id)
    db.commit()
    db.refresh(inst)
    assert inst.mecanismo_texto_id == a_mano.id
