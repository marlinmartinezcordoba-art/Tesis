"""
Importar un fondo descrito en RiC-O desde otro sistema.

- Ida y vuelta: un fondo de RICORA exportado en Turtle se importa como otro
  fondo con el mismo cuadro (por la parametrización de la TRD), la misma
  retención, sus documentos, su vocabulario y sus relaciones; conforme con RiC-O.
- Un RiC-O externo (Fondo › Serie › Expediente › Documento, sin secciones ni
  tipos de agrupación propios): los niveles se deducen del árbol y la sección de
  las series la indica la persona (se sugiere el productor del fondo).
- La vista previa no crea nada; sin `crear` se valida y se deshace; solo la
  administración importa; un archivo que no es RiC-O se rechaza.
"""

import uuid

from sqlalchemy import func, select

from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.models.trd import VersionTrd
from app.servicios import cuadro, exportacion_rico, retencion
from tests.archivos import trd_agn_xlsx
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import eventos

EXTERNO = """
@prefix rico: <https://www.ica.org/standards/RiC/ontology#> .
@prefix rst: <https://www.ica.org/standards/RiC/vocabularies/recordSetTypes#> .
@prefix ex: <https://archivo.ejemplo.org/> .

ex:fondo a rico:RecordSet ; rico:hasRecordSetType rst:Fonds ; rico:title "Archivo de la Notaría Primera"@es ;
    rico:hasCreator ex:notaria ; rico:includesOrIncluded ex:escrituras .
ex:notaria a rico:CorporateBody ; rico:name "Notaría Primera de Tunja" .
ex:escrituras a rico:RecordSet ; rico:title "Escrituras públicas" ; rico:identifier "3" ;
    rico:includesOrIncluded ex:protocolo1890 .
ex:protocolo1890 a rico:RecordSet ; rico:title "Protocolo de 1890" ; rico:includesOrIncluded ex:escritura12 .
ex:escritura12 a rico:Record ; rico:title "Escritura 12: venta de un solar" ;
    rico:scopeAndContent "Venta de un solar en la plaza principal." ;
    rico:hasSender ex:perez ; rico:hasOrHadSubject ex:tunja .
ex:perez a rico:Person ; rico:name "Juan Pérez" .
ex:tunja a rico:Place ; rico:name "Tunja" .
ex:copia a rico:Instantiation .
"""


def _vista(cliente, cab, contenido, nombre, **datos):
    return cliente.post("/api/importacion/rico/vista-previa", headers=cab, data=datos,
                        files={"archivo": (nombre, contenido)})


def _importar(cliente, cab, contenido, nombre, **datos):
    return cliente.post("/api/importacion/rico", headers=cab, data=datos, files={"archivo": (nombre, contenido)})


def _fondo_de_ricora(cliente, db, cab):
    filas = cuadro.vista_previa(trd_agn_xlsx(), "trd.xlsx")["filas"]
    r = cliente.post("/api/fondos/configurar", headers=cab, json={
        "fondo": {"titulo": "Secretaría General de Tunja", "fechas_extremas": "1950–1990"}, "filas": filas, "crear": True,
        "version": {"acto_aprobacion": "Resolución 045", "fecha_aprobacion": "2019-02-15", "vigente_desde": "2019-03-01"}})
    assert r.status_code == 200 and r.json()["creado"], r.text
    fnd = db.get(RecursoDocumental, uuid.UUID(r.json()["fondo"]["id"]))
    serie = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fnd.id,
                                                      RecursoDocumental.codigo_referencia == "110.15"))
    doc = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo="Oficio 114 al Gobernador", fondo_id=fnd.id,
                            incluido_en_id=serie.id, alcance_contenido="Informe sobre el archivo municipal.",
                            fechas_extremas="1948", fechas_extremas_edtf="1948",
                            publicado_en=__import__("app.db.base", fromlist=["ahora"]).ahora())
    alcalde = EntidadVocabulario(id=uuid.uuid4(), fondo_id=fnd.id, clase="agente", subtipo="persona", nombre="Pedro Gómez",
                                 nombre_normalizado="pedro gomez", origen="persona", estado_revision="validado")
    db.add_all([doc, alcalde])
    db.flush()
    db.add_all([Relacion(origen_tipo="recurso_documental", origen_id=serie.id, destino_tipo="recurso_documental",
                         destino_id=doc.id, tipo_relacion="inclusion", codigo_ric="includes_or_included", origen="persona"),
                Relacion(origen_tipo="recurso_documental", origen_id=doc.id, destino_tipo="entidad_vocabulario",
                         destino_id=alcalde.id, tipo_relacion="procedencia", codigo_ric="has_sender", rol="remitente",
                         origen="persona")])
    db.commit()
    return fnd


