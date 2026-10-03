"""
Hallazgo O-31: cada relación del mapeo que la exportación no ejercitaba
tiene ahora su propia tripleta comprobada en el RDF.

Las filas se crean con los servicios del sistema (vincular, secuencia,
custodio, hito) cuando el servicio existe. La migración y el remitente se
escriben como los escribe su servicio (preservación y publicación), porque
exigir un archivo real o una sesión de descripción no agrega nada a lo que
se prueba aquí: la tripleta. El guardián de integridad (CM-19) valida cada
fila igual que en producción.
"""

import uuid

import pytest
from rdflib import URIRef
from sqlalchemy import select

from app.db.base import ahora
from app.models.descripcion import EntidadVocabulario, Fecha, Relacion
from app.models.instanciacion import Instanciacion
from app.servicios import autoridad, descripcion, exportacion_rico, ric_o, vocabulario
from tests.test_exportacion_rico import RICO, exportar, fondo_rico, u  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def _nuevo(db, f, clase, nombre, subtipo=None):
    return vocabulario.crear(db, fondo_id=f["fondo"].id, clase=clase, nombre=nombre, subtipo=subtipo,
                             origen="persona", confianza=None, motor=None, usuario_id=None)


@pytest.fixture()
def fondo_completo(db, fondo_rico, admin):
    """`fondo_rico` más una fila de cada relación que antes no tenía prueba de tripleta."""
    f = fondo_rico
    alcaldia = f["alcaldia"]
    despacho = _nuevo(db, f, "agente", "Despacho del Alcalde", "entidad_corporativa")
    concejo = _nuevo(db, f, "agente", "Concejo Municipal", "entidad_corporativa")
    personeria = _nuevo(db, f, "agente", "Personería", "entidad_corporativa")
    # El cargo ya está en el contexto exportado (destinatario del oficio 114):
    # la exportación recorre el contexto desde los documentos.
    gobernador = db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == f["fondo"].id,
                                                            EntidadVocabulario.nombre == "Gobernador del Departamento"))
    gomez = _nuevo(db, f, "agente", "Pedro Gómez", "persona")
    boyaca = _nuevo(db, f, "lugar", "Departamento de Boyacá")
    tramite = _nuevo(db, f, "actividad", "Trámite del permiso N.º 3")
    db.flush()
    t = {"usuario_id": admin.id}
    v = {
        "has_or_had_subordinate": autoridad.vincular(db, tipo="subordinado", desde=alcaldia,
                                                     con_tipo="entidad_vocabulario", con_id=despacho.id, **t),
        "has_successor": autoridad.vincular(db, tipo="sucesor", desde=concejo, con_tipo="entidad_vocabulario",
                                            con_id=personeria.id, **t),
        "is_agent_associated_with_agent": autoridad.vincular(db, tipo="asociado", desde=alcaldia,
                                                             con_tipo="entidad_vocabulario", con_id=concejo.id, **t),
        "occupies_or_occupied": autoridad.vincular(db, tipo="ocupa_cargo", desde=gomez,
                                                   con_tipo="entidad_vocabulario", con_id=gobernador.id, **t),
        "authorizes": autoridad.vincular(db, tipo="creado_por", desde=alcaldia, con_tipo="entidad_vocabulario",
                                         con_id=f["acuerdo"].id, **t),
        "issued_by": autoridad.vincular(db, tipo="expedido_por", desde=f["acuerdo"], con_tipo="entidad_vocabulario",
                                        con_id=concejo.id, **t),
        "has_direct_subevent": autoridad.vincular(db, tipo="actividad_mayor", desde=tramite,
                                                  con_tipo="entidad_vocabulario", con_id=f["actividad"].id, **t),
        "contains_or_contained": autoridad.vincular(db, tipo="lugar_superior", desde=f["tunja"],
                                                    con_tipo="entidad_vocabulario", con_id=boyaca.id, **t),
        "is_related_to": autoridad.vincular(db, tipo="serie_producida", desde=f["funcion"],
                                            con_tipo="recurso_documental", con_id=f["serie"].id, **t),
    }
    # Secuencia entre dos oficios de la misma serie (DES).
    descripcion._secuencia(db, f["o114"], f["o115"].id, "precede", admin.id)
    # Custodio de la instanciación (DES-05).
    inst = db.get(Instanciacion, db.scalar(select(Relacion.destino_id).where(
        Relacion.origen_id == f["o114"].id, Relacion.codigo_ric == "has_or_had_instantiation")))
    descripcion.custodio_de_instanciacion(db, inst, concejo.id, None, None, admin.id)
    # El mecanismo que identificó su formato: así el Mechanism también sale (O-32).
    sf = vocabulario.mecanismo(db, fondo_id=f["fondo"].id, nombre="Siegfried", version="1.11.9", usuario_id=admin.id)
    inst.mecanismo_identificacion_id, inst.procesado_en = sf.id, ahora()
    # Migración de formato, como la escribe preservacion.migrar.
    nueva = Instanciacion(id=uuid.uuid4(), fondo_id=f["fondo"].id, nombre_original="Oficio_114_1948.tif",
                          ruta="x/z.tif", tamano_bytes=20, estado="listo_para_descripcion", huella="b" * 64,
                          formato_puid="fmt/353", formato_nombre="TIFF", derivada_de_id=inst.id)
    db.add(nueva)
    db.flush()
    for origen_tipo, origen_id, destino_tipo, destino_id, codigo in (
            ("instanciacion", inst.id, "instanciacion", nueva.id, "migrated_into"),
            ("recurso_documental", f["o114"].id, "instanciacion", nueva.id, "has_or_had_instantiation"),
            # Remitente, como lo escribe descripcion.publicar (rol «remitente»).
            ("recurso_documental", f["o115"].id, "entidad_vocabulario", concejo.id, "has_sender")):
        db.add(Relacion(origen_tipo=origen_tipo, origen_id=origen_id, destino_tipo=destino_tipo,
                        destino_id=destino_id, tipo_relacion="asociacion", codigo_ric=codigo, origen="persona"))
    # Fecha asociada (expedición del mandato, CM-12).
    expedicion = Fecha(id=uuid.uuid4(), expresion="12 de marzo de 1946", edtf="1946-03-12", subtipo="simple",
                       calendario="gregoriano", origen="persona")
    db.add(expedicion)
    db.flush()
    db.add(Relacion(origen_tipo="fecha", origen_id=expedicion.id, destino_tipo="entidad_vocabulario",
                    destino_id=f["acuerdo"].id, tipo_relacion="temporal", codigo_ric="is_date_associated_with",
                    rol="expedicion", origen="persona"))
    # Hito que afecta a otro agente además del suyo (CM-13).
    hito = autoridad.agregar_hito(db, alcaldia, tipo="reforma", descripcion="Fusión con la Personería", edtf="1950",
                                  usuario_id=admin.id, afectados=[{"tipo": "entidad_vocabulario",
                                                                   "id": str(personeria.id)}])
    db.commit()
    return f | {"vinculos": v, "inst": inst, "nueva": nueva, "concejo": concejo, "personeria": personeria,
                "expedicion": expedicion, "hito": hito}


