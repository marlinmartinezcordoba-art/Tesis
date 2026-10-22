"""
RiC completo, fase 1 (documentacion/brechas-ric-lineamiento-completo.md).

- A1 · Los tipos documentales que la TRD asigna a una serie salen en RiC-O como
  rico:hasOrHadSomeMembersWithDocumentaryFormType (RiC-AG: en un Record Set).
- A3 · El expediente eliminado lleva su fecha de destrucción; la digitalización
  del original es una actividad que lo afecta y resulta en la copia digital.
- A4 · El original en papel y la copia digital se distinguen; el original tiene
  su extensión de soporte y su ubicación (un lugar con su localización textual);
  cada instanciación declara su tipo de representación.
- A5 y A6 · Estado del documento, borrador de y respuesta a, como relaciones de RiC.
- A7 y A8 · Completitud (integrityNote) y código del CCD (classification).
- A9 · El CCD y cada versión de la TRD son documentos que describen el fondo, y
  la TRD se expresa en el suyo.

Todo pasa el OWL y el perfil SHACL, y la ida y vuelta tablas → grafo → tablas es exacta.
"""

import uuid

from rdflib import RDF, Literal, Namespace
from sqlalchemy import select

from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, grafo_control, grafo_rdf
from tests.test_descripcion import archivista, documento, eventos, fondo, iniciar  # noqa: F401
from tests.test_descripcion_v3 import TEXTO, publicar, sin_motor  # noqa: F401
from tests.test_disposicion import _fondo
from tests.test_especializacion_ric import exportar_conforme

RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")
u = exportacion_rico.uri


def _nombres(g, nodos):
    return {str(g.value(n, RICO.name)) for n in nodos}


def test_la_trd_en_ric_tipos_de_la_serie_clasificacion_instrumentos_y_destruccion(cliente, db, cabeceras_admin):
    cab = cabeceras_admin
    fnd, viejo, _ = _fondo(cliente, db, cab)
    serie = db.get(RecursoDocumental, viejo.incluido_en_id)
    assert serie.codigo_referencia == "110.15" and len(serie.formas_miembros) == 3
    viejo.nota_integridad = "Falta el oficio del folio 12."
    r = cliente.post("/api/disposicion/ejecutar", headers=cab, json={
        "fondo_id": str(fnd.id), "recursos": [str(viejo.id)], "disposicion": "eliminacion", "acta_numero": "05",
        "acta_fecha": "2025-03-10", "ejecutor": "Comité Institucional de Gestión y Desempeño"})
    assert r.status_code == 201, r.text
    g = exportar_conforme(db, fnd).grafo
    # A1: los tipos de la TRD, en la serie, con «algunos miembros».
    tipos = set(g.objects(u(serie.id), RICO.hasOrHadSomeMembersWithDocumentaryFormType))
    assert _nombres(g, tipos) == {"Oficio", "Memorando", "Circular"}
    assert all((t, RDF.type, RICO.DocumentaryFormType) in g for t in tipos)
    assert not list(g.objects(u(serie.id), RICO.hasDocumentaryFormType))  # solo de Record y Record Part
    # A8: el código del CCD; el expediente lleva el de su serie. No reemplaza al identificador.
    assert g.value(u(serie.id), RICO.classification) == Literal("110.15")
    assert g.value(u(viejo.id), RICO.classification) == Literal("110.15")
    # A7: completitud intelectual.
    assert str(g.value(u(viejo.id), RICO.integrityNote)) == "Falta el oficio del folio 12."
    # A3: el expediente eliminado lleva su fecha de destrucción, la del acta.
    destruccion = g.value(u(viejo.id), RICO.hasDestructionDate)
    assert str(g.value(destruccion, RICO.normalizedDateValue)) == "2025-03-10"
    # A9: el CCD y la TRD como documentos que describen el fondo; la regla se expresa en el suyo.
    describen = set(g.subjects(RICO.describesOrDescribed, u(fnd.id)))
    assert len(describen) == 2 and all((d, RDF.type, RICO.Record) in g for d in describen)
    formas = {str(g.value(g.value(d, RICO.hasDocumentaryFormType), RICO.name)) for d in describen}
    assert formas == {"Cuadro de clasificación documental", "Tabla de retención documental"}
    [regla_trd] = [s for s in g.subjects(RICO.isOrWasExpressedBy, None)]
    assert (regla_trd, RDF.type, RICO.Rule) in g and g.value(regla_trd, RICO.isOrWasExpressedBy) in describen