def test_ida_y_vuelta_un_fondo_de_ricora_se_importa_igual(cliente, db, cabeceras_admin):
    cab = cabeceras_admin
    original = _fondo_de_ricora(cliente, db, cab)
    ttl = exportacion_rico.serializar(exportacion_rico.exportar(db, original, incluir_restringidos=True).grafo, "turtle")
    v = _vista(cliente, cab, ttl, "secretaria.ttl")
    assert v.status_code == 200, v.text
    p = v.json()
    assert p["fondo"] == "Secretaría General de Tunja" and p["problemas"] == []
    assert p["niveles"] == {"fondo": 1, "seccion": 1, "serie": 2, "subserie": 2, "unidad_documental": 1}
    assert p["filas_cuadro"] == 3 and p["filas_con_problemas"] == 0 and p["series_sin_seccion"] == 0
    # La vista previa no creó nada; validar sin crear tampoco.
    antes = db.scalar(select(func.count()).select_from(RecursoDocumental))
    r = _importar(cliente, cab, ttl, "secretaria.ttl", titulo="Copia importada")
    assert r.status_code == 200 and r.json()["creado"] is False and r.json()["validacion"]["conforme"], r.text
    assert db.scalar(select(func.count()).select_from(RecursoDocumental)) == antes
    # Importar: el mismo cuadro por la TRD (vigente con el acto dado), la misma retención y el documento.
    r = _importar(cliente, cab, ttl, "secretaria.ttl", titulo="Copia importada", crear="1",
                  acto_aprobacion="Resolución 045", fecha_aprobacion="2019-02-15", vigente_desde="2019-03-01")
    assert r.status_code == 200, r.text
    i = r.json()
    assert i["creado"] and i["validacion"]["conforme"] and i["version"]["estado"] == "vigente"
    assert i["contenido"]["documentos"] == 1 and i["contenido"]["relaciones"] >= 1
    copia = db.get(RecursoDocumental, uuid.UUID(i["fondo"]["id"]))
    por_codigo = {x.codigo_referencia: x for x in db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == copia.id, RecursoDocumental.codigo_referencia.is_not(None)))}
    assert set(por_codigo) == {"110", "110.2", "110.2.1", "110.2.2", "110.15"}
    regla = retencion.retencion_de(db, por_codigo["110.2.1"])
    assert (regla["gestion_anios"], regla["central_anios"], regla["disposicion_final"]) == (2, 8, "conservacion_total")
    doc = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == copia.id,
                                                    RecursoDocumental.nivel == "unidad_documental"))
    assert doc.incluido_en_id == por_codigo["110.15"].id and doc.fechas_extremas_edtf == "1948"
    remitente = db.scalar(select(Relacion).where(Relacion.origen_id == doc.id, Relacion.codigo_ric == "has_sender"))
    assert remitente.rol == "remitente" and db.get(EntidadVocabulario, remitente.destino_id).nombre == "Pedro Gómez"
    assert copia.fechas_extremas_edtf == "1950/1990"
    assert len(eventos(db, "rico_importado")) == 1
    assert db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == copia.id)).estado == "vigente"


