"""
Evaluación por roles separados, referencia adjudicada, prueba piloto y versión congelada.

- Cada rol hace una sola cosa: la descriptora describe a ciegas, la validadora trabaja con la
  propuesta delante, la adjudicadora consolida la referencia y la calificadora califica.
- La referencia adjudicada exige dos descripciones ciegas enviadas, una adjudicadora que no vio la
  propuesta y una justificación escrita.
- Los documentos de la prueba piloto solo los trabaja el rol piloto y no entran en los resultados.
- Al iniciar se congela la versión del sistema, del motor, de la instrucción y del perfil SHACL.
- Resultados: A0 (motor) y A1 (asistida) frente a la referencia, con el IC de la diferencia;
  calibración de la certeza; coincidencias por aserción; hoja ciega con la llave aparte.
- La puesta en marcha no borra nada si hay una evaluación en curso.
"""

import io
import uuid
import zipfile

from openpyxl import load_workbook

from app.models.evaluacion import Evaluacion
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import documento, fondo  # noqa: F401
from tests.test_evaluacion import (CIEGA_A, CIEGA_B, TEXTO, _registrar_quien_administra, anotar,  # noqa: F401
                                   motor_eval, registrar_experta)


def _experta(cliente, db, ev_id, correo, rol):
    usuario = crear_usuario(db, correo, "archivista", nombre=correo.split("@")[0].title())
    registrar_experta(db, db.get(Evaluacion, uuid.UUID(ev_id)), usuario, rol=rol)
    db.commit()
    return ingresar(cliente, correo)


def _preparar(cliente, db, fondo, adm, piloto=False):  # noqa: F811
    d = documento(db, fondo, "Oficio_210_1948.pdf", TEXTO)
    ev = cliente.post("/api/evaluacion", headers=adm, json={"fondo_id": str(fondo.id), "nombre": "Con roles",
                                                             "umbral_similitud": 0.75}).json()
    cliente.put(f"/api/evaluacion/{ev['id']}/criterio", headers=adm,
                json={"margen_f": 0.10, "minimo_casos": 1, "rubrica_minima": 3, "conformidad_asistida": 1.0})
    r = cliente.post(f"/api/evaluacion/{ev['id']}/documentos", headers=adm,
                     json={"instanciacion_ids": [str(d.id)], "piloto": piloto})
    assert r.status_code == 200, r.text
    cliente.post(f"/api/evaluacion/{ev['id']}/propuestas", headers=adm)
    _registrar_quien_administra(cliente, db, adm, ev["id"])
    return ev["id"], d


def _iniciar(cliente, adm, ev_id):
    r = cliente.post(f"/api/evaluacion/{ev_id}/estado", headers=adm, json={"estado": "en_curso"})
    assert r.status_code == 200, r.text


