"""
Cuadro de clasificación (CCD) y tabla de retención (TRD).

- Plantilla Excel del sistema y TRD en el formato del AGN, en Excel y en PDF:
  la misma interpretación, con vista previa que no crea nada.
- Aplicar crea sección, serie y subserie con código compuesto, la regla de
  retención unida a la serie o subserie, los tipos documentales y la
  dependencia productora; todo o nada; al repetir, reutiliza y no duplica.
- Solo la administración carga el cuadro; la exportación RiC-O sigue conforme.
"""

from sqlalchemy import select

from app.models.descripcion import EntidadVocabulario
from app.models.recurso_documental import RecursoDocumental
from app.servicios import cuadro, retencion
from tests.archivos import trd_agn_pdf, trd_agn_xlsx
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import eventos, fondo  # noqa: F401
from tests.test_especializacion_ric import exportar_conforme


def _vista(cliente, cab, contenido, nombre):
    return cliente.post("/api/cuadro/vista-previa", headers=cab, files={"archivo": (nombre, contenido)})


def test_la_trd_del_agn_en_excel_y_en_pdf_se_entiende_igual():
    a, b = cuadro.vista_previa(trd_agn_xlsx(), "trd.xlsx"), cuadro.vista_previa(trd_agn_pdf(), "trd.pdf")
    assert a["origen"].startswith("excel") and b["origen"].startswith("pdf")
    comparable = lambda v: [{k: x for k, x in f.items() if k not in ("fila", "procedimiento")} for f in v["filas"]]  # noqa: E731
    assert comparable(a) == comparable(b)
    actas = a["filas"][0]
    assert actas["seccion"] == {"codigo": "110", "nombre": "Secretaría General"}
    assert actas["codigos"] == {"seccion": "110", "subseccion": None, "serie": "110.2", "subserie": "110.2.1"}
    assert actas["tipos"] == ["Citación", "Acta", "Lista de asistencia"]
    # CT y M marcadas: la principal es conservación total; medio técnico queda anotado.
    assert (actas["gestion"], actas["central"], actas["disposicion"], actas["otras_disposiciones"]) == (2, 8, "ct", ["m"])
    correspondencia = a["filas"][2]
    assert correspondencia["subserie"] is None and correspondencia["tipos"] == ["Oficio", "Memorando", "Circular"]
    assert a["resumen"] == {"filas": 3, "con_problemas": 0, "secciones": 1, "series": 2, "subseries": 2,
                            "con_retencion": 3}


def test_la_plantilla_del_sistema_se_descarga_y_se_lee(cliente, cabeceras_admin):
    r = cliente.get("/api/cuadro/plantilla", headers=cabeceras_admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    v = _vista(cliente, cabeceras_admin, r.content, "plantilla.xlsx").json()
    assert v["origen"] == "excel · plantilla del sistema" and v["resumen"]["filas"] == 2
    assert v["filas"][0]["codigos"]["subserie"] == "100.2.1" and v["filas"][1]["disposicion"] == "e"


def test_aplicar_crea_el_cuadro_las_reglas_y_no_duplica(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    filas = _vista(cliente, cabeceras_admin, trd_agn_pdf(), "trd.pdf").json()["filas"]
    r = cliente.post("/api/cuadro/aplicar", headers=cabeceras_admin, json={"fondo_id": str(fondo.id), "filas": filas})
    assert r.status_code == 200, r.text
    inf = r.json()
    assert inf["creados"] == {"seccion": 1, "serie": 2, "subserie": 2} and inf["reglas"] == 3
    assert inf["reutilizados"] == 0  # lo creado en la misma carga no «ya existía»
    assert inf["tipos_documentales"] == 6  # Citación, Acta, Lista de asistencia, Oficio, Memorando, Circular
    por_codigo = {x.codigo_referencia: x for x in db.scalars(select(RecursoDocumental).where(
        RecursoDocumental.fondo_id == fondo.id, RecursoDocumental.codigo_referencia.is_not(None)))}
    assert por_codigo["110.2.1"].nivel == "subserie" and por_codigo["110.2.1"].incluido_en_id == por_codigo["110.2"].id
    assert por_codigo["110.2"].incluido_en_id == por_codigo["110"].id and por_codigo["110"].nivel == "seccion"
    regla = retencion.retencion_de(db, por_codigo["110.2.1"])
    assert regla["gestion_anios"] == 2 and regla["central_anios"] == 8
    assert regla["disposicion_final"] == "conservacion_total" and "medio técnico" in regla["procedimiento"]
    assert db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.nombre == "Secretaría General")).clase == "agente"
    assert len(eventos(db, "cuadro_importado")) == 1
    # Al repetir: reutiliza, no crea otra regla.
    inf2 = cliente.post("/api/cuadro/aplicar", headers=cabeceras_admin,
                        json={"fondo_id": str(fondo.id), "filas": filas}).json()
    assert inf2["creados"] == {} and inf2["reutilizados"] == 8 and inf2["reglas"] == 0 and len(inf2["avisos"]) == 3
    # El árbol del cuadro y la exportación RiC-O conforme.
    arbol = cliente.get("/api/cuadro", headers=cabeceras_admin, params={"fondo_id": str(fondo.id)}).json()
    assert arbol[0]["codigo"] == "110" and [h["codigo"] for h in arbol[0]["hijos"]] == ["110.15", "110.2"]
    assert arbol[0]["hijos"][1]["hijos"][0]["regla"]["disposicion_final"] == "conservacion_total"
    exportar_conforme(db, fondo)


def test_todo_o_nada_y_solo_la_administracion(cliente, db, fondo, cabeceras_admin):  # noqa: F811
    filas = cuadro.vista_previa(trd_agn_xlsx(), "trd.xlsx")["filas"]
    filas[1]["disposicion"] = None  # retención sin disposición final
    r = cliente.post("/api/cuadro/aplicar", headers=cabeceras_admin, json={"fondo_id": str(fondo.id), "filas": filas})
    assert r.status_code == 422 and "no disposición final" in r.json()["detail"]
    assert db.scalar(select(RecursoDocumental).where(RecursoDocumental.codigo_referencia == "110")) is None
    crear_usuario(db, "ana@correo.com", "archivista")
    ana = ingresar(cliente, "ana@correo.com")
    assert _vista(cliente, ana, trd_agn_xlsx(), "trd.xlsx").status_code == 403
    assert cliente.post("/api/cuadro/aplicar", headers=ana, json={"fondo_id": str(fondo.id), "filas": filas}).status_code == 403
    assert cliente.get("/api/cuadro", headers=ana, params={"fondo_id": str(fondo.id)}).status_code == 200
    r = _vista(cliente, cabeceras_admin, b"Nombre;Otra\n", "cosa.csv")
    assert r.status_code == 422 and "plantilla" in r.json()["detail"]
