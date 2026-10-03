"""
Cierre del hallazgo INS-02 de la auditoría RiC (Ley 1712 de 2014, arts.
18, 19 y 22): lo clasificado o reservado no se filtra por ningún camino
lateral. Son los tres casos que la auditoría reprodujo, más el
vencimiento de la reserva (art. 22).
"""

from datetime import date, timedelta

from rdflib import RDF

from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.preservacion import DeclaracionDerechos
from app.servicios import autoridad, exportacion_rico, parametros, vocabulario
from tests.conftest import crear_usuario, ingresar
from tests.test_exportacion_rico import fondo_rico, u  # noqa: F401
from tests.test_instrumentos import _recurso, archivista, fondo_descrito  # noqa: F401


def _reservar(db, f, tipo, entidad_id, admin, hasta=None):
    db.add(DeclaracionDerechos(fondo_id=f["fondo"].id, entidad_tipo=tipo, entidad_id=entidad_id, base="estatuto",
                               acceso="reservado", reproduccion="no_permitida",
                               fundamento="Ley 1712 de 2014, art. 19", vigente_hasta=hasta, creada_por_id=admin.id))


def _lector(db, cliente, correo):
    crear_usuario(db, correo, "consulta")
    return ingresar(cliente, correo)


def test_archivo_reservado_no_sale_en_rdf_ni_en_uri_ni_en_la_ficha(cliente, db, fondo_rico, admin, archivista):
    f = fondo_rico
    inst = db.query(Instanciacion).filter(Instanciacion.nombre_original == "Oficio_114_1948.pdf").one()
    _reservar(db, f, "instanciacion", inst.id, admin)
    db.commit()
    ex = exportacion_rico.exportar(db, f["fondo"])
    assert (u(inst.id), RDF.type, None) not in ex.grafo
    assert (u(f["o114"].id), RDF.type, None) in ex.grafo  # el documento sigue siendo público
    parametros.cambiar(db, "rdf_uris_publicas", True, admin.id, "instrumentos")
    db.commit()
    r = cliente.get(f"/id/{inst.id}")
    assert r.status_code == 404 and "Oficio_114_1948.pdf" not in r.text
    lector = _lector(db, cliente, "lector-ins02a@correo.com")
    for ruta in (f"/api/instrumentos/catalogo/{f['o114'].id}", f"/api/catalogo/registros/{f['o114'].id}"):
        r = cliente.get(ruta, headers=lector)
        assert r.status_code == 200 and "Oficio_114_1948.pdf" not in r.text, ruta
    # El archivista sí lo ve: la reserva no es un borrado.
    r = cliente.get(f"/api/instrumentos/catalogo/{f['o114'].id}", headers=archivista)
    assert "Oficio_114_1948.pdf" in r.text


def test_parte_y_documento_hermano_reservados_no_se_nombran_en_la_ficha(cliente, db, fondo_rico, admin):
    f = fondo_rico
    parte = f["parte"]
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=f["o114"].id, destino_tipo="recurso_documental",
                    destino_id=parte.id, tipo_relacion="inclusion", codigo_ric="has_or_had_constituent",
                    origen="persona"))
    parte.titulo = "Anotacion SECRETA del margen"
    _reservar(db, f, "recurso_documental", parte.id, admin)
    hermano = _recurso(db, "unidad_documental", "Oficio RESERVADO 116", f["exp48"], f["fondo"])
    _reservar(db, f, "recurso_documental", hermano.id, admin)
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=f["o114"].id, destino_tipo="recurso_documental",
                    destino_id=hermano.id, tipo_relacion="temporal", codigo_ric="precedes_or_preceded",
                    origen="persona"))
    db.commit()
    lector = _lector(db, cliente, "lector-ins02b@correo.com")
    for ruta in (f"/api/instrumentos/catalogo/{f['o114'].id}", f"/api/catalogo/registros/{f['o114'].id}"):
        r = cliente.get(ruta, headers=lector)
        assert r.status_code == 200, ruta
        assert "SECRETA" not in r.text and "RESERVADO 116" not in r.text, ruta
    assert cliente.get(f"/api/instrumentos/catalogo/{parte.id}", headers=lector).status_code == 404


