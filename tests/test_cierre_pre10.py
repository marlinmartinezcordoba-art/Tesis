"""
Cierre del hallazgo PRE-10 de la auditoría RiC: la base de datos se
respalda y el respaldo se prueba restaurándolo de verdad en una base
efímera. Las pruebas usan pg_dump y pg_restore reales.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.base import ahora
from app.models.alerta import Alerta
from app.models.preservacion import RespaldoBaseDatos
from app.servicios import respaldo
from tests.conftest import crear_usuario, ingresar
from tests.test_ingesta import fondo  # noqa: F401


@pytest.fixture(autouse=True)
def destino(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "directorio_respaldo", tmp_path / "respaldo")
    return tmp_path / "respaldo"


def _bases_efimeras():
    url = make_url(settings.database_url)
    motor = create_engine(url.set(database="postgres"))
    with motor.connect() as con:
        n = con.execute(text("SELECT count(*) FROM pg_database WHERE datname LIKE 'ricora_simulacro_%'")).scalar()
    motor.dispose()
    return n


def test_respaldo_con_simulacro_correcto_y_huella(db, destino):
    r = respaldo.respaldar_y_probar(db, "manual")
    assert r.estado == "correcto" and r.simulacro_estado == "correcto", (r.error, r.simulacro_detalle)
    volcado = Path(r.archivo)
    assert volcado.parent == destino and volcado.stat().st_size == r.tamano_bytes
    assert Path(f"{volcado}.sha256").read_text().split()[0] == r.huella == respaldo._sha256(volcado)
    # Lo restaurado reproduce cada tabla clave y la huella de las huellas de fijeza.
    assert r.simulacro_detalle["diferencias"] == {}
    assert set(r.simulacro_detalle["tablas"]) == set(respaldo.TABLAS_CLAVE)
    assert r.conteos["tablas"]["hallazgos_conformidad"] >= 14
    assert _bases_efimeras() == 0  # la base efímera se elimina al terminar


def test_un_volcado_alterado_hace_fallar_el_simulacro_con_alerta(db):
    r = respaldo.respaldar(db, "manual")
    assert r.estado == "correcto"
    with open(r.archivo, "r+b") as f:
        f.seek(200)
        f.write(b"\x00\xff\x00\xff")
    respaldo.simulacro(db, r)
    assert r.simulacro_estado == "fallido" and "SHA-256" in r.simulacro_detalle["error"]
    alerta = db.scalar(select(Alerta).where(Alerta.tipo == "respaldo_fallido", Alerta.atendida_en.is_(None)))
    assert alerta is not None and alerta.severidad == "alta"
    assert _bases_efimeras() == 0


def test_pg_dump_ausente_deja_respaldo_fallido_y_alerta(db, monkeypatch):
    monkeypatch.setattr(settings, "pg_dump", "/no/existe/pg_dump")
    r = respaldo.respaldar_y_probar(db)
    assert r.estado == "fallido" and r.simulacro_estado is None and r.error
    assert db.scalar(select(Alerta).where(Alerta.tipo == "respaldo_fallido", Alerta.atendida_en.is_(None)))


def test_el_periodico_respeta_la_frecuencia_y_avisa_el_atraso(db):
    primero = respaldo.periodico(db)
    assert primero is not None and primero.simulacro_estado == "correcto"
    assert respaldo.periodico(db) is None  # dentro de la frecuencia no repite
    primero.iniciado_en = ahora() - timedelta(hours=60)
    db.flush()
    respaldo.revisar_atrasos(db)
    assert db.scalar(select(Alerta).where(Alerta.tipo == "respaldo_atrasado", Alerta.atendida_en.is_(None)))
    segundo = respaldo.periodico(db)
    assert segundo is not None and segundo.simulacro_estado == "correcto"
    # Un respaldo probado nuevo resuelve solo la alerta de atraso.
    assert not db.scalar(select(Alerta).where(Alerta.tipo == "respaldo_atrasado", Alerta.atendida_en.is_(None)))


def test_descarga_fuera_del_servidor_solo_administrador_y_queda_registrada(cliente, db, admin):
    r = respaldo.respaldar_y_probar(db, "manual")
    r.iniciado_en = ahora() - timedelta(days=10)
    db.commit()
    respaldo.revisar_atrasos(db)
    assert db.scalar(select(Alerta).where(Alerta.tipo == "respaldo_sin_copia_externa", Alerta.atendida_en.is_(None)))
    db.commit()
    crear_usuario(db, "arch-pre10@correo.com", "archivista")
    archivista = ingresar(cliente, "arch-pre10@correo.com")
    assert cliente.get(f"/api/preservacion/respaldos/{r.id}/descargar", headers=archivista).status_code == 403
    jefe = ingresar(cliente, admin.correo)
    d = cliente.get(f"/api/preservacion/respaldos/{r.id}/descargar", headers=jefe)
    assert d.status_code == 200 and d.headers["x-huella-sha256"] == r.huella
    assert len(d.content) == r.tamano_bytes
    db.refresh(r)
    assert r.descargado_en is not None
    assert not db.scalar(select(Alerta).where(Alerta.tipo == "respaldo_sin_copia_externa", Alerta.atendida_en.is_(None)))


def test_la_linea_de_tiempo_muestra_el_ultimo_simulacro(cliente, db, admin, fondo):
    respaldo.respaldar_y_probar(db, "manual")
    db.commit()
    jefe = ingresar(cliente, admin.correo)
    e = cliente.get("/api/preservacion/eventos-recientes", headers=jefe, params={"fondo_id": str(fondo.id)}).json()
    assert e["simulacro_base_de_datos"]["estado"] == "correcto"


def test_la_retencion_retira_archivos_viejos_pero_conserva_el_registro(db, admin):
    from app.servicios import parametros

    parametros.cambiar(db, "respaldo_retencion", 3, admin.id, "preservacion")
    hechos = [respaldo.respaldar(db, "manual") for _ in range(4)]
    for i, r in enumerate(hechos):
        r.iniciado_en = ahora() - timedelta(minutes=10 - i)
    db.flush()
    assert respaldo.depurar(db) == 1
    viejo = hechos[0]
    assert viejo.depurado_en is not None and not Path(viejo.archivo).exists()
    assert db.get(RespaldoBaseDatos, viejo.id) is not None
