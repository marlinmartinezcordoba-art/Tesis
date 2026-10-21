"""
Parametrización de la TRD y el CCD en el orden de los SGDEA.

- Dependencias, banco terminológico (series, subseries, tipos) y matriz por
  dependencia en una versión en borrador; validar no crea nada.
- Aplicar exige el acto de aprobación y la vigencia, arma el cuadro en RiC-O
  conforme y deja la versión vigente; lo vigente no se edita.
- Una versión nueva que cambia la retención no borra ni modifica la regla
  anterior: cierra su vigencia y crea la nueva; cada expediente se rige por la
  regla vigente en su fecha final.
- El archivo de la TRD (formato AGN) llena el borrador; solo la
  administración parametriza; lo usado no se anula.
"""

import uuid

from sqlalchemy import select

from app.models.recurso_documental import RecursoDocumental
from app.servicios import retencion
from tests.archivos import trd_agn_pdf
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import archivista, eventos, fondo, motor_prueba  # noqa: F401
from tests.test_especializacion_ric import exportar_conforme


def _post(cliente, cab, ruta, datos, codigo=201):
    r = cliente.post(ruta, headers=cab, json=datos)
    assert r.status_code == codigo, r.text
    return r.json() if r.content else None


def aplicar_trd(cliente, cab, fondo, filas, desde="2019-03-01", acto="Resolución 045"):  # noqa: F811
    """El cuadro de un fondo, por el único camino: una versión de la TRD cargada desde las filas
    leídas del archivo y aplicada. Devuelve la respuesta de aplicar (o la del paso que falló)."""
    v = cliente.post("/api/trd/versiones", headers=cab, json={
        "fondo_id": str(fondo.id), "acto_aprobacion": acto, "fecha_aprobacion": desde, "vigente_desde": desde})
    if v.status_code != 201:
        return v
    r = cliente.post(f"/api/trd/versiones/{v.json()['id']}/importar", headers=cab, json={"filas": filas})
    if r.status_code != 200:
        return r
    return cliente.post(f"/api/trd/versiones/{v.json()['id']}/aplicar", headers=cab)


def _armar(cliente, cab, fondo):  # noqa: F811
    f = str(fondo.id)
    sec = _post(cliente, cab, "/api/trd/dependencias", {"fondo_id": f, "codigo": "100", "nombre": "Secretaría General"})
    ofi = _post(cliente, cab, "/api/trd/dependencias", {"fondo_id": f, "codigo": "110", "nombre": "Archivo",
                                                        "superior_id": sec["id"]})
    actas = _post(cliente, cab, "/api/trd/banco", {"fondo_id": f, "clase": "serie", "codigo": "2", "nombre": "Actas"})
    comite = _post(cliente, cab, "/api/trd/banco", {"fondo_id": f, "clase": "subserie", "codigo": "1",
                                                    "nombre": "Actas del Comité de Archivo", "superior_id": actas["id"]})
    tipos = [_post(cliente, cab, "/api/trd/banco", {"fondo_id": f, "clase": "tipo_documental", "nombre": n})["id"]
             for n in ("Citación", "Acta")]
    v = _post(cliente, cab, "/api/trd/versiones", {"fondo_id": f})
    fila = _post(cliente, cab, f"/api/trd/versiones/{v['id']}/filas", {
        "dependencia_id": ofi["id"], "serie_id": actas["id"], "subserie_id": comite["id"], "tipos": tipos,
        "gestion": 2, "central": 8, "disposicion": "ct", "otras_disposiciones": ["m"], "soporte": "hibrido",
        "procedimiento": "Se conserva por su valor histórico."})
    return {"seccion": sec, "oficina": ofi, "serie": actas, "subserie": comite, "tipos": tipos, "version": v,
            "fila": fila}


