"""
Asistente RICORA con los documentos de la entidad (RAG).

- La administración carga una ley o un manual a la biblioteca; el trabajador le extrae el texto.
- El asistente recupera los pasajes que tratan la pregunta (biblioteca, documentos del fondo,
  descripciones publicadas) y el motor responde solo con ellos, citándolos; sin Google.
- Si no hay pasajes, no se consulta al motor: se dice que no está en los documentos.
- Un documento reservado (Ley 1712) nunca se recupera; los datos personales salen anonimizados.
- Nada se borra: un documento de la biblioteca se anula y deja de consultarse.
"""

import io
import uuid

import pytest

from app.models.instanciacion import Instanciacion
from app.servicios import biblioteca, derechos, motor, rag
from tests.conftest import crear_usuario, ingresar
from tests.test_ingesta import archivista, cargar, fondo, herramientas  # noqa: F401
from app.servicios import procesamiento

LEY = """LEY 594 DE 2000. Por medio de la cual se dicta la Ley General de Archivos.
ARTÍCULO 24. Obligatoriedad de las tablas de retención. Será obligatorio para las entidades del Estado
elaborar y adoptar las respectivas tablas de retención documental.
ARTÍCULO 26. Inventario documental. Es obligación de las entidades de la Administración Pública elaborar
inventarios de los documentos que produzcan en ejercicio de sus funciones."""


class MotorFalso:
    modelo = "gemini-de-prueba"

    def __init__(self):
        self.recibido = None

    def conversar(self, instruccion, contenido, buscar=False):
        self.recibido = (instruccion, contenido, buscar)
        return "Las entidades del Estado deben elaborar y adoptar sus tablas de retención documental [1]."


@pytest.fixture()
def falso(monkeypatch):
    m = MotorFalso()
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    return m


def _cargar_ley(cliente, cabeceras, db, contenido=LEY, nombre="ley_594_2000.txt", titulo="Ley 594 de 2000"):
    r = cliente.post("/api/asistente/biblioteca", headers=cabeceras,
                     files={"archivo": (nombre, io.BytesIO(contenido.encode("utf-8")), "text/plain")},
                     data={"titulo": titulo, "clase": "ley"})
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "procesando"
    assert biblioteca.una_pendiente(db)  # lo que hace el trabajador
    return r.json()["id"]


def test_la_ley_cargada_responde_la_pregunta_citando_el_pasaje(cliente, db, cabeceras_admin, falso):
    doc_id = _cargar_ley(cliente, cabeceras_admin, db)
    lista = cliente.get("/api/asistente/biblioteca", headers=cabeceras_admin).json()
    assert lista[0]["id"] == doc_id and lista[0]["estado"] == "listo" and lista[0]["clase_nombre"] == "Ley"
    r = cliente.post("/api/asistente/preguntar", headers=cabeceras_admin, json={"fuentes": "documentos",
        "mensajes": [{"rol": "persona", "texto": "¿Es obligatorio adoptar las tablas de retención?"}]})
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["modo"] == "documentos" and "[1]" in datos["respuesta"]
    [p] = datos["pasajes"]
    assert p["titulo"] == "Ley 594 de 2000" and p["tipo"] == "norma" and p["citado"] is True
    instruccion, contenido, buscar = falso.recibido
    assert buscar is False  # sin Google: solo los documentos de la entidad
    assert "Responde SOLO con los PASAJES" in instruccion
    assert "ARTÍCULO 24" in contenido[-1]["parts"][0]["text"] and "[1] Ley 594 de 2000" in contenido[-1]["parts"][0]["text"]


def test_automatico_primero_los_documentos_y_si_no_alcanzan_internet(cliente, db, cabeceras_admin, falso):
    """Sin elegir nada: con pasajes, el motor los usa (citados) y puede completar con Google; sin pasajes,
    responde con internet como antes. La persona solo ve la respuesta."""
    _cargar_ley(cliente, cabeceras_admin, db)
    r = cliente.post("/api/asistente/preguntar", headers=cabeceras_admin, json={
        "mensajes": [{"rol": "persona", "texto": "¿Es obligatorio adoptar las tablas de retención?"}]})
    assert r.json()["modo"] == "auto" and r.json()["pasajes"][0]["titulo"] == "Ley 594 de 2000"
    instruccion, contenido, buscar = falso.recibido
    assert buscar is True and "Úsalos primero" in instruccion and "ARTÍCULO 24" in contenido[-1]["parts"][0]["text"]
    falso.recibido = None
    r = cliente.post("/api/asistente/preguntar", headers=cabeceras_admin, json={
        "mensajes": [{"rol": "persona", "texto": "¿Cuál es la capital de Mongolia?"}]})
    assert r.json()["modo"] == "internet" and r.json()["pasajes"] == []
    assert falso.recibido[2] is True and "PASAJES" not in falso.recibido[1][-1]["parts"][0]["text"]