def test_cada_rol_hace_una_sola_cosa_y_la_referencia_se_adjudica_con_justificacion(cliente, db, fondo, cabeceras_admin,  # noqa: F811
                                                                                   motor_eval):
    adm = cabeceras_admin
    ev_id, d = _preparar(cliente, db, fondo, adm)
    ana = _experta(cliente, db, ev_id, "ana@correo.com", "descriptora")
    luis = _experta(cliente, db, ev_id, "luis@correo.com", "descriptora")
    vale = _experta(cliente, db, ev_id, "vale@correo.com", "validadora")
    rosa = _experta(cliente, db, ev_id, "rosa@correo.com", "adjudicadora")
    _iniciar(cliente, adm, ev_id)
    # Versión congelada al iniciar.
    v = cliente.get(f"/api/evaluacion/{ev_id}/tareas", headers=adm).json()["evaluacion"]["version_congelada"]
    assert v and v["motor"] and v["perfil_shacl_sha256"] and len(v["perfil_shacl_sha256"]) == 64

    # La validadora no describe a ciegas; la descriptora no trabaja con la propuesta delante.
    assert anotar(cliente, vale, ev_id, d.id, "ciega").status_code == 403
    assert anotar(cliente, ana, ev_id, d.id, "asistida").status_code == 403
    # La adjudicadora no puede empezar sin dos ciegas enviadas.
    r = anotar(cliente, rosa, ev_id, d.id, "adjudicada")
    assert r.status_code == 409 and "dos descripciones ciegas" in r.json()["detail"]
    assert anotar(cliente, ana, ev_id, d.id, "ciega", CIEGA_A).status_code == 200
    assert anotar(cliente, luis, ev_id, d.id, "ciega", CIEGA_B).status_code == 200
    # Ve las dos ciegas por código, sin la propuesta del motor.
    refs = cliente.get(f"/api/evaluacion/{ev_id}/documentos/{d.id}/referencias", headers=rosa)
    assert refs.status_code == 200 and len(refs.json()) == 2
    assert all(x["codigo"].startswith("E") for x in refs.json()) and "confianza" not in str(refs.json())
    # Sin justificación no se envía la referencia.
    a = cliente.post(f"/api/evaluacion/{ev_id}/documentos/{d.id}/anotar", headers=rosa,
                     json={"condicion": "adjudicada"}).json()
    referencia = {"titulo": "Oficio 210 de 1948", "entidades": CIEGA_A["entidades"] + CIEGA_B["entidades"][1:]}
    r = cliente.put(f"/api/evaluacion/anotaciones/{a['id']}", headers=rosa, json=referencia | {"enviar": True})
    assert r.status_code == 422 and "diferencias" in r.json()["detail"]
    r = cliente.put(f"/api/evaluacion/anotaciones/{a['id']}", headers=rosa,
                    json=referencia | {"enviar": True, "justificacion": "Se unió lo que registraron E2 y E3."})
    assert r.status_code == 200, r.text
    # La validadora trabaja con la propuesta delante.
    asistida = cliente.post(f"/api/evaluacion/{ev_id}/documentos/{d.id}/anotar", headers=vale,
                            json={"condicion": "asistida"})
    assert asistida.status_code == 200
    r = cliente.put(f"/api/evaluacion/anotaciones/{asistida.json()['id']}", headers=vale,
                    json=asistida.json()["datos"] | {"enviar": True})
    assert r.status_code == 200, r.text

    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=adm).json()
    ref = res["referencia_adjudicada"]
    assert ref["documentos"] == 1 and ref["tipos"]
    agente = next(t for t in ref["tipos"] if t["tipo"] == "agente")
    assert {"A0", "A1"} <= set(agente) and agente["A0"]["estado"] in ("no_inferior", "inferior", "datos_insuficientes",
                                                                      "sin_techo")
    assert "superioridad" in ref["nota"]
    # El veredicto principal sale del IC de la referencia adjudicada y coincide con su estado por tipo.
    comp = res["comparabilidad"]
    assert comp["base"] == "referencia_adjudicada_ic95"
    estado_ref = {"no_inferior": "comparable", "inferior": "no_comparable"}
    for t in comp["tipos"]:
        fila = next((x for x in ref["tipos"] if x["tipo"] == t["tipo"]), None)
        if fila and fila["A0"]["estado"] in estado_ref and t["estado"] in ("comparable", "no_comparable"):
            assert t["estado"] == estado_ref[fila["A0"]["estado"]] or t["motivos"]
    cal = res["calibracion"]
    assert len(cal["tramos"]) == 10 and cal["propuestas"] >= 1

    # Coincidencias por aserción para recalcular fuera del sistema.
    x = cliente.get(f"/api/evaluacion/{ev_id}/resultados/coincidencias", headers=adm)
    libro = load_workbook(io.BytesIO(x.content))
    assert {"Coincidencias", "Tiempos", "Versión"} <= set(libro.sheetnames)
    comparaciones = {f[1].value for f in libro["Coincidencias"].iter_rows(min_row=2)}
    assert {"A0 frente a R", "A1 frente a R", "B2 frente a B1"} <= comparaciones
    # Hoja ciega: sin origen ni certeza; la llave en otro archivo.
    z = zipfile.ZipFile(io.BytesIO(cliente.get(f"/api/evaluacion/{ev_id}/hoja-ciega", headers=adm).content))
    assert set(z.namelist()) == {"calificacion-ciega.xlsx", "llave-de-codigos.xlsx"}
    hoja = load_workbook(io.BytesIO(z.read("calificacion-ciega.xlsx"))).active
    texto = " ".join(str(c.value or "") for fila in hoja.iter_rows() for c in fila)
    assert "motor" not in texto.lower() and "confianza" not in texto.lower() and "E2" not in texto
    llave = load_workbook(io.BytesIO(z.read("llave-de-codigos.xlsx"))).active
    assert {f[1].value for f in llave.iter_rows(min_row=2)} >= {"A0", "B"}


