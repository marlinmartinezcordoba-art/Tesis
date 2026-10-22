"""
Tabla de valoración documental (TVD, Acuerdo 004 de 2019) del fondo acumulado.

- La TVD sigue el recorrido de la TRD (versión, dependencias, banco, matriz,
  aplicar validado en RiC-O) con su propia numeración y su propio borrador.
- Cada TVD valora un periodo institucional (desde, hasta): sus reglas rigen los
  documentos producidos en ese periodo. No cierran la regla de la TRD ni la de
  otro periodo; un expediente de 2008 se valora con la TVD 2006–2011 y uno de
  2020 con la TRD.
- Dos TVD vigentes no se traslapan; una nueva del mismo periodo reemplaza a la
  anterior (que pasa a histórica) y anula, sin borrarla, la regla que cambia.
- En RiC-O cada TVD es una rico:Rule de tipo «Tabla de valoración documental»
  con su periodo y las reglas que rigen en él.
"""

import uuid

from rdflib import Literal
from sqlalchemy import select

from app.models.recurso_documental import RecursoDocumental
from app.servicios import cuadro, retencion
from tests.test_descripcion import archivista, eventos, fondo, motor_prueba  # noqa: F401
from tests.test_especializacion_ric import exportar_conforme
from tests.test_parametrizacion_trd import aplicar_trd

TVD = """Dependencia;Código;Serie;Código serie;Subserie;Código subserie;Tipos documentales;AC;CT;E;S;M;Procedimiento
Despacho del Ministro;100;Actas;2;Actas del Comité Directivo;1;"Citación; Acta";20;X;;;;Conservar por su valor histórico.
Despacho del Ministro;100;Correspondencia;7;;;Oficio;5;;X;;;Eliminar: sin valores secundarios.
"""


def _filas(texto=TVD):
    return cuadro.vista_previa(texto.encode("utf-8"), "tvd.csv")["filas"]


def _tvd(cliente, cab, fondo, periodo, desde, hasta, filas, acto="Resolución 0790"):  # noqa: F811
    v = cliente.post("/api/trd/versiones", headers=cab, json={
        "fondo_id": str(fondo.id), "instrumento": "tvd", "periodo": periodo, "periodo_desde": desde,
        "periodo_hasta": hasta, "acto_aprobacion": acto, "fecha_aprobacion": "2020-05-10",
        "convalidacion": "Certificado AGN 0412", "copiar_vigente": False})
    assert v.status_code == 201, v.text
    r = cliente.post(f"/api/trd/versiones/{v.json()['id']}/importar", headers=cab, json={"filas": filas})
    assert r.status_code == 200, r.text
    return v.json(), cliente.post(f"/api/trd/versiones/{v.json()['id']}/aplicar", headers=cab)


def _serie(db, fondo, codigo):  # noqa: F811
    return db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fondo.id,
                                                     RecursoDocumental.codigo_referencia == codigo))


def _expediente(db, fondo, serie, fechas):  # noqa: F811
    e = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo=f"Expediente {fechas}", fondo_id=fondo.id,
                          incluido_en_id=serie.id, fechas_extremas_edtf=fechas)
    db.add(e)
    db.flush()
    return retencion.retencion_de(db, e)


