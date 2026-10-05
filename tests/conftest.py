"""
Entorno de pruebas. Usa una base PostgreSQL propia (ricora_pruebas) con
las migraciones reales aplicadas, incluido el disparador que impide
modificar la auditoría. Cada prueba corre dentro de una transacción que
se revierte al final: así no hace falta borrar nada entre pruebas (y el
registro de auditoría, por diseño, no se puede vaciar).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://ricora:ricora@localhost:5432/ricora_pruebas")
os.environ["RICORA_SECRET_KEY"] = "clave-de-pruebas-de-ricora-con-mas-de-32-caracteres"
os.environ["RICORA_URL_PUBLICA"] = "http://ricora.prueba"
os.environ["RICORA_DIRECTORIO_INTERFAZ"] = "/ruta/que/no/existe"
import glob  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

os.environ["DIRECTORIO_ALMACENAMIENTO"] = tempfile.mkdtemp(prefix="ricora-almacen-")
# Dos lugares para la segunda copia: el primero es el de por defecto.
os.environ["RICORA_SEGUNDA_COPIA"] = os.pathsep.join(tempfile.mkdtemp(prefix=f"ricora-copia{n}-") for n in (1, 2))
# Siegfried: el del sistema, o el instalado con «go install»; su archivo de
# firmas PRONOM viene en el propio módulo de Go.
os.environ.setdefault("RICORA_SIEGFRIED", shutil.which("sf") or os.path.expanduser("~/go/bin/sf"))
if "RICORA_SIEGFRIED_HOME" not in os.environ:
    firmas = sorted(glob.glob(os.path.expanduser("~/go/pkg/mod/github.com/richardlehane/siegfried@*/cmd/roy/data/default.sig")))
    os.environ["RICORA_SIEGFRIED_HOME"] = os.path.dirname(firmas[-1]) if firmas else "/opt/siegfried"
for variable in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
    os.environ.pop(variable, None)

import uuid  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core import correo as modulo_correo  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.seguridad import cifrar_contrasena  # noqa: E402
from app.db.session import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402

CONTRASENA = "Archivo2026seguro"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def base_de_pruebas():
    """Crea la base de pruebas con las migraciones. Requiere PostgreSQL en
    marcha (``service postgresql start``). Solo la piden las pruebas que usan
    la base (a través de ``db``): las del mapeo RiC-O, EDTF y demás funciones
    puras corren sin PostgreSQL (hallazgo O-31)."""
    url = make_url(settings.database_url)
    administracion = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with administracion.connect() as con:
        con.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        con.execute(text(f'CREATE DATABASE "{url.database}"'))
    administracion.dispose()
    config = Config(os.path.join(RAIZ, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    command.upgrade(config, "head")
    yield


@pytest.fixture()
def db(base_de_pruebas):
    conexion = engine.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield sesion
    sesion.close()
    transaccion.rollback()
    conexion.close()


class ClienteConContrato(TestClient):
    """Cliente de pruebas que valida cada respuesta contra el esquema que su
    ruta declara en OpenAPI (prueba de contrato, RF-INT-003)."""

    def request(self, method, url, *args, **kwargs):
        from tests import contrato

        respuesta = super().request(method, url, *args, **kwargs)
        contrato.validar(self.app, method, url, respuesta)
        return respuesta


@pytest.fixture()
def cliente(db):
    app.dependency_overrides[get_db] = lambda: db
    with ClienteConContrato(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def buzon(monkeypatch):
    """Simula un servidor de correo configurado y guarda lo enviado."""
    enviados = []

    def _enviar(destinatario, asunto, texto, html=None):
        enviados.append({"para": destinatario, "asunto": asunto, "texto": texto})

    monkeypatch.setattr(settings, "correo_servidor", "smtp.prueba")
    monkeypatch.setattr(settings, "correo_usuario", "ricora@prueba")
    monkeypatch.setattr(settings, "correo_contrasena", "x")
    monkeypatch.setattr(modulo_correo, "enviar", _enviar)
    return enviados


def crear_usuario(db, correo, rol="archivista", contrasena=CONTRASENA, activo=True, nombre=None):
    usuario = Usuario(
        id=uuid.uuid4(),
        nombre=nombre or correo.split("@")[0].replace(".", " ").title(),
        correo=correo.lower(),
        rol=rol,
        activo=activo,
        contrasena_hash=cifrar_contrasena(contrasena) if contrasena else None,
    )
    db.add(usuario)
    db.commit()
    return usuario


def ingresar(cliente, correo, contrasena=CONTRASENA):
    r = cliente.post("/api/auth/login", json={"correo": correo, "contrasena": contrasena})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token_acceso']}"}


@pytest.fixture()
def admin(db):
    return crear_usuario(db, "admin@ricora.prueba", "administrador", nombre="Marlín Martínez")


@pytest.fixture()
def cabeceras_admin(cliente, admin):
    return ingresar(cliente, admin.correo)