def test_los_documentos_de_la_prueba_piloto_no_entran_en_los_resultados(cliente, db, fondo, cabeceras_admin,  # noqa: F811
                                                                      motor_eval):
    adm = cabeceras_admin
    ev_id, d = _preparar(cliente, db, fondo, adm, piloto=True)
    pia = _experta(cliente, db, ev_id, "pia@correo.com", "piloto")
    ana = _experta(cliente, db, ev_id, "ana@correo.com", "descriptora")
    _iniciar(cliente, adm, ev_id)
    # Solo el rol piloto lo trabaja; para las demás no aparece en sus tareas.
    assert anotar(cliente, ana, ev_id, d.id, "ciega").status_code == 403
    assert cliente.get(f"/api/evaluacion/{ev_id}/tareas", headers=ana).json()["tareas"] == []
    assert anotar(cliente, pia, ev_id, d.id, "ciega", CIEGA_A).status_code == 200
    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=adm).json()
    assert res["documentos"] == [] and res["anotaciones"]["ciegas"] == 0


def test_la_puesta_en_marcha_no_borra_con_una_evaluacion_en_curso(cliente, db, fondo, cabeceras_admin, motor_eval):  # noqa: F811
    from tests.conftest import CONTRASENA
    from app.servicios import reinicio

    ev_id, _ = _preparar(cliente, db, fondo, cabeceras_admin)
    _iniciar(cliente, cabeceras_admin, ev_id)
    r = cliente.post("/api/sistema/reinicio", headers=cabeceras_admin,
                     json={"contrasena": CONTRASENA, "frase": reinicio.FRASE})
    assert r.status_code == 409 and "evaluación en curso" in r.json()["detail"]


def test_con_una_evaluacion_en_curso_el_asistente_no_consulta_internet(cliente, db, fondo, cabeceras_admin,  # noqa: F811
                                                                     motor_eval, monkeypatch):
    from app.core.config import settings
    from app.servicios import asistente

    llamadas = []

    class Motor:
        modelo = "gemini-de-prueba"

        def conversar(self, instruccion, contenido, buscar=False):
            llamadas.append(buscar)
            return "respuesta"

    assert asistente.internet_permitido(db)
    ev_id, _ = _preparar(cliente, db, fondo, cabeceras_admin)
    _iniciar(cliente, cabeceras_admin, ev_id)
    from app.servicios import motor

    monkeypatch.setattr(motor, "motor_activo", lambda: Motor())
    assert not asistente.internet_permitido(db)
    for fuentes in ("auto", "internet"):
        r = cliente.post("/api/asistente/preguntar", headers=cabeceras_admin, json={
            "fuentes": fuentes, "mensajes": [{"rol": "persona", "texto": "¿Cuál es la capital de Mongolia?"}]})
        assert r.status_code == 200 and "no consulta internet" in r.json()["respuesta"]
    assert True not in llamadas  # ninguna llamada con búsqueda en Google
    # El modo evaluación también lo apaga y avisa al menú.
    monkeypatch.setattr(settings, "modo_evaluacion", True)
    from app.models.usuario import Usuario
    from app.routers import auth
    from sqlalchemy import select

    admin = db.scalar(select(Usuario).where(Usuario.rol == "administrador").limit(1))
    assert auth._breve(admin).modo_evaluacion is True
