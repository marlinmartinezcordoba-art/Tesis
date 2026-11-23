"""
Evaluación del rendimiento del motor con la medida F1 (objetivo 3).

La referencia es la descripción que la archivista valida en Descripción: cada propuesta aceptada
es un verdadero positivo, cada rechazada un falso positivo, cada agregada un falso negativo y
cada corregida un falso positivo y un falso negativo. Los textos libres no entran en la F1 global.
"""

import io

import pytest
from openpyxl import load_workbook

from app.models.evaluacion import Evaluacion
from app.servicios import evaluacion as ev_s
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import (OFICIO_114, OFICIO_115, aceptar_todo, archivista, documento, eventos, fondo,  # noqa: F401
                                    iniciar, motor_prueba)


# --- Métricas (a mano) ---------------------------------------------------------------------------


def test_cada_decision_cuenta_como_dice_la_metodologia():
    c = ev_s.conteo(["aceptada", "aceptada", "rechazada", "agregada", "corregida"])
    assert (c["vp"], c["fp"], c["fn"]) == (2, 2, 2)
    m = ev_s.prf(c)
    assert m == {"precision": 0.5, "exhaustividad": 0.5, "f1": 0.5}
    assert ev_s.prf(ev_s.conteo([])) == {"precision": None, "exhaustividad": None, "f1": None}


def test_los_textos_libres_no_entran_en_la_f1_global():
    filas = [{"tipo": "agente", "decision": "aceptada", "documento_id": "a"},
             {"tipo": "fecha", "decision": "aceptada", "documento_id": "a"},
             {"tipo": "titulo", "decision": "corregida", "documento_id": "a"},
             {"tipo": "alcance", "decision": "corregida", "documento_id": "a"}]
    m = ev_s.metricas(filas)
    assert m["f1"] == 1.0 and m["conteo"]["vp"] == 2
    titulo = next(t for t in m["por_tipo"] if t["tipo"] == "titulo")
    assert titulo["texto_libre"] and titulo["f1"] == 0.0
    assert m["f1_macro"] == 1.0  # el promedio entre tipos tampoco los incluye


def test_el_intervalo_es_reproducible_y_contiene_el_valor():
    docs = [{"vp": 8, "fp": 1, "fn": 2}, {"vp": 5, "fp": 2, "fn": 1}, {"vp": 9, "fp": 0, "fn": 1},
            {"vp": 4, "fp": 3, "fn": 2}, {"vp": 7, "fp": 1, "fn": 0}]
    a, b = ev_s.intervalo(docs, "f1"), ev_s.intervalo(docs, "f1")
    assert a == b and a["remuestreos"] == ev_s.REMUESTREOS
    total = ev_s.prf({k: sum(d[k] for d in docs) for k in ("vp", "fp", "fn")})["f1"]
    assert a["inferior"] <= total <= a["superior"]


def test_el_dictamen_usa_el_limite_inferior():
    m = {"f1": 0.85, "precision": 0.90, "exhaustividad": 0.82,
         "intervalos": {"f1": {"inferior": 0.78}, "precision": {"inferior": 0.86}, "exhaustividad": {"inferior": 0.80}}}
    d = ev_s.dictamen(m, ev_s.CRITERIO_POR_DEFECTO)
    assert d["f1"]["cumple"] is False  # 0,85 supera 0,80, pero el límite inferior (0,78) no
    assert d["precision"]["cumple"] and d["exhaustividad"]["cumple"]
    assert d["hipotesis"] == "no se sostiene"


def test_el_anio_sale_del_nombre_del_archivo():
    assert ev_s.anio_de("Resolución 0818 de 2025.pdf") == "2025"
    assert ev_s.anio_de("res_2021_0045.pdf") == "2021"
    assert ev_s.anio_de("borrador.pdf") == "sin año"


# --- Flujo completo ------------------------------------------------------------------------------


def crear_evaluacion(cliente, cab, fondo, ids):
    r = cliente.post("/api/evaluacion", headers=cab, json={"fondo_id": str(fondo.id), "nombre": "Prueba RICORA"})
    assert r.status_code == 201, r.text
    ev_id = r.json()["id"]
    r = cliente.post(f"/api/evaluacion/{ev_id}/documentos", headers=cab, json={"instanciacion_ids": [str(i) for i in ids]})
    assert r.status_code == 200, r.text
    return ev_id


