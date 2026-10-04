"""
Cierre de brechas, lote 2 · Recuperación ante desastres (NFR-04, NFR-07,
RF-OPS-001): el paquete de recuperación lleva la base, los archivos del
almacén y su manifiesto; se restaura entero en una base y una carpeta nuevas,
se verifica todo y se mide el tiempo. Usan pg_dump y pg_restore reales.

Los datos de estas pruebas se confirman de verdad (pg_dump solo ve lo
confirmado) y se retiran al terminar.
"""

import hashlib
import io
import json
import tarfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.instanciacion import Instanciacion
from app.models.preservacion import PaqueteRecuperacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import recuperacion
from tests.conftest import crear_usuario, ingresar


@pytest.fixture(autouse=True)
def destino(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "directorio_respaldo", tmp_path / "respaldo")
    return tmp_path / "respaldo"


@pytest.fixture()
def documento_confirmado():
    """Un fondo con un archivo real en el almacén, confirmado en la base."""
    contenido = b"%PDF-1.4\nOficio 114 de 1948 - prueba de recuperacion\n%%EOF\n"
    fondo_id, inst_id = uuid.uuid4(), uuid.uuid4()
    ruta_rel = f"{fondo_id}/{inst_id}/oficio.pdf"
    ruta = Path(settings.directorio_almacenamiento) / ruta_rel
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    with SessionLocal() as s:
        s.add(RecursoDocumental(id=fondo_id, nivel="fondo", titulo="Fondo de recuperación", fondo_id=fondo_id))
        s.flush()
        s.add(Instanciacion(id=inst_id, fondo_id=fondo_id, nombre_original="oficio.pdf", ruta=ruta_rel,
                            tamano_bytes=len(contenido), estado="listo_para_descripcion", paso="terminado",
                            progreso=100, huella=hashlib.sha256(contenido).hexdigest()))
        s.commit()
    yield {"ruta": ruta_rel, "contenido": contenido}
    with SessionLocal() as s:
        s.execute(text("DELETE FROM instanciaciones WHERE id = :i"), {"i": inst_id})
        s.execute(text("DELETE FROM recursos_documentales WHERE id = :i"), {"i": fondo_id})
        s.commit()
    ruta.unlink(missing_ok=True)


@pytest.fixture()
def base_vacia():
    url = make_url(settings.database_url)
    nombre = f"ricora_prueba_restaurar_{uuid.uuid4().hex[:8]}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as con:
        con.execute(text(f'CREATE DATABASE "{nombre}"'))
    yield url.set(database=nombre).render_as_string(hide_password=False)
    with admin.connect() as con:
        con.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
    admin.dispose()


def test_paquete_completo_se_restaura_entero_y_mide_el_tiempo(db, documento_confirmado):
    p = recuperacion.generar_y_probar(db, "manual")
    assert p.estado == "correcto", p.error
    assert p.simulacro_estado == "correcto", p.simulacro_detalle
    d = p.simulacro_detalle
    assert d["archivos"] >= 1 and d["archivos_verificados"] == d["archivos"] and d["problemas"] == []
    assert set(d["pasos_segundos"]) == {"abrir_paquete", "restaurar_base", "copiar_archivos", "verificar"}
    assert p.simulacro_segundos is not None
    with tarfile.open(p.archivo) as tar:
        nombres = set(tar.getnames())
        manifiesto = json.loads(tar.extractfile("manifiesto.json").read())
        crudo = b"".join(tar.extractfile(m).read() for m in tar.getmembers() if m.isfile())
    assert {"base/ricora.dump", "base/ricora.dump.sha256", "manifiesto.json", "LEEME.txt",
            f"archivos/{documento_confirmado['ruta']}"} <= nombres
    assert any(a["ruta"] == documento_confirmado["ruta"] for a in manifiesto["archivos"])
    assert manifiesto["auditoria"]["huella"] and manifiesto["migracion"]
    # Ninguna clave va en el paquete.
    assert settings.secret_key.encode() not in crudo
    assert "RICORA_SECRET_KEY" in manifiesto["variables_requeridas"]


def test_un_archivo_alterado_en_el_paquete_hace_fallar_la_restauracion(db, documento_confirmado, base_vacia, tmp_path):
    p = recuperacion.generar(db, "manual")
    alterado = tmp_path / "alterado.tar"
    with tarfile.open(p.archivo) as origen, tarfile.open(alterado, "w") as salida:
        for m in origen.getmembers():
            datos = origen.extractfile(m).read()
            if m.name == f"archivos/{documento_confirmado['ruta']}":
                datos = datos.replace(b"1948", b"1949")
            m.size = len(datos)
            salida.addfile(m, io.BytesIO(datos))
    with pytest.raises(recuperacion.ErrorRecuperacion, match="huella"):
        recuperacion.restaurar(alterado, base_vacia, tmp_path / "almacen")