def _filas(f):
    """(código, origen, destino) de cada relación que antes no tenía tripleta propia."""
    v = f["vinculos"]
    filas = [(codigo, r.origen_id, r.destino_id) for codigo, r in v.items()]
    return filas + [
        ("precedes_or_preceded", f["o114"].id, f["o115"].id),
        ("has_or_had_holder", f["inst"].id, f["concejo"].id),
        ("migrated_into", f["inst"].id, f["nueva"].id),
        ("has_sender", f["o115"].id, f["concejo"].id),
        ("is_date_associated_with", f["expedicion"].id, f["acuerdo"].id),
        ("affects_or_affected", f["hito"].id, f["personeria"].id),
    ]


CODIGOS = ("has_or_had_subordinate", "has_successor", "is_agent_associated_with_agent", "occupies_or_occupied",
           "authorizes", "issued_by", "has_direct_subevent", "contains_or_contained", "is_related_to",
           "precedes_or_preceded", "has_or_had_holder", "migrated_into", "has_sender", "is_date_associated_with",
           "affects_or_affected")


def test_las_quince_relaciones_tienen_tripleta_propia(db, fondo_completo):
    f = fondo_completo
    filas = _filas(f)
    assert {c for c, _, _ in filas} == set(CODIGOS)
    g = exportar(db, f).grafo
    faltan = [codigo for codigo, o, d in filas
              if (u(o), RICO[ric_o.PROPIEDADES[codigo].rico], u(d)) not in g]
    assert not faltan, f"sin tripleta en el RDF: {faltan}"


def test_las_propiedades_de_cada_relacion_estan_en_el_owl():
    """Las propiedades usadas en estas tripletas existen en RiC-O 1.1 con ese nombre exacto."""
    owl = ric_o._owl()
    for codigo in CODIGOS:
        assert (URIRef(ric_o.RICO + ric_o.PROPIEDADES[codigo].rico), None, None) in owl, codigo


def test_la_exportacion_del_fondo_completo_sigue_conforme(db, fondo_completo):
    from app.servicios import conformidad_rico

    ex = exportar(db, fondo_completo)
    reporte = conformidad_rico.reporte(ex)
    assert reporte["owl"]["problemas"] == []
    assert reporte["shacl"]["conforme"], reporte["shacl"]["resultados"]
    assert not [k for k in ex.omitidas if "dominio o rango" in k]


def test_las_pruebas_del_mapeo_corren_sin_postgresql(tmp_path):
    """La base de pruebas ya no es «autouse»: las pruebas que no la piden
    corren aunque PostgreSQL esté detenido (segunda mitad de O-31)."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    entorno = os.environ | {"DATABASE_URL": "postgresql+psycopg2://ricora:ricora@127.0.0.1:1/inexistente"}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_ric_o.py"],
                       cwd=raiz, env=entorno, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:]
    assert "error" not in r.stdout.splitlines()[-1].lower()