def test_el_sorteo_es_reproducible_con_la_misma_semilla(cliente, db, fondo, cabeceras_admin):
    ids = [documento(db, fondo, f"Resolucion {n} de {anio}.pdf", f"Texto {n}").id
           for n, anio in enumerate([2021, 2021, 2022, 2022, 2023, 2023, 2024, 2024, 2025, 2025])]
    resultados = []
    for _ in range(2):
        ev_id = crear_evaluacion(cliente, cabeceras_admin, fondo, ids)
        r = cliente.post(f"/api/evaluacion/{ev_id}/sorteo", headers=cabeceras_admin, json={"semilla": 2026, "desarrollo": 3})
        assert r.status_code == 200, r.text
        assert r.json()["desarrollo"] == 3 and r.json()["prueba"] == 7 and len(r.json()["estratos"]) == 5
        docs = cliente.get(f"/api/evaluacion/{ev_id}/documentos", headers=cabeceras_admin).json()
        resultados.append(sorted(d["instanciacion_id"] for d in docs if d["conjunto"] == "desarrollo"))
    assert resultados[0] == resultados[1]


def test_reglas_de_preparacion(cliente, db, fondo, cabeceras_admin, archivista, motor_prueba):  # noqa: F811
    a, b, c = (documento(db, fondo, f"Resolucion {n} de 2023.pdf", OFICIO_114).id for n in range(3))
    ev_id = crear_evaluacion(cliente, cabeceras_admin, fondo, [a, b, c])
    # Sin sorteo no se inicia.
    r = cliente.post(f"/api/evaluacion/{ev_id}/estado", headers=cabeceras_admin, json={"estado": "en_curso"})
    assert r.status_code == 409 and "sortee" in r.json()["detail"]
    assert cliente.put(f"/api/evaluacion/{ev_id}/criterio", headers=cabeceras_admin,
                       json={"f1": 0.75, "precision": 0.8, "exhaustividad": 0.7, "acuerdo": 0.8}).status_code == 200
    assert cliente.post(f"/api/evaluacion/{ev_id}/sorteo", headers=cabeceras_admin,
                        json={"semilla": 1, "desarrollo": 1}).status_code == 200
    # Tras el sorteo no se agregan ni se quitan documentos.
    d = documento(db, fondo, "otra.pdf", OFICIO_115)
    assert cliente.post(f"/api/evaluacion/{ev_id}/documentos", headers=cabeceras_admin,
                        json={"instanciacion_ids": [str(d.id)]}).status_code == 409
    assert cliente.post(f"/api/evaluacion/{ev_id}/estado", headers=cabeceras_admin,
                        json={"estado": "en_curso"}).status_code == 200
    ev = db.get(Evaluacion, ev_id)
    db.refresh(ev)
    assert ev.version_congelada["motor"] == "motor-de-prueba" and ev.version_congelada["version_instruccion"]
    assert ev.criterio["f1"] == 0.75
    # Los umbrales y el sorteo quedan congelados.
    assert cliente.put(f"/api/evaluacion/{ev_id}/criterio", headers=cabeceras_admin, json={"f1": 0.5}).status_code == 409
    assert cliente.post(f"/api/evaluacion/{ev_id}/sorteo", headers=cabeceras_admin,
                        json={"semilla": 2, "desarrollo": 1}).status_code == 409
    # Un documento ya descrito no entra a una evaluación nueva.
    espacio = iniciar(cliente, archivista, [d.id])
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio)).status_code == 201
    otra = cliente.post("/api/evaluacion", headers=cabeceras_admin, json={"fondo_id": str(fondo.id), "nombre": "Otra"}).json()
    r = cliente.post(f"/api/evaluacion/{otra['id']}/documentos", headers=cabeceras_admin,
                     json={"instanciacion_ids": [str(d.id)]})
    assert r.status_code == 422 and "descrito" in r.json()["detail"]
    # La archivista no administra la evaluación.
    assert cliente.post("/api/evaluacion", headers=archivista,
                        json={"fondo_id": str(fondo.id), "nombre": "No"}).status_code == 403


@pytest.fixture()
def evaluacion_en_curso(cliente, db, fondo, cabeceras_admin, motor_prueba):  # noqa: F811
    ids = [documento(db, fondo, f"Resolucion {n} de 2024.pdf", OFICIO_114).id for n in range(4)]
    ev_id = crear_evaluacion(cliente, cabeceras_admin, fondo, ids)
    assert cliente.post(f"/api/evaluacion/{ev_id}/sorteo", headers=cabeceras_admin,
                        json={"semilla": 7, "desarrollo": 1}).status_code == 200
    assert cliente.post(f"/api/evaluacion/{ev_id}/estado", headers=cabeceras_admin,
                        json={"estado": "en_curso"}).status_code == 200
    docs = cliente.get(f"/api/evaluacion/{ev_id}/documentos", headers=cabeceras_admin).json()
    desarrollo = [d["instanciacion_id"] for d in docs if d["conjunto"] == "desarrollo"]
    prueba = [d["instanciacion_id"] for d in docs if d["conjunto"] == "prueba"]
    return ev_id, desarrollo, prueba


