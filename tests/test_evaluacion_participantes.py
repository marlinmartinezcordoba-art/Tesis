"""
Expertas participantes (pregunta problema: humano frente a máquina).

Quién hizo cada descripción humana de referencia queda registrado con su
formación, su experiencia y su consentimiento. Solo describe quien está
registrada; los resultados la muestran por su código y comparan el motor
con la descripción ciega de cada una.
"""

import io
import uuid

from openpyxl import load_workbook

from app.models.usuario import Usuario
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import documento, fondo  # noqa: F401
from tests.test_evaluacion import CIEGA_A, CIEGA_B, TEXTO, anotar, motor_eval  # noqa: F401

EXPERTA = {"nombre": "Ana Ruiz", "profesion": "Profesional en Ciencia de la Información – Archivística",
           "formacion": "maestria", "anios_experiencia": 12, "anios_descripcion": 7, "cargo": "Archivista",
           "institucion": "Archivo Regional", "rol": "descriptora", "consentimiento": True}


def _evaluacion_lista(cliente, db, fondo, adm):  # noqa: F811
    d = documento(db, fondo, "Oficio_210_1948.pdf", TEXTO)
    ev = cliente.post("/api/evaluacion", headers=adm, json={"fondo_id": str(fondo.id), "nombre": "Humano y máquina",
                                                             "umbral_similitud": 0.75}).json()
    cliente.post(f"/api/evaluacion/{ev['id']}/documentos", headers=adm, json={"instanciacion_ids": [str(d.id)]})
    cliente.post(f"/api/evaluacion/{ev['id']}/propuestas", headers=adm)
    return ev["id"], d


