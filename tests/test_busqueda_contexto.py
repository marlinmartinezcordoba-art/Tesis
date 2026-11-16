"""Consulta por contexto RiC en el buscador: afinar por función (tipo de actividad), actividad,
lugar, mandato o forma documental, y listar sin texto los documentos de una entidad («¿qué
documentos responden a la función de correspondencia oficial?»), con la misma reserva."""

from sqlalchemy import select

from app.models.descripcion import EntidadVocabulario, Relacion
from app.servicios import vocabulario
from tests.test_brechas_lote4 import _buscar, _reservar, _titulos, fondo  # noqa: F401
from tests.test_grafo_contexto import consulta  # noqa: F401
from tests.test_instrumentos import archivista, fondo_descrito  # noqa: F401


def _funcion(db, f):
    """El oficio 114 documenta una actividad cuyo tipo (la función) es «Correspondencia oficial»."""
    crear = dict(fondo_id=f["fondo"].id, subtipo=None, origen="persona", confianza=None, motor=None, usuario_id=None)
    act = vocabulario.crear(db, clase="actividad", nombre="Informe de daños en el archivo", **crear)
    fun = vocabulario.crear(db, clase="tipo_actividad", nombre="Correspondencia oficial", **crear)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=f["o114"].id, destino_tipo="entidad_vocabulario",
                    destino_id=act.id, tipo_relacion="asociacion", codigo_ric="documents", origen="persona"))
    db.add(Relacion(origen_tipo="entidad_vocabulario", origen_id=act.id, destino_tipo="entidad_vocabulario",
                    destino_id=fun.id, tipo_relacion="asociacion", codigo_ric="has_activity_type", origen="persona"))
    db.commit()
    return act, fun


def test_facetas_de_contexto_por_clase_ric(cliente, db, fondo, archivista):  # noqa: F811
    _, fun = _funcion(db, fondo)
    d = _buscar(cliente, archivista, "oficio")
    clases = {c["clase"]: {e["nombre"] for e in c["entidades"]} for c in d["facetas"]["contextos"]}
    assert "Correspondencia oficial" in clases["tipo_actividad"]  # la función, a través de la actividad
    assert "Informe de daños en el archivo" in clases["actividad"]
    assert "Boyacá" in clases["lugar"] and "Oficio" in clases["forma_documental"]
    assert "Alcaldía Municipal" in clases["agente"] and d["facetas"]["agentes"]
    assert _titulos(_buscar(cliente, archivista, "oficio", contexto_id=str(fun.id))) == ["Oficio N.º 114"]


def test_sin_texto_lista_los_documentos_de_la_entidad(cliente, db, fondo, archivista):  # noqa: F811
    _, fun = _funcion(db, fondo)
    d = _buscar(cliente, archivista, "", contexto_id=str(fun.id))
    assert _titulos(d) == ["Oficio N.º 114"] and d["contexto"]["nombre"] == "Correspondencia oficial"
    assert d["documentos"][0]["motivos"] == ["relacionado con Correspondencia oficial"]
    produjo = _buscar(cliente, archivista, "", contexto_id=str(fondo["alcaldia"].id))
    assert set(_titulos(produjo)) >= {"Oficio N.º 114", "Correspondencia 1949"}
    assert cliente.get("/api/buscar", headers=archivista).status_code == 422


def test_la_consulta_por_contexto_respeta_la_reserva(cliente, db, fondo, archivista, consulta):  # noqa: F811
    _, fun = _funcion(db, fondo)
    _reservar(db, fondo, "recurso_documental", fondo["o114"].id)
    assert _buscar(cliente, consulta, "", contexto_id=str(fun.id))["total"] == 0
    nombres = {e["nombre"] for c in _buscar(cliente, consulta, "oficio")["facetas"]["contextos"] for e in c["entidades"]}
    assert "Correspondencia oficial" not in nombres and "Boyacá" not in nombres
    assert _buscar(cliente, archivista, "", contexto_id=str(fun.id))["total"] == 1