def validar_con_errores(espacio):
    """Acepta casi todo: rechaza el lugar, corrige la forma documental y agrega un lugar que el motor no vio."""
    datos = aceptar_todo(espacio)
    datos["entidades"] = [e for e in datos["entidades"] if e["valor"] != "Boyacá"]
    for e in datos["entidades"]:
        if e["tipo"] == "forma_documental":
            e["valor"] = "Carta"
    datos["entidades"].append({"tipo": "lugar", "valor": "Tunja", "crear_nueva": True})
    return datos


def test_flujo_completo_calcula_la_f1_desde_las_decisiones(cliente, db, fondo, cabeceras_admin, archivista,
                                                         evaluacion_en_curso):
    ev_id, desarrollo, prueba = evaluacion_en_curso
    # El documento de desarrollo se describe, pero no entra en los resultados.
    espacio = iniciar(cliente, archivista, [desarrollo[0]])
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=validar_con_errores(espacio)).status_code == 201
    # Primer documento de prueba: todo aceptado. Segundo: con errores. El tercero queda sin publicar.
    espacio = iniciar(cliente, archivista, [prueba[0]])
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio)).status_code == 201
    espacio = iniciar(cliente, archivista, [prueba[1]])
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=validar_con_errores(espacio)).status_code == 201

    r = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=cabeceras_admin)
    assert r.status_code == 200, r.text
    res = r.json()
    c = res["metricas"]["conteo"]
    # 6 entidades aceptadas en el primero; en el segundo 4 aceptadas, 1 rechazada, 1 corregida y 1 agregada.
    assert (c["aceptada"], c["rechazada"], c["corregida"], c["agregada"]) == (10, 1, 1, 1)
    assert (c["vp"], c["fp"], c["fn"]) == (10, 2, 2)
    assert res["metricas"]["precision"] == round(10 / 12, 4) and res["metricas"]["f1"] == round(20 / 24, 4)
    assert res["metricas"]["documentos"] == 2
    assert any("todavía no se han validado" in a for a in res["avisos"])
    assert res["dictamen"]["f1"]["umbral"] == 0.80
    tipos = {t["tipo"]: t for t in res["metricas"]["por_tipo"]}
    assert tipos["titulo"]["texto_libre"] and not tipos["agente"]["texto_libre"]

    # La hoja de cálculo trae la hoja Decisiones con los encabezados que importa el Anexo D.
    r = cliente.get(f"/api/evaluacion/{ev_id}/resultados/hoja-de-calculo", headers=cabeceras_admin)
    assert r.status_code == 200
    libro = load_workbook(io.BytesIO(r.content))
    encabezado = [c.value for c in libro["Decisiones"][1]]
    for columna in ("Documento", "Tipo", "Propuesto por el motor", "Valor final", "Decisión", "Confianza"):
        assert columna in encabezado
    decisiones = [f[encabezado.index("Decisión")] for f in libro["Decisiones"].iter_rows(min_row=2, values_only=True)]
    assert decisiones.count("Agregada por la archivista") == 1
    assert libro["Resumen"]["A6"].value == "Medida F1"


def test_causas_de_error(cliente, db, fondo, cabeceras_admin, archivista, evaluacion_en_curso):
    ev_id, _, prueba = evaluacion_en_curso
    espacio = iniciar(cliente, archivista, [prueba[0]])
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=validar_con_errores(espacio)).status_code == 201
    errores = cliente.get(f"/api/evaluacion/{ev_id}/errores", headers=archivista).json()
    assert sorted(e["decision"] for e in errores if e["tipo"] not in ev_s.TEXTO_LIBRE) == ["agregada", "corregida", "rechazada"]
    rechazada = next(e for e in errores if e["decision"] == "rechazada")
    r = cliente.put(f"/api/evaluacion/{ev_id}/errores/{rechazada['evento_id']}", headers=archivista,
                    json={"causa": "invencion", "nota": "Boyacá no aparece como lugar del documento."})
    assert r.status_code == 200, r.text
    assert next(e for e in cliente.get(f"/api/evaluacion/{ev_id}/errores", headers=archivista).json()
                if e["evento_id"] == rechazada["evento_id"])["causa"] == "invencion"
    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=cabeceras_admin).json()
    assert {"causa": "invencion", "nombre": "Invención del motor", "cantidad": 1} in res["causas"]
    assert cliente.put(f"/api/evaluacion/{ev_id}/errores/{rechazada['evento_id']}", headers=archivista,
                       json={"causa": "otra"}).status_code == 422