def test_se_registran_las_expertas_y_solo_ellas_describen(cliente, db, fondo, cabeceras_admin, motor_eval):  # noqa: F811
    ev_id, d = _evaluacion_lista(cliente, db, fondo, cabeceras_admin)
    ana_u = crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    luis_u = crear_usuario(db, "luis@correo.com", "archivista", nombre="Luis Pardo")
    intrusa_u = crear_usuario(db, "otra@correo.com", "archivista", nombre="Otra Persona")
    ana, luis, intrusa = (ingresar(cliente, c) for c in ("ana@correo.com", "luis@correo.com", "otra@correo.com"))
    base = f"/api/evaluacion/{ev_id}/participantes"

    # Sin consentimiento no cuenta para iniciar.
    r = cliente.post(base, headers=cabeceras_admin, json=EXPERTA | {"usuario_id": str(ana_u.id), "consentimiento": False})
    assert r.status_code == 201 and r.json()["codigo"] == "E1" and r.json()["formacion_nombre"] == "Maestría"
    ana_p = r.json()["id"]
    r = cliente.post(f"/api/evaluacion/{ev_id}/estado", headers=cabeceras_admin, json={"estado": "en_curso"})
    assert r.status_code == 409 and "consentimiento" in r.json()["detail"]
    assert cliente.put(f"{base}/{ana_p}", headers=cabeceras_admin, json={"consentimiento": True}).json()["consentimiento"]
    r = cliente.post(base, headers=cabeceras_admin, json=EXPERTA | {"usuario_id": str(luis_u.id), "nombre": "Luis Pardo",
                                                                   "formacion": "profesional", "anios_experiencia": 5})
    assert r.json()["codigo"] == "E2"
    # La misma persona no se registra dos veces; una cuenta inexistente tampoco.
    assert cliente.post(base, headers=cabeceras_admin, json=EXPERTA | {"usuario_id": str(ana_u.id)}).status_code == 409
    assert cliente.post(base, headers=cabeceras_admin, json=EXPERTA | {"usuario_id": str(uuid.uuid4())}).status_code == 422
    # Solo la administración registra.
    assert cliente.post(base, headers=ana, json=EXPERTA | {"usuario_id": str(intrusa_u.id)}).status_code == 403
    assert cliente.post(f"/api/evaluacion/{ev_id}/estado", headers=cabeceras_admin, json={"estado": "en_curso"}).status_code == 200

    # Quien no está registrada no ve la evaluación ni describe.
    assert cliente.get("/api/evaluacion", headers=intrusa, params={"fondo_id": str(fondo.id)}).json() == []
    r = anotar(cliente, intrusa, ev_id, d.id, "ciega", CIEGA_A)
    assert r.status_code == 403 and "no está registrada" in r.json()["detail"]
    assert [e["id"] for e in cliente.get("/api/evaluacion", headers=ana, params={"fondo_id": str(fondo.id)}).json()] == [ev_id]
    # Una descriptora no califica la propuesta.
    r = cliente.post(f"/api/evaluacion/{ev_id}/documentos/{d.id}/propuesta", headers=ana)
    assert r.status_code == 403 and "describir" in r.json()["detail"]

    assert anotar(cliente, ana, ev_id, d.id, "ciega", CIEGA_A).status_code == 200
    assert anotar(cliente, luis, ev_id, d.id, "ciega", CIEGA_B).status_code == 200

    # Resultados: humano frente a máquina, experta por experta, con su perfil y sin su nombre.
    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=cabeceras_admin).json()
    por_codigo = {e["codigo"]: e for e in res["expertas"]}
    assert set(por_codigo) == {"E1", "E2"} and all(e["nombre"] is None for e in res["expertas"])
    assert por_codigo["E1"]["formacion_nombre"] == "Maestría" and por_codigo["E1"]["anios_experiencia"] == 12
    assert por_codigo["E1"]["documentos_descritos"] == 1
    assert por_codigo["E1"]["motor_frente_a_ella"]["entidades"]["f1"] is not None
    assert por_codigo["E1"]["motor_frente_a_ella"]["relaciones"]["f1"] is not None
    assert "Ana Ruiz" not in str(res)
    # El nombre lo ve solo la administración, en la lista de participantes.
    nombres = {p["codigo"]: p["nombre"] for p in cliente.get(base, headers=cabeceras_admin).json()}
    assert nombres == {"E1": "Ana Ruiz", "E2": "Luis Pardo"}
    hoja = cliente.get(f"/api/evaluacion/{ev_id}/resultados/hoja-de-calculo", headers=cabeceras_admin)
    libro = load_workbook(io.BytesIO(hoja.content))
    filas = [[c.value for c in f] for f in libro["Expertas"].iter_rows()]
    assert filas[0][0] == "Código" and {f[0] for f in filas[1:]} == {"E1", "E2"} and "Ana Ruiz" not in str(filas)

    # Retirar no borra: deja de describir, y lo que envió sigue contando con su código.
    assert cliente.put(f"{base}/{ana_p}", headers=cabeceras_admin, json={"retirar": True}).json()["activa"] is False
    assert anotar(cliente, ana, ev_id, d.id, "asistida").status_code == 403
    res = cliente.get(f"/api/evaluacion/{ev_id}/resultados", headers=cabeceras_admin).json()
    assert {e["codigo"] for e in res["expertas"]} == {"E1", "E2"}


def test_el_registro_queda_en_la_auditoria(cliente, db, fondo, cabeceras_admin, motor_eval):  # noqa: F811
    from sqlalchemy import select

    from app.models.auditoria import RegistroAuditoria

    ev_id, _ = _evaluacion_lista(cliente, db, fondo, cabeceras_admin)
    ana_u = crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    cliente.post(f"/api/evaluacion/{ev_id}/participantes", headers=cabeceras_admin,
                 json=EXPERTA | {"usuario_id": str(ana_u.id)})
    acciones = set(db.scalars(select(RegistroAuditoria.accion).where(RegistroAuditoria.entidad_id == ev_id)).all())
    assert "participante_registrada" in acciones
    assert db.get(Usuario, ana_u.id) is not None