def test_un_rico_externo_sin_secciones_pide_la_dependencia_productora(cliente, db, cabeceras_admin):
    cab, ttl = cabeceras_admin, EXTERNO.encode()
    p = _vista(cliente, cab, ttl, "notaria.ttl").json()
    # Niveles deducidos del árbol: serie, expediente y documento.
    assert p["niveles"] == {"fondo": 1, "serie": 1, "expediente": 1, "unidad_documental": 1}
    assert p["series_sin_seccion"] == 1 and p["productor_sugerido"] == "Notaría Primera de Tunja"
    assert p["entidades"] == {"agente": 2, "lugar": 1}
    assert any("instanciaciones" in k for k in p["omitidas"])
    # Sin la sección, no se importa: la serie necesita su dependencia productora.
    r = _importar(cliente, cab, ttl, "notaria.ttl", crear="1")
    assert r.status_code == 422 and "sección" in r.json()["detail"], r.text
    r = _importar(cliente, cab, ttl, "notaria.ttl", crear="1", seccion_nombre="Notaría Primera de Tunja",
                  seccion_codigo="100")
    assert r.status_code == 200 and r.json()["creado"], r.text
    i = r.json()
    assert i["version"]["estado"] == "borrador" and i["contenido"]["expedientes"] == 1
    # Remitente y tema del documento, y el productor del fondo.
    assert i["contenido"]["documentos"] == 1 and i["contenido"]["relaciones"] == 3
    fnd = uuid.UUID(i["fondo"]["id"])
    productor = db.scalar(select(Relacion).where(Relacion.origen_id == fnd, Relacion.codigo_ric == "has_creator"))
    assert productor.rol == "productor" and db.get(EntidadVocabulario, productor.destino_id).nombre == "Notaría Primera de Tunja"
    serie = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fnd, RecursoDocumental.nivel == "serie"))
    assert serie.titulo == "Escrituras públicas" and serie.codigo_referencia == "100.3"
    exp = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fnd,
                                                    RecursoDocumental.nivel == "expediente"))
    assert exp.incluido_en_id == serie.id
    tema = db.scalar(select(Relacion).where(Relacion.codigo_ric == "has_or_had_subject",
                                            Relacion.destino_id.in_(select(EntidadVocabulario.id).where(
                                                EntidadVocabulario.fondo_id == fnd))))
    assert tema.rol == "lugar"


def test_solo_la_administracion_y_solo_rico(cliente, db, cabeceras_admin):
    crear_usuario(db, "ana@imp.co", "archivista")
    db.commit()
    ana = ingresar(cliente, "ana@imp.co")
    assert _vista(cliente, ana, EXTERNO.encode(), "x.ttl").status_code == 403
    r = _vista(cliente, cabeceras_admin, b"<http://ejemplo.org/a> <http://ejemplo.org/b> <http://ejemplo.org/c> .", "x.nt")
    assert r.status_code == 422 and "RiC-O" in r.json()["detail"]
    assert _vista(cliente, cabeceras_admin, b"hola", "x.docx").status_code == 422
    assert _vista(cliente, cabeceras_admin, b"@prefix : <x", "x.ttl").status_code == 422


def test_la_trd_viaja_como_instrumento_en_rico(cliente, db, cabeceras_admin):
    from rdflib import RDF, Namespace

    rico = Namespace("https://www.ica.org/standards/RiC/ontology#")
    original = _fondo_de_ricora(cliente, db, cabeceras_admin)
    ex = exportacion_rico.exportar(db, original, incluir_restringidos=True)
    v = db.scalar(select(VersionTrd).where(VersionTrd.fondo_id == original.id))
    trd, acto = exportacion_rico.uri(v.id), exportacion_rico.uri(v.id, "acto")
    g = ex.grafo
    assert (trd, RDF.type, rico.Rule) in g and (acto, RDF.type, rico.Mandate) in g
    assert (acto, rico.regulatesOrRegulated, trd) in g and (trd, rico.regulatesOrRegulated, exportacion_rico.uri(original.id)) in g
    assert len(list(g.objects(trd, rico.hasOrHadPart))) == 3  # las tres reglas de serie de la versión
    from app.servicios import conformidad_rico
    assert conformidad_rico.verificar_owl(g) == [] and conformidad_rico.validar_shacl(g)["conforme"]
    # Al importarlo en otro sistema, la vista previa trae el acto, su fecha y la vigencia.
    ttl = exportacion_rico.serializar(g, "turtle")
    p = _vista(cliente, cabeceras_admin, ttl, "secretaria.ttl").json()
    assert p["trd"] == {"nombre": "TRD versión 1", "acto_aprobacion": "Resolución 045",
                        "fecha_aprobacion": "2019-02-15", "vigente_desde": "2019-03-01"}
    assert "mandato" not in p["entidades"]  # el acto no se vuelve una entidad suelta del vocabulario