def test_parametrizar_validar_y_aplicar_una_version(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab, a = cabeceras_admin, _armar(cliente, cabeceras_admin, fondo)
    assert a["oficina"]["codigo_completo"] == "100.110" and a["subserie"]["codigo_completo"] == "2.1"
    assert a["fila"]["codigo"] == "100.110.2.1" and a["fila"]["nombres_tipos"] == ["Citación", "Acta"]
    vid = a["version"]["id"]
    # Validar no crea nada y dice qué falta para aplicar.
    prueba = _post(cliente, cab, f"/api/trd/versiones/{vid}/validar", None, 200)
    assert prueba["aplicada"] is False and prueba["validacion"]["conforme"]
    assert len(prueba["informe"]["faltan_para_aplicar"]) == 3
    assert db.scalar(select(RecursoDocumental).where(RecursoDocumental.codigo_referencia == "100.110.2.1")) is None
    r = cliente.post(f"/api/trd/versiones/{vid}/aplicar", headers=cab)
    assert r.status_code == 400 and "acto administrativo" in r.json()["detail"]
    r = cliente.patch(f"/api/trd/versiones/{vid}", headers=cab, json={
        "acto_aprobacion": "Resolución 045", "fecha_aprobacion": "2019-02-15", "vigente_desde": "2019-03-01",
        "convalidacion": "Certificado de convalidación 12"})
    assert r.status_code == 200, r.text
    hecho = _post(cliente, cab, f"/api/trd/versiones/{vid}/aplicar", None, 200)
    assert hecho["aplicada"] and hecho["version"]["estado"] == "vigente" and not hecho["version"]["editable"]
    sub = db.scalar(select(RecursoDocumental).where(RecursoDocumental.codigo_referencia == "100.110.2.1"))
    regla = retencion.retencion_de(db, sub)
    assert (regla["gestion_anios"], regla["central_anios"], regla["disposicion_final"]) == (2, 8, "conservacion_total")
    assert regla["vigencia"] == "2019-03-01/" and "Soporte: híbrido" in regla["procedimiento"]
    assert "Resolución 045" in regla["procedimiento"]
    assert len(eventos(db, "trd_version_aplicada")) == 1
    # Lo vigente no se edita.
    r = cliente.post(f"/api/trd/versiones/{vid}/filas", headers=cab, json={
        "dependencia_id": a["oficina"]["id"], "serie_id": a["serie"]["id"]})
    assert r.status_code == 409
    exportar_conforme(db, fondo)


def test_version_nueva_cierra_la_regla_anterior_y_cada_expediente_usa_la_de_su_fecha(cliente, db, fondo,  # noqa: F811
                                                                                       cabeceras_admin):
    cab, a = cabeceras_admin, _armar(cliente, cabeceras_admin, fondo)
    v1 = a["version"]["id"]
    cliente.patch(f"/api/trd/versiones/{v1}", headers=cab, json={
        "acto_aprobacion": "Resolución 045", "fecha_aprobacion": "2019-02-15", "vigente_desde": "2019-03-01"})
    _post(cliente, cab, f"/api/trd/versiones/{v1}/aplicar", None, 200)
    # Solo un borrador a la vez; la versión 2 parte de la vigente.
    v2 = _post(cliente, cab, "/api/trd/versiones", {"fondo_id": str(fondo.id), "acto_aprobacion": "Resolución 210",
                                                   "fecha_aprobacion": "2024-06-01", "vigente_desde": "2024-07-01"})
    assert v2["numero"] == 2 and v2["filas"] == 1
    assert cliente.post("/api/trd/versiones", headers=cab, json={"fondo_id": str(fondo.id)}).status_code == 409
    fila = cliente.get(f"/api/trd/versiones/{v2['id']}/filas", headers=cab).json()[0]
    r = cliente.put(f"/api/trd/filas/{fila['id']}", headers=cab, json={
        "dependencia_id": fila["dependencia_id"], "serie_id": fila["serie_id"], "subserie_id": fila["subserie_id"],
        "tipos": fila["tipos"], "gestion": 3, "central": 12, "disposicion": "s"})
    assert r.status_code == 200, r.text
    hecho = _post(cliente, cab, f"/api/trd/versiones/{v2['id']}/aplicar", None, 200)
    assert hecho["informe"]["reglas_reemplazadas"] == 1 and hecho["validacion"]["conforme"]
    versiones = {v["numero"]: v for v in cliente.get("/api/trd/versiones", headers=cab,
                                                     params={"fondo_id": str(fondo.id)}).json()}
    assert versiones[1]["estado"] == "historica" and versiones[1]["vigente_hasta"] == "2024-06-30"
    assert versiones[2]["estado"] == "vigente"
    sub = db.scalar(select(RecursoDocumental).where(RecursoDocumental.codigo_referencia == "100.110.2.1"))
    hoy = retencion.retencion_de(db, sub)
    assert (hoy["central_anios"], hoy["disposicion_final"], hoy["versiones"]) == (12, "seleccion", 2)

    def expediente(fechas):
        e = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo=f"Actas {fechas}", fondo_id=fondo.id,
                              incluido_en_id=sub.id, fechas_extremas_edtf=fechas)
        db.add(e)
        db.flush()
        return retencion.retencion_de(db, e)

    viejo, nuevo = expediente("2020-01-10/2021-11-30"), expediente("2024-08-01/2025-03-01")
    assert viejo["central_anios"] == 8 and viejo["vigencia"] == "2019-03-01/2024-06-30"
    assert nuevo["central_anios"] == 12 and viejo["heredada_de"]["id"] == str(sub.id)
    assert len(eventos(db, "regla_cerrada")) == 1
    exportar_conforme(db, fondo)