def test_una_version_nueva_reemplaza_los_tipos_de_la_serie(cliente, db, cabeceras_admin):
    from app.servicios import cuadro

    fnd, viejo, _ = _fondo(cliente, db, cabeceras_admin)
    serie = db.get(RecursoDocumental, viejo.incluido_en_id)
    filas = [f for f in cuadro.vista_previa(__import__("tests.archivos", fromlist=["x"]).trd_agn_xlsx(), "t.xlsx")["filas"]
             if f["serie"]["codigo"] == "15"]
    filas[0]["tipos"] = ["Oficio"]
    cuadro.aplicar(db, fnd, filas, fnd.creado_por_id)
    db.flush()
    db.refresh(serie)
    assert len(serie.formas_miembros) == 1


def test_original_en_papel_y_copia_digital_con_digitalizacion_ubicacion_y_representacion(
        cliente, db, fondo, archivista, sin_motor):  # noqa: F811
    d = documento(db, fondo, "acta.pdf", TEXTO)
    acta = publicar(cliente, archivista, iniciar(cliente, archivista, [d.id]), titulo="Acta 12").json()
    db.get(RecursoDocumental, uuid.UUID(acta["id"])).folios = 4
    db.commit()
    r = cliente.post(f"/api/descripcion/registros/{acta['id']}/original-fisico", headers=archivista, json={
        "soporte": "papel", "ubicacion": "Archivo central", "deposito": "2", "estante": "14", "entrepano": "3"})
    assert r.status_code == 201, r.text
    [fisico] = [i for i in r.json()["instanciaciones"] if i.get("fisica")]
    g = exportar_conforme(db, db.get(RecursoDocumental, fondo.id)).grafo
    a, f, dig = u(acta["id"]), u(fisico["id"]), u(d.id)
    assert (a, RICO.hasOrHadAnalogueInstantiation, f) in g and (a, RICO.hasOrHadDigitalInstantiation, dig) in g
    assert (a, RICO.hasOrHadInstantiation, f) in g  # la general sigue
    # Extensión del soporte (RiC-A04): los folios del original.
    assert str(g.value(f, RICO.carrierExtent)) == "4 folios"
    assert any((e, RDF.type, RICO.CarrierExtent) in g for e in g.objects(f, RICO.hasExtent))
    # La ubicación: un lugar con su localización textual (RiC-A27).
    lugar = g.value(f, RICO.hasOrHadLocation)
    assert (lugar, RDF.type, RICO.Place) in g
    assert str(g.value(lugar, RICO.location)) == "Depósito 2, estante 14, entrepaño 3; Archivo central"
    # Tipo de representación (RiC-A37).
    assert str(g.value(g.value(f, RICO.hasRepresentationType), RICO.name)).startswith("Analógica")
    assert str(g.value(g.value(dig, RICO.hasRepresentationType), RICO.name)).startswith("Digital")
    # La digitalización (RiC-AG): afecta al original y resulta en la copia.
    [act] = list(g.subjects(RICO.resultsOrResultedIn, dig))
    assert (act, RDF.type, RICO.Activity) in g and (act, RICO.affectsOrAffected, f) in g
    assert str(g.value(g.value(act, RICO.hasActivityType), RICO.name)) == "Digitalización"


