"""
Cierre de brechas, lote 6 · Versiones y atributos (RF-RIC-001 y RF-RIC-002).

- RF-RIC-001: publicar y corregir dos veces deja 3 versiones con autor y
  cambios; restaurar la versión 1 crea la versión 4 con los atributos de
  la 1; ninguna versión se modifica ni se borra.
- RF-RIC-002: un atributo multivaluado rechaza pasar de su cardinalidad y
  cada valor muestra su fuente (motor, motor corregido, persona) en la
  vista interna.
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models.version_descripcion import VersionDescripcion
from app.servicios import atributos
from tests.test_descripcion import (OFICIO_114, RESPUESTA_UNO, aceptar_todo, archivista, documento, eventos,  # noqa: F401
                                    fondo, iniciar, motor_prueba)

TITULO_2 = "Oficio sobre la conservación del archivo municipal"
TITULO_3 = "Oficio de la Alcaldía sobre el archivo municipal, 1948"


def _publicado(cliente, db, fondo, archivista):  # noqa: F811
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    r = cliente.post("/api/descripcion/publicar", headers=archivista,
                     json=aceptar_todo(iniciar(cliente, archivista, [d.id]), idiomas=["spa"]))
    assert r.status_code == 201, r.text
    return r.json()


def _editar(cliente, cab, rid, **cambios):
    trabajo = cliente.post(f"/api/descripcion/registros/{rid}/reabrir", headers=cab).json()["trabajo_id"]
    r = cliente.patch(f"/api/descripcion/{rid}", headers=cab, json={"trabajo_id": trabajo, **cambios})
    assert r.status_code == 200, r.text
    return r.json()


# --- RF-RIC-001 ----------------------------------------------------------------------------------


def test_editar_dos_veces_deja_tres_versiones_con_autor_y_cambios_y_se_restaura_la_primera(
        cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    registro = _publicado(cliente, db, fondo, archivista)
    rid = registro["id"]
    _editar(cliente, archivista, rid, titulo=TITULO_2)
    _editar(cliente, archivista, rid, titulo=TITULO_3, agregar_entidades=[{"tipo": "lugar", "valor": "Tunja",
                                                                            "crear_nueva": True}])
    versiones = cliente.get(f"/api/descripcion/registros/{rid}/versiones", headers=archivista).json()
    assert [v["numero"] for v in versiones] == [3, 2, 1]
    assert [v["motivo"] for v in versiones] == ["edicion", "edicion", "publicacion"]
    assert all(v["autor"] == "Catalina Torres" and v["integra"] for v in versiones)
    v2 = versiones[1]
    [titulo] = [c for c in v2["cambios"] if c["campo"] == "titulo"]
    assert titulo["antes"] == RESPUESTA_UNO["titulo"] and titulo["despues"] == TITULO_2
    # La procedencia viaja con el valor: del motor a una persona.
    assert titulo["fuente_antes"] == "motor" and titulo["fuente_despues"] == "persona"
    [ents] = [c for c in versiones[0]["cambios"] if c["campo"] == "entidades"]
    assert any("Tunja" in x for x in ents["agregados"]) and ents["quitados"] == []

    r = cliente.post(f"/api/descripcion/registros/{rid}/versiones/1/restaurar", headers=archivista)
    assert r.status_code == 200, r.text
    assert r.json()["titulo"] == RESPUESTA_UNO["titulo"] and r.json()["origen_titulo"] == "motor"
    versiones = cliente.get(f"/api/descripcion/registros/{rid}/versiones", headers=archivista).json()
    assert versiones[0]["numero"] == 4 and versiones[0]["motivo"] == "restauracion" and versiones[0]["restaurada_de"] == 1
    assert len(eventos(db, "descripcion_restaurada", rid)) == 1
    # El contexto (Tunja) no se deshace con la restauración: tiene su propia historia.
    assert any(e["valor"] == "Tunja" for e in r.json()["entidades"])
    completa = cliente.get(f"/api/descripcion/registros/{rid}/versiones/2", headers=archivista).json()
    assert completa["contenido"]["atributos"]["titulo"] == TITULO_2 and completa["integra"]


def test_una_correccion_sin_cambios_no_crea_version_y_la_vigente_no_se_restaura(
        cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    rid = _publicado(cliente, db, fondo, archivista)["id"]
    _editar(cliente, archivista, rid)
    assert len(cliente.get(f"/api/descripcion/registros/{rid}/versiones", headers=archivista).json()) == 1
    r = cliente.post(f"/api/descripcion/registros/{rid}/versiones/1/restaurar", headers=archivista)
    assert r.status_code == 409
    assert cliente.post(f"/api/descripcion/registros/{rid}/versiones/9/restaurar", headers=archivista).status_code == 404


def test_no_se_restaura_mientras_alguien_la_edita(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    rid = _publicado(cliente, db, fondo, archivista)["id"]
    _editar(cliente, archivista, rid, titulo=TITULO_2)
    cliente.post(f"/api/descripcion/registros/{rid}/reabrir", headers=archivista)
    r = cliente.post(f"/api/descripcion/registros/{rid}/versiones/1/restaurar", headers=archivista)
    assert r.status_code == 409 and "en edición" in r.json()["detail"]


def test_una_version_no_se_modifica_ni_se_borra(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    rid = _publicado(cliente, db, fondo, archivista)["id"]
    v = db.scalar(select(VersionDescripcion).where(VersionDescripcion.recurso_id == rid))
    assert len(v.huella) == 64
    for sentencia in ("UPDATE versiones_descripcion SET motivo = 'otra' WHERE id = :i",
                      "DELETE FROM versiones_descripcion WHERE id = :i"):
        with pytest.raises(DBAPIError, match="no se modifica ni se borra"):
            with db.begin_nested():
                db.execute(text(sentencia), {"i": v.id})


def test_la_consulta_no_ve_las_versiones(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    from tests.conftest import crear_usuario, ingresar

    rid = _publicado(cliente, db, fondo, archivista)["id"]
    crear_usuario(db, "lector@correo.com", "consulta")
    lector = ingresar(cliente, "lector@correo.com")
    assert cliente.get(f"/api/descripcion/registros/{rid}/versiones", headers=lector).status_code == 403


# --- RF-RIC-002 ----------------------------------------------------------------------------------


def test_un_atributo_multivaluado_rechaza_pasar_de_su_cardinalidad(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    rid = _publicado(cliente, db, fondo, archivista)["id"]
    trabajo = cliente.post(f"/api/descripcion/registros/{rid}/reabrir", headers=archivista).json()["trabajo_id"]
    r = cliente.patch(f"/api/descripcion/{rid}", headers=archivista,
                      json={"trabajo_id": trabajo, "idiomas": ["spa", "lat", "eng", "fra", "por", "ita"]})
    assert r.status_code == 422 and "máximo 5" in r.json()["detail"] and "Lenguas" in r.json()["detail"]
    with pytest.raises(atributos.ErrorAtributo, match="obligatorio"):
        atributos.validar_cardinalidad("titulo", "  ")


def test_cada_valor_muestra_su_fuente_en_la_vista_interna(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    rid = _publicado(cliente, db, fondo, archivista)["id"]
    detalle = _editar(cliente, archivista, rid, condiciones_acceso="Consulta en sala")
    por_clave = {a["clave"]: a for a in detalle["atributos"]}
    assert por_clave["titulo"]["fuente"] == "motor"
    assert por_clave["alcance_contenido"]["fuente"] == "motor" and por_clave["alcance_contenido"]["confianza"] == 0.85
    assert por_clave["condiciones_acceso"]["fuente"] == "persona"
    assert por_clave["idiomas"]["cardinalidad"] == "0..n" and por_clave["titulo"]["cardinalidad"] == "1..1"
    catalogo = cliente.get("/api/descripcion/atributos", headers=archivista).json()
    titulo = next(a for a in catalogo if a["clave"] == "titulo")
    assert titulo["rico"] == "rico:title" and titulo["isad"] == "3.1.2" and titulo["minimo"] == 1


def test_el_catalogo_cubre_las_columnas_que_versiona_la_migracion():
    """La migración 0037 copió la lista de columnas: si el catálogo crece, la
    versión inicial y las nuevas deben seguir comparándose igual."""
    import importlib.util
    from pathlib import Path

    ruta = Path(__file__).parent.parent / "alembic" / "versions" / "0037_versiones_descripcion.py"
    spec = importlib.util.spec_from_file_location("m0037", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert set(m.COLUMNAS) == {a.clave for a in atributos.ATRIBUTOS} | set(atributos.PROCEDENCIA)