def test_el_archivo_de_la_trd_llena_el_borrador(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab = cabeceras_admin
    filas = cliente.post("/api/cuadro/vista-previa", headers=cab,
                         files={"archivo": ("trd.pdf", trd_agn_pdf())}).json()["filas"]
    v = _post(cliente, cab, "/api/trd/versiones", {"fondo_id": str(fondo.id)})
    inf = _post(cliente, cab, f"/api/trd/versiones/{v['id']}/importar", {"filas": filas}, 200)
    assert inf == {"dependencias": 1, "series": 2, "subseries": 2, "tipos_documentales": 6, "filas": 3, "repetidas": 0}
    # Repetir no duplica.
    assert _post(cliente, cab, f"/api/trd/versiones/{v['id']}/importar", {"filas": filas}, 200)["repetidas"] == 3
    matriz = cliente.get(f"/api/trd/versiones/{v['id']}/filas", headers=cab).json()
    assert len(matriz) == 3 and {m["codigo_dependencia"] for m in matriz} == {"110"}
    banco = cliente.get("/api/trd/banco", headers=cab, params={"fondo_id": str(fondo.id), "clase": "serie"}).json()
    assert {b["nombre"] for b in banco} == {"ACTAS", "CORRESPONDENCIA"}


def test_solo_la_administracion_y_nada_usado_se_anula(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab, a = cabeceras_admin, _armar(cliente, cabeceras_admin, fondo)
    crear_usuario(db, "arch@trd.co", rol="archivista")
    db.commit()
    otro = ingresar(cliente, "arch@trd.co")
    assert cliente.post("/api/trd/dependencias", headers=otro, json={
        "fondo_id": str(fondo.id), "codigo": "200", "nombre": "Hacienda"}).status_code == 403
    assert cliente.get("/api/trd/dependencias", headers=otro, params={"fondo_id": str(fondo.id)}).status_code == 200
    # La dependencia y la serie están en la matriz del borrador: no se anulan.
    assert cliente.post(f"/api/trd/dependencias/{a['oficina']['id']}/anular", headers=cab).status_code == 409
    assert cliente.post(f"/api/trd/banco/{a['serie']['id']}/anular", headers=cab).status_code == 409
    assert cliente.post(f"/api/trd/banco/{a['tipos'][0]}/anular", headers=cab).status_code == 409
    # Código repetido y subserie sin serie.
    assert cliente.post("/api/trd/dependencias", headers=cab, json={
        "fondo_id": str(fondo.id), "codigo": "100", "nombre": "Otra"}).status_code == 409
    assert cliente.post("/api/trd/banco", headers=cab, json={
        "fondo_id": str(fondo.id), "clase": "subserie", "codigo": "9", "nombre": "Suelta"}).status_code == 400
    # Quitar la fila (queda anulada) y después sí se anulan.
    assert cliente.post(f"/api/trd/filas/{a['fila']['id']}/anular", headers=cab).status_code == 204
    assert cliente.post(f"/api/trd/banco/{a['subserie']['id']}/anular", headers=cab).status_code == 204
    assert cliente.post(f"/api/trd/banco/{a['serie']['id']}/anular", headers=cab).status_code == 204
    assert cliente.get("/api/trd/banco", headers=cab, params={"fondo_id": str(fondo.id), "clase": "serie"}).json() == []
    v = cliente.post(f"/api/trd/versiones/{a['version']['id']}/anular", headers=cab, json={"motivo": "prueba"}).json()
    assert v["estado"] == "anulada"


def test_la_version_1_fecha_las_reglas_cargadas_antes_de_parametrizar(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    cab = cabeceras_admin
    filas = cliente.post("/api/cuadro/vista-previa", headers=cab,
                         files={"archivo": ("trd.pdf", trd_agn_pdf())}).json()["filas"]
    # Un cuadro cargado antes de existir la parametrización (datos anteriores a esta versión del sistema).
    from app.models.usuario import Usuario
    from app.servicios import cuadro
    cuadro.aplicar(db, fondo, filas, db.scalar(select(Usuario.id).limit(1)))
    db.commit()
    v = _post(cliente, cab, "/api/trd/versiones", {"fondo_id": str(fondo.id), "acto_aprobacion": "Acuerdo 3",
                                                  "fecha_aprobacion": "2015-05-02", "vigente_desde": "2015-06-01"})
    _post(cliente, cab, f"/api/trd/versiones/{v['id']}/importar", {"filas": filas}, 200)
    hecho = _post(cliente, cab, f"/api/trd/versiones/{v['id']}/aplicar", None, 200)
    assert hecho["informe"]["reglas"] == 0 and hecho["informe"]["reglas_sin_cambio"] == 3
    serie = db.scalar(select(RecursoDocumental).where(RecursoDocumental.codigo_referencia == "110.15"))
    regla = retencion.retencion_de(db, serie)
    assert regla["vigencia"] == "2015-06-01/" and regla["vigencia_legible"].startswith("rige desde 1 de junio de 2015")


def test_el_fondo_nace_con_su_trd_vigente_y_el_cuadro_no_se_toca_suelto(cliente, db, cabeceras_admin, archivista,  # noqa: F811
                                                                         motor_prueba):
    from app.servicios import cuadro
    from tests.archivos import trd_agn_xlsx
    from tests.test_descripcion import OFICIO_114, aceptar_todo, documento, iniciar

    cab = cabeceras_admin
    filas = cuadro.vista_previa(trd_agn_xlsx(), "trd.xlsx")["filas"]
    r = cliente.post("/api/fondos/configurar", headers=cab, json={
        "fondo": {"titulo": "Archivo de Tunja"}, "filas": filas, "crear": True,
        "version": {"acto_aprobacion": "Resolución 045", "fecha_aprobacion": "2019-02-15", "vigente_desde": "2019-03-01"}})
    assert r.status_code == 200 and r.json()["creado"], r.text
    fnd = db.get(RecursoDocumental, uuid.UUID(r.json()["fondo"]["id"]))
    [v] = cliente.get("/api/trd/versiones", headers=cab, params={"fondo_id": str(fnd.id)}).json()
    assert v["estado"] == "vigente" and v["filas"] == 3
    serie = db.scalar(select(RecursoDocumental).where(RecursoDocumental.fondo_id == fnd.id,
                                                      RecursoDocumental.codigo_referencia == "110.15"))
    assert retencion.retencion_de(db, serie)["vigencia"] == "2019-03-01/"
    # Un documento de un fondo con cuadro va dentro de una serie, no suelto en el fondo.
    d = documento(db, fnd, "Oficio_114_1948.pdf", OFICIO_114)
    datos = aceptar_todo(iniciar(cliente, archivista, [d.id]))
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 422 and "serie" in r.json()["detail"], r.text
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos | {"incluido_en_id": str(serie.id)})
    assert r.status_code == 201, r.text
    # La serie no se renombra, recodifica ni mueve desde la descripción: eso lo hace la TRD.
    trabajo = cliente.post(f"/api/descripcion/registros/{serie.id}/reabrir", headers=archivista).json()["trabajo_id"]
    r = cliente.patch(f"/api/descripcion/{serie.id}", headers=archivista,
                      json={"trabajo_id": trabajo, "titulo": "Correspondencia enviada"})
    assert r.status_code == 409 and "TRD" in r.json()["detail"], r.text


def test_todo_parte_de_cargar_el_ccd_y_la_trd(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    from app.servicios import cuadro
    from tests.archivos import trd_agn_xlsx

    cab = cabeceras_admin
    filas = cuadro.vista_previa(trd_agn_xlsx(), "trd.xlsx")["filas"]
    # Fondo nuevo: la respuesta dice qué configuró la carga y en qué estado quedó la versión 1.
    r = cliente.post("/api/fondos/configurar", headers=cab, json={
        "fondo": {"titulo": "Fondo desde instrumentos"}, "filas": filas, "crear": True}).json()
    assert r["parametrizacion"] == {"dependencias": 1, "series": 2, "subseries": 2, "tipos_documentales": 6,
                                    "filas": 3, "repetidas": 0}
    assert r["version"] == {"nombre": "TRD versión 1", "estado": "borrador"}
    # Fondo existente: la carga abre el borrador de la versión siguiente y lo configura entero.
    c = cliente.post("/api/trd/cargar", headers=cab, json={"fondo_id": str(fondo.id), "filas": filas})
    assert c.status_code == 200, c.text
    assert c.json()["version"]["estado"] == "borrador" and c.json()["parametrizacion"]["filas"] == 3
    # Cargar otra vez reutiliza el mismo borrador sin duplicar.
    c2 = cliente.post("/api/trd/cargar", headers=cab, json={"fondo_id": str(fondo.id), "filas": filas}).json()
    assert c2["version"]["id"] == c.json()["version"]["id"] and c2["parametrizacion"]["repetidas"] == 3