def test_no_restaura_sobre_una_base_con_datos_ni_rutas_fuera_de_la_carpeta(db, base_vacia, tmp_path):
    p = recuperacion.generar(db, "manual")
    with pytest.raises(recuperacion.ErrorRecuperacion, match="no está vacía"):
        recuperacion.restaurar(Path(p.archivo), settings.database_url, tmp_path / "almacen1")
    malicioso = tmp_path / "malicioso.tar"
    with tarfile.open(malicioso, "w") as tar:
        info = tarfile.TarInfo("../fuera.txt")
        info.size = 3
        tar.addfile(info, io.BytesIO(b"mal"))
    with pytest.raises(recuperacion.ErrorRecuperacion, match="ruta no permitida"):
        recuperacion.restaurar(malicioso, base_vacia, tmp_path / "almacen2")
    assert not (tmp_path / "fuera.txt").exists()


def test_rpo_y_rto_por_escenario_frente_a_lo_medido(db, admin):
    e = recuperacion.estado(db)
    assert {f["clave"] for f in e["escenarios"]} == {"archivo_danado", "error_humano", "base_corrupta",
                                                     "perdida_servidor", "secuestro"}
    perdida = next(f for f in e["escenarios"] if f["clave"] == "perdida_servidor")
    assert perdida["cumple"] is False  # sin paquete descargado no hay copia fuera del servidor
    p = recuperacion.generar_y_probar(db, "manual")
    recuperacion.registrar_descarga(db, p, admin.id)
    db.flush()
    perdida = next(f for f in recuperacion.estado(db)["escenarios"] if f["clave"] == "perdida_servidor")
    assert perdida["rpo_actual_horas"] is not None and perdida["rpo_actual_horas"] < 1
    assert perdida["rto_medido_horas"] is not None and perdida["cumple"] is True


def test_recuperacion_por_la_api_solo_administrador(cliente, db, cabeceras_admin):
    crear_usuario(db, "arch@ricora.prueba", "archivista")
    archivista = ingresar(cliente, "arch@ricora.prueba")
    assert cliente.post("/api/preservacion/recuperacion", headers=archivista).status_code == 403
    r = cliente.post("/api/preservacion/recuperacion", headers=cabeceras_admin)
    assert r.status_code == 200 and r.json()["simulacro_estado"] == "correcto", r.text
    bajada = cliente.get(f"/api/preservacion/recuperacion/{r.json()['id']}/descargar", headers=cabeceras_admin)
    assert bajada.status_code == 200 and bajada.headers["x-huella-sha256"] == r.json()["huella"]
    assert hashlib.sha256(bajada.content).hexdigest() == r.json()["huella"]
    estado = cliente.get("/api/preservacion/recuperacion", headers=cabeceras_admin).json()
    assert estado["ultimo_paquete"]["descargado_en"] is not None
    malo = cliente.put("/api/preservacion/recuperacion/objetivos", headers=cabeceras_admin,
                       json={"rpo_horas": 0, "rto_horas": 8, "frecuencia_dias": 7})
    assert malo.status_code == 422
    bien = cliente.put("/api/preservacion/recuperacion/objetivos", headers=cabeceras_admin,
                       json={"rpo_horas": 72, "rto_horas": 6, "frecuencia_dias": 3})
    assert bien.status_code == 200 and bien.json()["objetivos"]["rpo_horas"] == 72


def test_solo_se_conservan_dos_paquetes_en_el_servidor(db):
    paquetes = [recuperacion.generar(db, "manual") for _ in range(3)]
    assert recuperacion.depurar(db) == 1
    assert paquetes[0].depurado_en is not None and not Path(paquetes[0].archivo).exists()
    assert all(Path(p.archivo).exists() for p in paquetes[1:])
    assert db.get(PaqueteRecuperacion, paquetes[0].id) is not None  # la fila queda


def test_orden_de_consola_para_un_servidor_nuevo(tmp_path):
    from app import cli

    assert cli.restaurar_paquete(str(tmp_path / "no-existe.tar")) == 1


def test_un_archivo_perdido_no_bloquea_el_paquete_pero_queda_registrado_y_alerta(db, documento_confirmado):
    from sqlalchemy import select

    from app.models.alerta import Alerta

    ruta = Path(settings.directorio_almacenamiento) / documento_confirmado["ruta"]
    ruta.unlink()
    p = recuperacion.generar_y_probar(db, "manual")
    assert p.estado == "correcto" and p.simulacro_estado == "correcto", (p.error, p.simulacro_detalle)
    assert [a["ruta"] for a in p.simulacro_detalle["ausentes"]] == [documento_confirmado["ruta"]]
    assert recuperacion.out(p)["ausentes"] == ["oficio.pdf"]
    alerta = db.scalar(select(Alerta).where(Alerta.tipo == "recuperacion_fallida", Alerta.atendida_en.is_(None)))
    assert alerta is not None and "segunda copia" in alerta.mensaje
