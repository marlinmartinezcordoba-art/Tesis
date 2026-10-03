"""
Cierre de CM-11 y O-19 (y la parte RDF de CM-22) de la auditoría RiC: el
agente mecanismo que actuó sobre un archivo exportado sale en el RDF como
rico:Mechanism con su versión (rico:technicalCharacteristics), y su acción
técnica como rico:Activity que ejerce y que afecta al archivo. El motor de
análisis (procedencia del dato) sigue sin salir.
"""

import uuid

from rdflib import RDF, Literal, Namespace

from app.db.base import ahora
from app.models.instanciacion import Instanciacion
from app.models.preservacion import Migracion
from app.servicios import conformidad_rico, exportacion_rico, ric_o, vocabulario
from tests.test_exportacion_rico import exportar, fondo_rico, u  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401

RICO = Namespace(ric_o.RICO)


def _con_acciones(db, f, admin):
    inst = db.query(Instanciacion).filter(Instanciacion.nombre_original == "Oficio_114_1948.pdf").one()
    sf = vocabulario.mecanismo(db, fondo_id=f["fondo"].id, nombre="Siegfried", version="1.11.9", usuario_id=admin.id)
    gs = vocabulario.mecanismo(db, fondo_id=f["fondo"].id, nombre="Ghostscript", version="10.02.1", usuario_id=admin.id)
    inst.mecanismo_identificacion_id, inst.procesado_en = sf.id, ahora()
    pdfa = Instanciacion(id=uuid.uuid4(), fondo_id=f["fondo"].id, nombre_original="Oficio_114_1948_pdfa.pdf",
                         ruta="x/z.pdf", tamano_bytes=12, estado="listo_para_descripcion", huella="b" * 64,
                         formato_puid="fmt/95", derivada_de_id=inst.id)
    db.add(pdfa)
    db.flush()
    m = Migracion(id=uuid.uuid4(), instanciacion_origen_id=inst.id, destino="pdfa", destino_nombre="PDF/A-2b",
                  modo="automatica", estado="completada", aprobada_por_id=admin.id, terminada_en=ahora(),
                  instanciacion_resultado_id=pdfa.id, mecanismo_id=gs.id)
    db.add(m)
    db.flush()
    return inst, sf, gs, m


def test_el_mecanismo_sale_con_su_version_y_su_accion_tecnica(db, fondo_rico, admin):
    f = fondo_rico
    inst, sf, gs, m = _con_acciones(db, f, admin)
    g = exportar(db, f).grafo
    for mec, version in ((sf, "1.11.9"), (gs, "10.02.1")):
        assert (u(mec.id), RDF.type, RICO.Mechanism) in g
        assert (u(mec.id), RICO.technicalCharacteristics, Literal(version)) in g
    identificacion = exportacion_rico.uri(inst.id, "identificacion-de-formato")
    migracion = exportacion_rico.uri(inst.id, "migracion", m.id)
    for accion, quien in ((identificacion, sf), (migracion, gs)):
        assert (accion, RDF.type, RICO.Activity) in g
        assert (u(quien.id), RICO.performsOrPerformed, accion) in g
        assert (accion, RICO.affectsOrAffected, u(inst.id)) in g
        assert next(g.objects(accion, RICO.hasBeginningDate), None) is not None
    texto = exportacion_rico.serializar(g, "turtle").decode()
    assert "Motor de análisis" not in texto  # el motor es procedencia del dato, no acción sobre el archivo


def test_la_exportacion_con_mecanismos_es_conforme_al_owl_y_al_perfil_shacl(db, fondo_rico, admin):
    f = fondo_rico
    _con_acciones(db, f, admin)
    g = exportar(db, f).grafo
    assert conformidad_rico.verificar_owl(g) == []
    r = conformidad_rico.validar_shacl(g)
    assert r["conforme"], r["resultados"]
    # La forma pr:Mechanism ya tiene a quién aplicarse.
    assert any(True for _ in g.subjects(RDF.type, RICO.Mechanism))


def test_la_accion_tecnica_resuelve_su_uri(cliente, db, fondo_rico, admin):
    from app.servicios import parametros

    f = fondo_rico
    inst, sf, _, _ = _con_acciones(db, f, admin)
    parametros.cambiar(db, "rdf_uris_publicas", True, admin.id, "instrumentos")
    db.commit()
    r = cliente.get(f"/id/{inst.id}/identificacion-de-formato.ttl")
    assert r.status_code == 200 and "affectsOrAffected" in r.text
    r = cliente.get(f"/id/{sf.id}.ttl")
    assert r.status_code == 200 and "technicalCharacteristics" in r.text and "1.11.9" in r.text