def test_validacion_de_control_y_acuerdo(cliente, db, fondo, cabeceras_admin, archivista, evaluacion_en_curso):
    ev_id, _, prueba = evaluacion_en_curso
    espacio = iniciar(cliente, archivista, [prueba[0]])
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=validar_con_errores(espacio)).status_code == 201
    # Quien validó el documento no hace su control.
    assert cliente.get(f"/api/evaluacion/{ev_id}/control/{prueba[0]}", headers=archivista).status_code == 403
    crear_usuario(db, "zully@correo.com", "archivista", nombre="Zully")
    segunda = ingresar(cliente, "zully@correo.com")
    r = cliente.get(f"/api/evaluacion/{ev_id}/control/{prueba[0]}", headers=segunda)
    assert r.status_code == 200, r.text
    propuestas = r.json()["propuestas"]
    assert propuestas and all("decision" not in p for p in propuestas)  # no ve la decisión de la primera
    originales = {e.id: e.valor_nuevo["decision"] for e in eventos(db, "decision_ia")}
    # Coincide en todas menos en una.
    for i, p in enumerate(propuestas):
        decision = originales[p["evento_id"]]
        if i == 0:
            decision = "rechazada" if decision != "rechazada" else "aceptada"
        assert cliente.put(f"/api/evaluacion/{ev_id}/control/decisiones/{p['evento_id']}", headers=segunda,
                           json={"decision": decision}).status_code == 200
    a = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=cabeceras_admin).json()["acuerdo"]
    assert a["pares"] == len(propuestas) and a["iguales"] == len(propuestas) - 1 and a["documentos"] == 1
    assert a["porcentaje"] == round((len(propuestas) - 1) / len(propuestas), 4)


def test_solo_cuenta_la_version_congelada(cliente, db, fondo, cabeceras_admin, archivista, evaluacion_en_curso):
    ev_id, _, prueba = evaluacion_en_curso
    espacio = iniciar(cliente, archivista, [prueba[0]])
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio)).status_code == 201
    ev = db.get(Evaluacion, ev_id)
    ev.version_congelada = ev.version_congelada | {"version_instruccion": "otraversi"}
    db.commit()
    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=cabeceras_admin).json()
    assert res["decisiones"] == 0 and any("otra versión" in a for a in res["avisos"])


def test_solo_cuenta_la_primera_publicacion(cliente, db, fondo, cabeceras_admin, archivista, evaluacion_en_curso):
    ev_id, _, prueba = evaluacion_en_curso
    espacio = iniciar(cliente, archivista, [prueba[0]])
    publicado = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert publicado.status_code == 201
    antes = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=cabeceras_admin).json()["decisiones"]
    recurso = publicado.json()["id"]
    trabajo = cliente.post(f"/api/descripcion/registros/{recurso}/reabrir", headers=archivista).json()["trabajo_id"]
    assert cliente.patch(f"/api/descripcion/{recurso}", headers=archivista,
                         json={"trabajo_id": trabajo, "titulo": "Otro título"}).status_code == 200
    assert cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=cabeceras_admin).json()["decisiones"] == antes


def test_los_documentos_de_la_evaluacion_se_revisan_uno_a_uno(cliente, db, fondo, cabeceras_admin, archivista,
                                                               evaluacion_en_curso):
    """Si RICORA dejara aceptadas de antemano las propuestas (política «todo» o «de una vez»), la
    evaluación contaría como acierto lo que nadie revisó: en sus documentos la política es «revisar todo»."""
    from app.servicios import parametros


    db.commit()
    r = cliente.put("/api/descripcion/politica-ia", headers=cabeceras_admin, json={"politica": "todo"})
    assert r.status_code == 200, r.text
    assert parametros.politica_ia(db) == "todo"
    _, _, prueba = evaluacion_en_curso
    espacio = iniciar(cliente, archivista, [prueba[0]])
    assert espacio["politica_ia"] == "revisar_todo"
