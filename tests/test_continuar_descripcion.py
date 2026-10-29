"""
Continuar una descripción que se dejó a medias.

- La cola le dice a quien tiene el documento abierto cuál es su trabajo, para
  volver a él; a los demás solo quién lo tiene (y a la administración, el
  trabajo para poder liberarlo).
- El avance del formulario se guarda mientras se trabaja y vuelve al reabrir.
- Una descripción empezada no se pierde: si la marca venció, la persona salió
  sin publicar o la administración la liberó, al abrir otra vez los mismos
  documentos se continúa donde iba, la misma persona u otra del equipo:
  recupera la propuesta (sin consultar de nuevo el motor) y el avance.
- La administración libera la marca de otra persona con motivo; el avance se
  conserva y queda constancia.
"""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient

from app.db.base import ahora
from app.models.descripcion import TrabajoDescripcion
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import (OFICIO_114, aceptar_todo, archivista, documento, eventos, fondo,  # noqa: F401
                                    iniciar, motor_prueba)

AVANCE = {"titulo": "Oficio 114 sobre el acueducto", "alcance": "Revisado a mano hasta la mitad.",
          "decisiones": {"agente-1": "aceptada"}}


def _cola(cliente, cab, fondo):  # noqa: F811
    return {x["id"]: x for x in cliente.get("/api/descripcion/cola", headers=cab,
                                             params={"fondo_id": str(fondo.id)}).json()}


def test_continuar_el_trabajo_propio_con_su_avance(cliente, db, fondo, archivista, motor_prueba):  # noqa: F811
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    r = cliente.put(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/borrador", headers=archivista,
                    json={"borrador": AVANCE})
    assert r.status_code == 204, r.text
    # La cola le ofrece continuar a quien lo tiene abierto.
    fila = _cola(cliente, archivista, fondo)[str(d.id)]
    assert fila["en_edicion_por"] == "Catalina Torres" and fila["trabajo_propio_id"] == espacio["trabajo_id"]
    # Al reabrir la pantalla vuelve el avance.
    reabierto = cliente.get(f"/api/descripcion/trabajos/{espacio['trabajo_id']}", headers=archivista).json()
    assert reabierto["borrador"] == AVANCE and reabierto["borrador_guardado_en"]
    assert reabierto["recuperado"] is False


def test_si_la_marca_vencio_se_continua_donde_iba_sin_volver_al_motor(cliente, db, fondo, archivista,  # noqa: F811
                                                                     motor_prueba):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    cliente.put(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/borrador", headers=archivista,
                json={"borrador": AVANCE})
    trabajo = db.get(TrabajoDescripcion, uuid.UUID(espacio["trabajo_id"]))
    trabajo.ultima_actividad = ahora() - timedelta(minutes=31)
    db.commit()
    consultas = motor_prueba.llamadas if hasattr(motor_prueba, "llamadas") else None
    # Se fue: la marca venció. Al abrir otra vez el mismo documento continúa.
    nuevo = iniciar(cliente, archivista, [d.id])
    db.refresh(trabajo)
    assert trabajo.estado == "expirado" and nuevo["trabajo_id"] != espacio["trabajo_id"]
    assert nuevo["recuperado"] is True and nuevo["borrador"] == AVANCE
    assert nuevo["propuesta"]["propuesta_id"] == espacio["propuesta"]["propuesta_id"]
    if consultas is not None:
        assert motor_prueba.llamadas == consultas  # no se volvió a consultar el motor
    assert len(eventos(db, "descripcion_recuperada")) == 1
    # Y se publica normalmente desde el trabajo recuperado.
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(nuevo)).status_code == 201


def test_otra_persona_continua_la_descripcion_que_quedo_a_medias(cliente, db, fondo, archivista,  # noqa: F811
                                                                 motor_prueba):
    from app.main import app

    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    cliente.put(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/borrador", headers=archivista,
                json={"borrador": AVANCE})
    crear_usuario(db, "julian@correo.com", "archivista", nombre="Julián Rincón")
    with TestClient(app) as otro_cliente:
        otro = ingresar(otro_cliente, "julian@correo.com")
        # Mientras Catalina lo tiene abierto, Julián ve quién lo tiene, pero no su trabajo.
        fila = _cola(otro_cliente, otro, fondo)[str(d.id)]
        assert fila["en_edicion_por"] == "Catalina Torres" and fila["trabajo_propio_id"] is None
        assert fila["trabajo_id"] is None  # no es administración
        assert otro_cliente.put(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/borrador", headers=otro,
                                json={"borrador": {}}).status_code == 404
        # Catalina se va sin publicar: Julián lo abre y sigue desde donde ella iba.
        trabajo = db.get(TrabajoDescripcion, uuid.UUID(espacio["trabajo_id"]))
        trabajo.ultima_actividad = ahora() - timedelta(minutes=31)
        db.commit()
        suyo = iniciar(otro_cliente, otro, [d.id])
        assert suyo["recuperado"] is True and suyo["borrador"] == AVANCE
        assert suyo["empezada_por"] == "Catalina Torres"
        assert any("empezó Catalina Torres" in (e.detalle or "") for e in eventos(db, "descripcion_recuperada"))
        # Y la publica él: la descripción no se queda sin hacer.
        assert otro_cliente.post("/api/descripcion/publicar", headers=otro, json=aceptar_todo(suyo)).status_code == 201


def test_la_administracion_libera_con_motivo_y_el_avance_se_conserva(cliente, db, fondo, archivista,  # noqa: F811
                                                                    motor_prueba, cabeceras_admin):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    cliente.put(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/borrador", headers=archivista,
                json={"borrador": AVANCE})
    fila = _cola(cliente, cabeceras_admin, fondo)[str(d.id)]
    assert fila["trabajo_id"] == espacio["trabajo_id"]
    ruta = f"/api/descripcion/trabajos/{espacio['trabajo_id']}/liberar"
    assert cliente.post(ruta, headers=archivista, json={"motivo": "Quiero liberarlo yo misma"}).status_code == 403
    r = cliente.post(ruta, headers=cabeceras_admin, json={"motivo": "corto"})
    assert r.status_code == 422 and "por qué" in r.json()["detail"]
    assert cliente.post(ruta, headers=cabeceras_admin,
                        json={"motivo": "Catalina está de vacaciones dos semanas"}).status_code == 204
    assert _cola(cliente, archivista, fondo)[str(d.id)]["en_edicion_por"] is None
    assert any("vacaciones" in (e.detalle or "") for e in eventos(db, "edicion_liberada"))
    # Cuando vuelve, abre el documento y sigue donde iba.
    vuelve = iniciar(cliente, archivista, [d.id])
    assert vuelve["recuperado"] is True and vuelve["borrador"] == AVANCE
