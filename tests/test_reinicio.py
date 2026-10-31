"""
Puesta en marcha: dejar RICORA en blanco (app/servicios/reinicio.py).

Borra todo lo cargado y descrito; conserva usuarios, roles, parámetros,
respaldos y la auditoría. Exige contraseña, frase y un respaldo previo
correcto; sin respaldo no borra nada. Los archivos se apartan, no se eliminan.
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from app.core.config import settings
from app.models.auditoria import RegistroAuditoria
from app.models.parametro import Parametro
from app.models.recurso_documental import RecursoDocumental
from app.models.usuario import Usuario
from app.servicios import mecanismos, parametros, reinicio
from tests.conftest import CONTRASENA, crear_usuario, ingresar
from tests.test_especializacion_ric import agente, documento, relacion
from tests.test_preservacion import fondo  # noqa: F401  (fixture)


def test_toda_tabla_esta_clasificada(db):
    """Una tabla nueva debe declararse en BORRAR, CONSERVAR o TESAUROS: nunca se borra por omisión."""
    assert reinicio.sin_clasificar(db) == set()
    assert not set(reinicio.BORRAR) & set(reinicio.CONSERVAR)
    assert "registro_auditoria" in reinicio.CONSERVAR and "usuarios" in reinicio.CONSERVAR


@pytest.fixture()
def respaldo_falso(monkeypatch):
    estado = {"estado": "correcto", "llamadas": 0}

    def respaldar(db, origen, usuario_id=None):
        estado["llamadas"] += 1
        return SimpleNamespace(id=uuid.uuid4(), estado=estado["estado"], archivo="/data/respaldo/ricora-prueba.dump",
                               huella="abc123", error=None if estado["estado"] == "correcto" else "disco lleno")

    from app.servicios import respaldo

    monkeypatch.setattr(respaldo, "respaldar", respaldar)
    return estado


@pytest.fixture()
def almacen_propio(monkeypatch, tmp_path):
    raiz = tmp_path / "almacen"
    (raiz / "fondo-x").mkdir(parents=True)
    (raiz / "fondo-x" / "oficio.pdf").write_bytes(b"%PDF-1.4 prueba")
    monkeypatch.setattr(settings, "directorio_almacenamiento", raiz)
    monkeypatch.setattr(settings, "directorio_respaldo", tmp_path / "respaldo")
    return raiz


def _contenido(db, fondo, admin):  # noqa: F811
    doc = documento(db, fondo, "Oficio 301 de 1949")
    motor = mecanismos.del_motor(db, fondo.id, "motor-de-prueba-2.0")
    relacion(db, doc, agente(db, fondo, "Alcaldía de Tunja", "entidad_corporativa"), "has_creator", origen="motor",
             confianza=0.9, motor="motor-de-prueba-2.0", motor_id=motor.id, confirmada_por_id=admin.id)
    parametros.cambiar(db, "rdf_uris_publicas", True, admin.id, "instrumentos")
    db.commit()


def _cuenta(db, tabla):
    return db.scalar(text(f'SELECT count(*) FROM "{tabla}"'))


def test_deja_el_sistema_en_blanco_y_conserva_lo_que_lo_hace_funcionar(cliente, db, fondo, admin, cabeceras_admin,
                                                                       respaldo_falso, almacen_propio):
    _contenido(db, fondo, admin)
    eventos_antes = db.scalar(select(func.count()).select_from(RegistroAuditoria))
    inv = cliente.get("/api/sistema/reinicio", headers=cabeceras_admin).json()
    cantidades = {x["que"]: x["cantidad"] for x in inv["se_borra"]}
    assert cantidades["Fondos y unidades de descripción"] == 2 and cantidades["Relaciones"] == 1
    assert inv["frase"] == reinicio.FRASE and inv["sin_clasificar"] == []

    # Contraseña equivocada, frase equivocada: no se borra nada.
    r = cliente.post("/api/sistema/reinicio", headers=cabeceras_admin, json={"contrasena": "otra", "frase": reinicio.FRASE})
    assert r.status_code == 403
    r = cliente.post("/api/sistema/reinicio", headers=cabeceras_admin, json={"contrasena": CONTRASENA, "frase": "borrar"})
    assert r.status_code == 422 and reinicio.FRASE in r.json()["detail"]
    # Si el respaldo previo falla, tampoco.
    respaldo_falso["estado"] = "fallido"
    r = cliente.post("/api/sistema/reinicio", headers=cabeceras_admin, json={"contrasena": CONTRASENA, "frase": reinicio.FRASE})
    assert r.status_code == 500 and "No se borró nada" in r.json()["detail"]
    assert _cuenta(db, "recursos_documentales") == 2 and (almacen_propio / "fondo-x" / "oficio.pdf").exists()

    respaldo_falso["estado"] = "correcto"
    r = cliente.post("/api/sistema/reinicio", headers=cabeceras_admin,
                     json={"contrasena": CONTRASENA, "frase": "  borrar todo el contenido "})
    assert r.status_code == 200, r.text
    hecho = r.json()
    assert hecho["respaldo"]["archivo"] == "ricora-prueba.dump" and respaldo_falso["llamadas"] == 2

    # En blanco.
    for tabla in ("recursos_documentales", "entidades_vocabulario", "relaciones", "instanciaciones", "grafos_rdf",
                  "propuestas_ia", "evaluaciones", "trd_versiones"):
        assert _cuenta(db, tabla) == 0, tabla
    assert db.get(Parametro, "mecanismos_motor") is None  # apuntaba a contenido borrado
    # Se conserva: usuarios, parámetros de configuración y toda la auditoría, con el evento del reinicio.
    assert db.get(Usuario, admin.id) is not None and parametros.leer(db, "rdf_uris_publicas") is True
    assert db.scalar(select(func.count()).select_from(RegistroAuditoria)) > eventos_antes
    evento = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "sistema_reiniciado"))
    assert evento.usuario_id == admin.id and evento.valor_nuevo["respaldo_archivo"] == "ricora-prueba.dump"
    assert {"que": "Relaciones", "cantidad": 1} in evento.valor_nuevo["borrado"]
    # Los archivos no se eliminan: quedan apartados.
    assert not (almacen_propio / "fondo-x").exists()
    apartados = list((almacen_propio / "_retirado").glob("*/fondo-x/oficio.pdf"))
    assert len(apartados) == 1 and hecho["archivos_apartados"]["movidos"] == 1
    # La administradora sigue entrando, y el sistema funciona vacío.
    assert ingresar(cliente, admin.correo)
    assert cliente.get("/api/sistema/reinicio", headers=cabeceras_admin).json()["se_borra"][0]["cantidad"] == 0


def test_solo_la_administracion_y_los_tesauros_se_conservan_si_no_se_piden(cliente, db, fondo, admin, cabeceras_admin,
                                                                          respaldo_falso, almacen_propio):
    crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    ana = ingresar(cliente, "ana@correo.com")
    assert cliente.get("/api/sistema/reinicio", headers=ana).status_code == 403
    assert cliente.post("/api/sistema/reinicio", headers=ana,
                        json={"contrasena": CONTRASENA, "frase": reinicio.FRASE}).status_code == 403
    from app.models.tesauro import Tesauro

    db.add(Tesauro(nombre="Tesauro de prueba", formato="skos", importado_por_id=admin.id))
    db.commit()
    cliente.post("/api/sistema/reinicio", headers=cabeceras_admin, json={"contrasena": CONTRASENA, "frase": reinicio.FRASE})
    assert _cuenta(db, "tesauros") == 1 and db.scalar(select(func.count()).select_from(RecursoDocumental)) == 0
    r = cliente.post("/api/sistema/reinicio", headers=cabeceras_admin,
                     json={"contrasena": CONTRASENA, "frase": reinicio.FRASE, "incluir_tesauros": True})
    assert r.status_code == 200 and r.json()["tesauros_borrados"] and _cuenta(db, "tesauros") == 0