def test_respuesta_borrador_estado_y_completitud(cliente, db, fondo, archivista, sin_motor):  # noqa: F811
    recibido = publicar(cliente, archivista, iniciar(cliente, archivista, [documento(db, fondo, "of1.pdf", TEXTO).id]),
                        titulo="Oficio recibido 77").json()
    final = publicar(cliente, archivista, iniciar(cliente, archivista, [documento(db, fondo, "of2.pdf", TEXTO).id]),
                     titulo="Respuesta al oficio 77", responde_a_id=recibido["id"], estado_documento="original",
                     nota_integridad="Completo.").json()
    assert final["estado_documento"] == "original" and final["nota_integridad"] == "Completo."
    assert [(v["tipo"], v["id"]) for v in final["vinculos"]] == [("responde_a", recibido["id"])]
    r = publicar(cliente, archivista, iniciar(cliente, archivista, [documento(db, fondo, "of3.pdf", TEXTO).id]),
                 titulo="Borrador de la respuesta", borrador_de_id=final["id"], estado_documento="borrador")
    assert r.status_code == 201, r.text
    borrador = r.json()
    # Lo que no se admite.
    trabajo = cliente.post(f"/api/descripcion/registros/{final['id']}/reabrir", headers=archivista).json()["trabajo_id"]
    malo = cliente.patch(f"/api/descripcion/{final['id']}", headers=archivista,
                         json={"trabajo_id": trabajo, "estado_documento": "perdido"})
    assert malo.status_code == 422
    repetido = cliente.patch(f"/api/descripcion/{final['id']}", headers=archivista,
                             json={"trabajo_id": trabajo, "responde_a_id": recibido["id"]})
    assert repetido.status_code == 409
    # La ficha de consulta y la del recibido los nombran desde su lado.
    detalle = cliente.get(f"/api/descripcion/registros/{recibido['id']}", headers=archivista).json()
    assert [(v["tipo"], v["uri_rico"]) for v in detalle["vinculos"]] == [("tiene_respuesta", "rico:hasReply")]
    publica = cliente.get(f"/api/catalogo/registros/{final['id']}", headers=archivista)
    assert publica.status_code == 200, publica.text
    assert {v["tipo"] for v in publica.json()["vinculos"]} == {"responde_a", "tiene_borrador"}
    assert publica.json()["estado_documento"] == "original"
    # En RiC-O 1.1.
    g = exportar_conforme(db, db.get(RecursoDocumental, fondo.id)).grafo
    assert (u(recibido["id"]), RICO.hasReply, u(final["id"])) in g
    assert (u(borrador["id"]), RICO.isDraftOf, u(final["id"])) in g
    estado = g.value(u(final["id"]), RICO.hasRecordState)
    assert (estado, RDF.type, RICO.RecordState) in g and str(g.value(estado, RICO.name)) == "Original"
    assert str(g.value(u(final["id"]), RICO.integrityNote)) == "Completo."
    clases = {g.value(n, RDF.type) for n in g.subjects(RICO.relationHasTarget, u(final["id"]))}
    assert {RICO.RecordResourceToRecordResourceRelation, RICO.RecordResourceGeneticRelation} <= clases
    assert db.scalar(select(Relacion).where(Relacion.codigo_ric == "is_draft_of")).origen_id == uuid.UUID(borrador["id"])
    assert any(e.valor_nuevo.get("vinculos") for e in eventos(db, "descripcion_publicada") if e.valor_nuevo)


def test_el_estado_es_de_un_documento_no_de_una_agrupacion(cliente, db, fondo, archivista, sin_motor):  # noqa: F811
    a, b = documento(db, fondo, "a.pdf", TEXTO), documento(db, fondo, "b.pdf", TEXTO)
    r = publicar(cliente, archivista, iniciar(cliente, archivista, [a.id, b.id], nivel="expediente"),
                 titulo="Expediente 9", estado_documento="copia")
    assert r.status_code == 422 and "agrupación" in r.json()["detail"]


def test_ida_y_vuelta_exacta_con_los_datos_nuevos(cliente, db, cabeceras_admin):
    fnd, viejo, _ = _fondo(cliente, db, cabeceras_admin)
    viejo.nota_integridad = "Completo, 120 folios."
    db.commit()
    for alcance in grafo_rdf.ALCANCES:
        grafo_rdf.sincronizar(db, fnd, alcance)
    db.commit()
    antes = grafo_control.foto(db, fnd.id)
    assert grafo_rdf.comparar(db, fnd.id) == []
    # RiC-O primero: los tipos de la serie y la completitud no se repiten en el control.
    control = grafo_rdf.almacen().leer(grafo_rdf.nombre(fnd.id, "control")).decode()
    assert "#formas_miembros>" not in control and "#nota_integridad>" not in control
    assert grafo_rdf.reconstruir(db, fnd.id)["diferencias_despues"] == []
    assert grafo_control.foto(db, fnd.id) == antes