def test_la_tvd_valora_su_periodo_y_la_trd_lo_que_sigue(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab = cabeceras_admin
    filas = _filas()
    assert all(not f["problemas"] for f in filas) and filas[0]["central"] == 20
    v, r = _tvd(cliente, cab, fondo, "Periodo 2: MAVDT", "2006-09-12", "2011-09-26", filas)
    assert v["nombre"] == "TVD Periodo 2: MAVDT" and v["instrumento"] == "tvd" and v["numero"] == 1
    assert r.status_code == 200, r.text
    assert r.json()["aplicada"] and r.json()["validacion"]["conforme"]
    # La TRD del fondo, aparte: su propia versión 1, desde 2019, con otra retención para Actas.
    trd = [dict(f, central=10, disposicion="s") if f["serie"]["nombre"] == "Actas" else f for f in filas]
    assert aplicar_trd(cliente, cab, fondo, trd, desde="2019-03-01").status_code == 200
    trds = cliente.get("/api/trd/versiones", headers=cab, params={"fondo_id": str(fondo.id)}).json()
    tvds = cliente.get("/api/trd/versiones", headers=cab, params={"fondo_id": str(fondo.id), "instrumento": "tvd"}).json()
    assert [(x["nombre"], x["estado"]) for x in trds] == [("TRD versión 1", "vigente")]
    assert [(x["nombre"], x["estado"], x["periodo_desde"]) for x in tvds] == [
        ("TVD Periodo 2: MAVDT", "vigente", "2006-09-12")]
    actas = _serie(db, fondo, "100.2.1")
    viejo, nuevo = _expediente(db, fondo, actas, "2007-02-01/2008-11-30"), _expediente(db, fondo, actas, "2020-01-10/2021-03-01")
    assert (viejo["central_anios"], viejo["disposicion_final"], viejo["vigencia"]) == (
        20, "conservacion_total", "2006-09-12/2011-09-26")
    assert (nuevo["central_anios"], nuevo["disposicion_final"]) == (10, "seleccion")
    correspondencia = _expediente(db, fondo, _serie(db, fondo, "100.7"), "2009-05-05/2009-12-31")
    assert (correspondencia["central_anios"], correspondencia["disposicion_final"]) == (5, "eliminacion")
    # En RiC-O: una rico:Rule por TVD, de tipo «Tabla de valoración documental», con su periodo.
    ex = exportar_conforme(db, fondo)
    assert (None, None, Literal("Tabla de valoración documental")) in ex.grafo
    assert any("Valora el periodo institucional «Periodo 2: MAVDT»" in str(o) for o in ex.grafo.objects())


def test_periodos_que_se_traslapan_y_una_tvd_que_reemplaza_a_otra(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab = cabeceras_admin
    _, r = _tvd(cliente, cab, fondo, "Periodo 2: MAVDT", "2006-09-12", "2011-09-26", _filas())
    assert r.status_code == 200
    # Otro periodo que se cruza con el primero: no se aplica (cada documento, una sola TVD).
    v, r = _tvd(cliente, cab, fondo, "Periodo mal fechado", "2010-01-01", "2013-12-31", _filas())
    assert r.status_code == 409 and "se traslapa" in r.json()["detail"]
    cliente.post(f"/api/trd/versiones/{v['id']}/anular", headers=cab, json={"motivo": "Fechas erradas"})
    # Una TVD nueva del mismo periodo (corregida) reemplaza a la vigente; la regla que cambia se anula, no se borra.
    corregida = _filas(TVD.replace("Oficio;5;;X", "Oficio;8;;X"))
    v2, r = _tvd(cliente, cab, fondo, "Periodo 2: MAVDT", "2006-09-12", "2011-09-26", corregida, acto="Resolución 1100")
    assert r.status_code == 200, r.text
    assert r.json()["informe"]["reglas_reemplazadas"] == 1 and r.json()["informe"]["reglas_sin_cambio"] == 1
    tvds = {x["numero"]: x for x in cliente.get("/api/trd/versiones", headers=cab,
                                                params={"fondo_id": str(fondo.id), "instrumento": "tvd"}).json()}
    assert (tvds[1]["estado"], tvds[2]["estado"], tvds[3]["estado"]) == ("historica", "anulada", "vigente")
    caso = _expediente(db, fondo, _serie(db, fondo, "100.7"), "2009-05-05/2009-12-31")
    assert caso["central_anios"] == 8
    assert len(eventos(db, "regla_cerrada")) == 1
    exportar_conforme(db, fondo)


def test_la_tvd_pide_su_periodo_y_no_estorba_a_la_trd(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab = cabeceras_admin
    v = cliente.post("/api/trd/versiones", headers=cab, json={"fondo_id": str(fondo.id), "instrumento": "tvd"}).json()
    assert v["nombre"] == "TVD versión 1"
    cliente.post(f"/api/trd/versiones/{v['id']}/importar", headers=cab, json={"filas": _filas()})
    prueba = cliente.post(f"/api/trd/versiones/{v['id']}/validar", headers=cab).json()
    assert "el nombre del periodo institucional" in prueba["informe"]["faltan_para_aplicar"]
    assert "las fechas del periodo institucional (desde y hasta)" in prueba["informe"]["faltan_para_aplicar"]
    assert cliente.post(f"/api/trd/versiones/{v['id']}/aplicar", headers=cab).status_code == 400
    r = cliente.patch(f"/api/trd/versiones/{v['id']}", headers=cab, json={"periodo_desde": "2011-01-01",
                                                                          "periodo_hasta": "2006-01-01"})
    assert r.status_code == 400 and "termina antes de empezar" in r.json()["detail"]
    # Un borrador de TVD no impide abrir el de la TRD (cada instrumento lleva el suyo).
    trd = cliente.post("/api/trd/versiones", headers=cab, json={"fondo_id": str(fondo.id)})
    assert trd.status_code == 201 and trd.json()["nombre"] == "TRD versión 1"
    assert cliente.post("/api/trd/versiones", headers=cab, json={"fondo_id": str(fondo.id),
                                                                "instrumento": "tvd"}).status_code == 409
