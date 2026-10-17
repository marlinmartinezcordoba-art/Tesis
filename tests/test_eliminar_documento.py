"""
Documentos cargados por error: solo la administración los elimina, solo si
nunca se describieron, y queda constancia en la auditoría (nombre, huella,
quién, cuándo y por qué). Y la ingesta lee el texto de las hojas de cálculo.
"""


from openpyxl import Workbook

from app.models.instanciacion import Instanciacion
from app.servicios import texto
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import aceptar_todo, documento, eventos, fondo, iniciar, motor_prueba  # noqa: F401
from tests.test_evaluacion import motor_eval, preparar  # noqa: F401

MOTIVO = {"motivo": "Se cargó un borrador personal por error."}


def test_la_administracion_elimina_un_documento_nunca_descrito_y_queda_constancia(cliente, db, fondo, cabeceras_admin):
    d = documento(db, fondo, "borrador.pdf", "Texto cualquiera")
    d.huella = "a" * 64
    db.commit()
    crear_usuario(db, "ana@correo.com", "archivista")
    ana = ingresar(cliente, "ana@correo.com")
    assert cliente.post(f"/api/ingesta/{d.id}/eliminar", headers=ana, json=MOTIVO).status_code == 403
    assert cliente.post(f"/api/ingesta/{d.id}/eliminar", headers=cabeceras_admin, json={"motivo": "x"}).status_code == 422
    r = cliente.post(f"/api/ingesta/{d.id}/eliminar", headers=cabeceras_admin, json=MOTIVO)
    assert r.status_code == 204, r.text
    db.expire_all()
    assert db.get(Instanciacion, d.id) is None
    [ev] = eventos(db, "documento_eliminado", d.id)
    assert ev.detalle == MOTIVO["motivo"] and ev.valor_anterior["nombre"] == "borrador.pdf"
    assert ev.valor_anterior["huella"] == "a" * 64 and ev.valor_anterior["fondo_id"] == str(fondo.id)
    assert cliente.post(f"/api/ingesta/{d.id}/eliminar", headers=cabeceras_admin, json=MOTIVO).status_code == 404


def test_lo_descrito_o_en_edicion_no_se_elimina(cliente, db, fondo, cabeceras_admin, motor_prueba):  # noqa: F811
    d = documento(db, fondo, "oficio.pdf", "Oficio 114 de 1948.")
    espacio = iniciar(cliente, cabeceras_admin, [d.id])
    r = cliente.post(f"/api/ingesta/{d.id}/eliminar", headers=cabeceras_admin, json=MOTIVO)
    assert r.status_code == 409 and "describiendo" in r.json()["detail"]
    assert cliente.post("/api/descripcion/publicar", headers=cabeceras_admin, json=aceptar_todo(espacio)).status_code == 201
    r = cliente.post(f"/api/ingesta/{d.id}/eliminar", headers=cabeceras_admin, json=MOTIVO)
    assert r.status_code == 409 and "valoración" in r.json()["detail"]
    assert db.get(Instanciacion, d.id) is not None


def test_un_documento_en_una_evaluacion_no_se_elimina(cliente, db, fondo, cabeceras_admin, motor_eval):  # noqa: F811
    _, d = preparar(cliente, db, fondo, cabeceras_admin)
    r = cliente.post(f"/api/ingesta/{d.id}/eliminar", headers=cabeceras_admin, json=MOTIVO)
    assert r.status_code == 409 and "evaluación" in r.json()["detail"]


def test_la_ingesta_lee_el_texto_de_un_excel(tmp_path):
    libro = Workbook()
    h = libro.active
    h.title = "Inventario"
    h.append(["Código", "Serie", "Fechas"])
    h.append(["110.2", "Actas del Concejo", "1948-1952"])
    otra = libro.create_sheet("Notas")
    otra.append(["Revisado por el archivo central"])
    ruta = tmp_path / "inventario.xlsx"
    libro.save(ruta)
    t = texto.extraer(ruta, None, lambda *_: None)
    assert t.origen == "capa_de_texto"
    assert "Hoja: Inventario" in t.contenido and "110.2 | Actas del Concejo | 1948-1952" in t.contenido
    assert "Hoja: Notas" in t.contenido
    roto = tmp_path / "roto.xlsx"
    roto.write_bytes(b"no es un excel")
    try:
        texto.extraer(roto, None, lambda *_: None)
        raise AssertionError("debió fallar")
    except texto.ArchivoIlegible:
        pass