def test_agente_citado_solo_en_un_documento_reservado_no_se_exporta_por_un_vinculo(db, fondo_rico, admin):
    f = fondo_rico
    reservado = _recurso(db, "unidad_documental", "Denuncia", f["exp49"], f["fondo"])
    informante = vocabulario.crear(db, fondo_id=f["fondo"].id, clase="agente", nombre="Informante Juan Perez",
                                   subtipo="persona", origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=reservado.id, destino_tipo="entidad_vocabulario",
                    destino_id=informante.id, tipo_relacion="procedencia", codigo_ric="has_creator", origen="persona"))
    _reservar(db, f, "recurso_documental", reservado.id, admin)
    autoridad.vincular(db, tipo="asociado", desde=f["alcaldia"], con_tipo="entidad_vocabulario",
                       con_id=informante.id, usuario_id=admin.id)
    db.commit()
    ex = exportacion_rico.exportar(db, f["fondo"])
    assert (u(informante.id), RDF.type, None) not in ex.grafo
    assert (u(reservado.id), RDF.type, None) not in ex.grafo
    assert (u(f["alcaldia"].id), RDF.type, None) in ex.grafo
    # Con permiso de escritura y la exportación completa, sí sale.
    completo = exportacion_rico.exportar(db, f["fondo"], incluir_restringidos=True)
    assert (u(informante.id), RDF.type, None) in completo.grafo


def test_agente_de_contexto_sin_documentos_se_sigue_exportando(db, fondo_rico, admin):
    """La regla no borra el contexto puro: una institución antecesora que no
    cita ningún documento sigue saliendo (ISAAR-CPF 5.3)."""
    f = fondo_rico
    cabildo = vocabulario.crear(db, fondo_id=f["fondo"].id, clase="agente", nombre="Cabildo colonial",
                                subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None,
                                usuario_id=admin.id)
    db.flush()
    autoridad.vincular(db, tipo="sucesor", desde=cabildo, con_tipo="entidad_vocabulario", con_id=f["alcaldia"].id,
                       usuario_id=admin.id)
    db.commit()
    ex = exportacion_rico.exportar(db, f["fondo"])
    assert (u(cabildo.id), RDF.type, None) in ex.grafo


def test_la_reserva_vencida_se_levanta_sola(cliente, db, fondo_rico, admin):
    """Ley 1712, art. 22: la reserva dura lo que dice su plazo; vencido, el
    documento vuelve a ser público sin que nadie tenga que recordarlo."""
    f = fondo_rico
    vencido = _recurso(db, "unidad_documental", "Oficio con reserva vencida", f["exp48"], f["fondo"])
    vigente = _recurso(db, "unidad_documental", "Oficio con reserva vigente", f["exp48"], f["fondo"])
    _reservar(db, f, "recurso_documental", vencido.id, admin, hasta=date.today() - timedelta(days=1))
    _reservar(db, f, "recurso_documental", vigente.id, admin, hasta=date.today() + timedelta(days=30))
    db.commit()
    ex = exportacion_rico.exportar(db, f["fondo"])
    assert (u(vencido.id), RDF.type, None) in ex.grafo
    assert (u(vigente.id), RDF.type, None) not in ex.grafo
    lector = _lector(db, cliente, "lector-ins02c@correo.com")
    assert cliente.get(f"/api/instrumentos/catalogo/{vencido.id}", headers=lector).status_code == 200
    assert cliente.get(f"/api/instrumentos/catalogo/{vigente.id}", headers=lector).status_code == 404


def test_archivo_reservado_tampoco_aparece_en_el_grafo(cliente, db, fondo_rico, admin, archivista):
    f = fondo_rico
    inst = db.query(Instanciacion).filter(Instanciacion.nombre_original == "Oficio_114_1948.pdf").one()
    _reservar(db, f, "instanciacion", inst.id, admin)
    db.commit()
    lector = _lector(db, cliente, "lector-ins02d@correo.com")
    ruta = f"/api/grafo/recurso_documental/{f['o114'].id}"
    r = cliente.get(ruta, headers=lector)
    assert r.status_code == 200 and "Oficio_114_1948.pdf" not in r.text
    assert cliente.get(f"/api/grafo/instanciacion/{inst.id}", headers=lector).status_code == 404
    assert "Oficio_114_1948.pdf" in cliente.get(ruta, headers=archivista).text