def test_solo_documentos_sin_pasajes_no_se_consulta_al_motor_ni_se_inventa(cliente, db, cabeceras_admin, falso):
    _cargar_ley(cliente, cabeceras_admin, db)
    r = cliente.post("/api/asistente/preguntar", headers=cabeceras_admin, json={"fuentes": "documentos",
        "mensajes": [{"rol": "persona", "texto": "¿Cuál es la capital de Mongolia?"}]})
    assert r.status_code == 200
    assert r.json()["pasajes"] == [] and "No encontré" in r.json()["respuesta"]
    assert falso.recibido is None


def test_con_internet_responde_como_antes_con_google(cliente, db, cabeceras_admin, falso):
    r = cliente.post("/api/asistente/preguntar", headers=cabeceras_admin, json={
        "fuentes": "internet", "mensajes": [{"rol": "persona", "texto": "¿Qué es el FUID?"}]})
    assert r.status_code == 200 and r.json()["modo"] == "internet"
    assert falso.recibido[2] is True


def test_el_texto_de_los_documentos_del_fondo_se_recupera_y_lo_reservado_no(cliente, db, fondo, archivista,
                                                                             cabeceras_admin, admin):  # noqa: F811
    [publico, reservado] = cargar(cliente, archivista, fondo,
                                  ("oficio_publico.txt", "Oficio sobre la sustracción de la reserva forestal del Pacífico."
                                   .encode("utf-8")),
                                  ("acta_reservada.txt", "Acta reservada sobre la sustracción de la reserva forestal."
                                   .encode("utf-8")))
    procesamiento.procesar_pendientes(db)
    derechos.declarar(db, entidad_tipo="instanciacion", entidad_id=uuid.UUID(reservado["id"]), base="estatuto",
                      acceso="reservado", reproduccion="no_permitida", fundamento="Ley 1712 de 2014, art. 19",
                      nota=None, vigente_hasta=None, usuario_id=admin.id)
    db.commit()
    pasajes = rag.recuperar(db, "sustracción de la reserva forestal", fondo.id)
    titulos = [p.titulo for p in pasajes]
    assert "oficio_publico.txt" in titulos
    assert "acta_reservada.txt" not in titulos  # su texto nunca sale hacia el motor
    assert db.get(Instanciacion, uuid.UUID(reservado["id"])).texto_extraido  # el documento sigue intacto


def test_los_datos_personales_del_pasaje_salen_anonimizados(cliente, db, cabeceras_admin, falso):
    _cargar_ley(cliente, cabeceras_admin, db, contenido="Manual de archivo. Las tablas de retención las firma "
                "la persona con cédula 1.023.456.789 y se publican en la sede electrónica.", nombre="manual.txt",
                titulo="Manual de gestión documental")
    cliente.post("/api/asistente/preguntar", headers=cabeceras_admin, json={
        "mensajes": [{"rol": "persona", "texto": "¿Quién firma las tablas de retención?"}]})
    enviado = falso.recibido[1][-1]["parts"][0]["text"]
    assert "1.023.456.789" not in enviado and "Manual de gestión documental" in enviado


def test_solo_la_administracion_carga_y_anula_y_nada_se_borra(cliente, db, cabeceras_admin, falso):
    crear_usuario(db, "ana@correo.com", "archivista", nombre="Ana Ruiz")
    ana = ingresar(cliente, "ana@correo.com")
    r = cliente.post("/api/asistente/biblioteca", headers=ana,
                     files={"archivo": ("x.txt", io.BytesIO(b"texto"), "text/plain")}, data={"clase": "ley"})
    assert r.status_code == 403
    doc_id = _cargar_ley(cliente, cabeceras_admin, db)
    # El mismo archivo dos veces: se avisa, no se duplica.
    r = cliente.post("/api/asistente/biblioteca", headers=cabeceras_admin,
                     files={"archivo": ("otra.txt", io.BytesIO(LEY.encode("utf-8")), "text/plain")}, data={"clase": "ley"})
    assert r.status_code == 409
    assert cliente.post(f"/api/asistente/biblioteca/{doc_id}/anular", headers=ana, json={}).status_code == 403
    r = cliente.post(f"/api/asistente/biblioteca/{doc_id}/anular", headers=cabeceras_admin,
                     json={"motivo": "Derogada"})
    assert r.status_code == 200 and r.json()["estado"] == "anulado"
    assert cliente.get("/api/asistente/biblioteca", headers=cabeceras_admin).json() == []
    assert rag.recuperar(db, "tablas de retención obligatorio", None) == []
    from app.models.referencia import DocumentoReferencia

    assert db.get(DocumentoReferencia, uuid.UUID(doc_id)).texto  # anulado, no borrado


def test_la_consulta_es_de_palabras_sueltas():
    assert rag.consulta("¿Cómo se elabora el FUID?") == "cómo or elabora or fuid"
    assert rag.consulta("¿?") is None
