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
    # El veredicto principal es la hipótesis preregistrada (F puntual frente a las ciegas); el IC frente a la
    # referencia adjudicada es complementario y coincide con su estado por tipo.
    assert res["comparabilidad"]["base"] == "h1_f_puntual_frente_a_ciegas"
    comp = res["veredicto_complementario"]
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
    # Ningún código de experta (E1, E2…) como palabra: los códigos al azar de la hoja (p. ej. «4E2D2D») sí pueden
    # contener esas letras sin revelar nada.
    import re

    assert "motor" not in texto.lower() and "confianza" not in texto.lower() and not re.search(r"\bE\d+\b", texto)
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


def test_la_hoja_trae_el_instrumento_1_el_tiempo_del_motor_y_la_evidencia_de_cada_fuente(cliente, db, fondo,  # noqa: F811
                                                                                        cabeceras_admin, motor_eval):
    """Trazabilidad (aserciones con evidencia textual, para el motor y para las archivistas),
    eficiencia (tiempo por unidad documental, también el del motor) y la matriz de evaluación ciega
    con sus columnas."""
    adm = cabeceras_admin
    ev_id, d = _preparar(cliente, db, fondo, adm)
    ana = _experta(cliente, db, ev_id, "ana@correo.com", "ambas")
    _iniciar(cliente, adm, ev_id)
    con_evidencia = {**CIEGA_A, "entidades": [dict(e, evidencia="Tunja, 14 de marzo de 1948") if i == 0 else e
                                              for i, e in enumerate(CIEGA_A["entidades"])]}
    assert anotar(cliente, ana, ev_id, d.id, "ciega", con_evidencia).status_code == 200
    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=adm).json()
    ciega = res["indicadores"]["ciega"]["evidencia"]
    assert ciega["con_evidencia"] == 1 and ciega["entidades"] == len(CIEGA_A["entidades"])
    assert res["indicadores"]["motor"]["evidencia"]["entidades"] >= 1
    assert res["tiempos"]["motor"]["n"] == 1 and res["tiempos"]["motor"]["mediana_minutos"] is not None
    libro = load_workbook(io.BytesIO(cliente.get(f"/api/evaluacion/{ev_id}/resultados/hoja-de-calculo", headers=adm).content))
    hoja = libro["Matriz de evaluación ciega"]
    assert [c.value for c in hoja[1]][:8] == ["ID Unidad Documental", "Experta (código)",
                                              "Tipo de entidad RiC-CM / propiedad RiC-O", "Valor propuesto por el motor",
                                              "Valor en la descripción ciega de la experta", "Resultado (VP, FP o FN)",
                                              "Clase de desacuerdo", "Tipo de error"]
    filas = [[c.value for c in f] for f in hoja.iter_rows(min_row=2)]
    datos = [f for f in filas if f[5] in ("VP", "FP", "FN")]
    assert datos and all(f[0] == "Oficio_210_1948.pdf" and f[1].startswith("E") for f in datos)
    assert any(f[0] == "TOTALES (micro)" and str(f[8]).startswith("=IFERROR") for f in filas)


def test_la_asistida_se_compara_con_las_ciegas_de_otras_y_cada_descripcion_pasa_por_el_perfil_shacl(  # noqa: F811
        cliente, db, fondo, cabeceras_admin, motor_eval):
    """La versión validada (asistida) frente a las ciegas, nunca frente a la ciega de la misma
    persona; y el porcentaje de descripciones conformes con el perfil SHACL."""
    adm = cabeceras_admin
    ev_id, d = _preparar(cliente, db, fondo, adm)
    ana = _experta(cliente, db, ev_id, "ana@correo.com", "ambas")
    luis = _experta(cliente, db, ev_id, "luis@correo.com", "ambas")
    _iniciar(cliente, adm, ev_id)
    assert anotar(cliente, ana, ev_id, d.id, "ciega", CIEGA_A).status_code == 200
    assert anotar(cliente, luis, ev_id, d.id, "ciega", CIEGA_B).status_code == 200
    a = cliente.post(f"/api/evaluacion/{ev_id}/documentos/{d.id}/anotar", headers=ana, json={"condicion": "asistida"}).json()
    assert cliente.put(f"/api/evaluacion/anotaciones/{a['id']}", headers=ana,
                       json=a["datos"] | {"enviar": True}).status_code == 200
    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=adm).json()
    af = res["asistida_frente_a_ciegas"]
    assert af["pares"] == 1  # la asistida de Ana solo frente a la ciega de Luis
    assert af["flexible"]["micro"]["vp"] + af["flexible"]["micro"]["fp"] > 0
    for fuente, n in (("motor", 1), ("ciega", 2), ("asistida", 1)):
        s = res["indicadores"][fuente]["shacl"]
        assert s["descripciones"] == n and 0 <= s["conformes"] <= n
    libro = load_workbook(io.BytesIO(cliente.get(f"/api/evaluacion/{ev_id}/resultados/hoja-de-calculo", headers=adm).content))
    assert libro["Asistida frente a ciegas"]["C1"].value == 1
    filas = [f[0].value for f in libro["Normalización y cobertura"].iter_rows()]
    assert "Descripciones conformes con el perfil SHACL" in filas


def test_una_descripcion_completa_cumple_el_perfil_shacl_y_sin_titulo_no():
    from app.servicios import evaluacion_ric as ric

    completa = {"titulo": "Oficio 210 de 1948", "entidades": [
        {"tipo": "agente", "rol": "productor", "valor": "Alcaldía de Tunja", "subtipo": "entidad_corporativa"},
        {"tipo": "fecha", "valor": "1948 a 1950", "edtf": "1948/1950"},
        {"tipo": "forma_documental", "valor": "oficio"}]}
    assert ric.shacl(ric.desde_roles(completa)) == {"conforme": True, "problemas": []}
    sin_titulo = ric.shacl(ric.desde_roles(dict(completa, titulo="")))
    assert not sin_titulo["conforme"] and any("título" in p for p in sin_titulo["problemas"])
    # Un destinatario sin clase de agente no cumple la forma de rico:hasAddressee.
    sin_clase = ric.shacl(ric.desde_roles(dict(completa, entidades=completa["entidades"] + [
        {"tipo": "agente", "rol": "destinatario", "valor": "Concejo"}])))
    assert not sin_clase["conforme"]


def test_si_quien_administra_participa_como_experta_queda_advertido(cliente, db, fondo, cabeceras_admin,  # noqa: F811
                                                                     motor_eval):
    """Conflicto de interés: quien administra la evaluación conoce el motor; no se bloquea (el piloto lo
    admite), pero queda marcado en la lista de expertas, en los resultados y en la hoja de cálculo."""
    adm = cabeceras_admin
    ev_id, _ = _preparar(cliente, db, fondo, adm)  # registra a quien administra como experta
    lista = cliente.get(f"/api/evaluacion/{ev_id}/participantes", headers=adm).json()
    assert [p["administra_la_evaluacion"] for p in lista] == [True]
    _experta(cliente, db, ev_id, "ana@correo.com", "descriptora")
    lista = cliente.get(f"/api/evaluacion/{ev_id}/participantes", headers=adm).json()
    assert sorted(p["administra_la_evaluacion"] for p in lista) == [False, True]
    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=adm).json()
    assert len(res["advertencias"]) == 1 and "no es independiente" in res["advertencias"][0]
    libro = load_workbook(io.BytesIO(cliente.get(f"/api/evaluacion/{ev_id}/resultados/hoja-de-calculo", headers=adm).content))
    assert any(str(f[0].value or "").startswith("Advertencia:") for f in libro["Expertas"].iter_rows())
