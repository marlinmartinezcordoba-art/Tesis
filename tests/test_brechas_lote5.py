"""
Cierre de brechas, lote 5 · Evidencia de la IA (RF-AI-002 y RF-OCR-001).

- RF-AI-002: iniciar una descripción deja una fila en propuestas_ia con la
  hora, el modelo, la versión de la instrucción, los parámetros, la huella
  del texto enviado y la respuesta tal como llegó. Cancelar el trabajo la
  conserva consultable. Su contenido no se puede cambiar ni borrar.
- RF-OCR-001: en un PDF escaneado de 3 páginas, la evidencia de una entidad
  de la página 2 devuelve página = 2 y la caja de su línea; queda fijada en
  la relación publicada. En un PDF con capa de texto, la zona se busca en el
  propio PDF.
"""

import hashlib
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models.descripcion import Relacion, TrabajoDescripcion
from app.models.evidencia_ia import PaginaTexto, PropuestaIA
from app.models.recurso_documental import RecursoDocumental
from app.servicios import evidencia, motor, procesamiento, propuestas_ia
from tests import archivos
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import MotorDePrueba, aceptar_todo, eventos, iniciar

ESCANEADO = [["ARCHIVO MUNICIPAL DE TUNJA", "ACTA DE ENTREGA"],
             ["EL INSPECTOR RAFAEL CUERVO", "RECIBIO LOS LEGAJOS"],
             ["FIRMA DEL GOBERNADOR"]]


@pytest.fixture()
def fondo(db, admin):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Correspondencia municipal", creado_por_id=admin.id)
    f.fondo_id = f.id
    db.add(f)
    db.commit()
    return f


@pytest.fixture()
def archivista(cliente, db):
    crear_usuario(db, "catalina@correo.com", "archivista", nombre="Catalina Torres")
    return ingresar(cliente, "catalina@correo.com")


def _cargar(cliente, db, cab, fondo, nombre, contenido):
    r = cliente.post("/api/ingesta/cargar", headers=cab, data={"fondo_id": str(fondo.id)},
                     files=[("archivos", (nombre, contenido, "application/pdf"))])
    assert r.status_code == 200, r.text
    procesamiento.procesar_pendientes(db)
    db.expire_all()
    from app.models.instanciacion import Instanciacion

    inst = db.get(Instanciacion, uuid.UUID(r.json()["resultados"][0]["id"]))
    assert inst.estado == "listo_para_descripcion", inst.mensaje_error
    return inst


def _respuesta(fragmento):
    return {"titulo": "Acta de entrega de los legajos del archivo", "alcance_contenido": "El inspector recibe los legajos.",
            "entidades": [{"tipo": "agente", "subtipo": "persona", "rol": "mencionado", "valor": "Rafael Cuervo",
                           "fragmento": fragmento, "documento": 1, "confianza": 0.9}]}


# --- RF-OCR-001 ----------------------------------------------------------------------------------


def test_pdf_escaneado_de_tres_paginas_ubica_la_entidad_en_la_pagina_2_con_su_caja(
        cliente, db, fondo, archivista, monkeypatch):
    inst = _cargar(cliente, db, archivista, fondo, "acta_escaneada.pdf", archivos.pdf_escaneado_paginas(ESCANEADO))
    paginas = db.scalars(select(PaginaTexto).where(PaginaTexto.instanciacion_id == inst.id)
                         .order_by(PaginaTexto.numero)).all()
    assert [p.numero for p in paginas] == [1, 2, 3] and all(p.origen == "ocr" and p.lineas for p in paginas)
    assert inst.texto_extraido[paginas[1].inicio:paginas[1].fin].startswith("EL INSPECTOR RAFAEL CUERVO")

    m = MotorDePrueba(_respuesta("EL INSPECTOR RAFAEL CUERVO"))
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    espacio = iniciar(cliente, archivista, [inst.id])
    [cuervo] = espacio["propuesta"]["entidades"]
    assert cuervo["pagina"] == 2
    zona = cuervo["zona"]
    assert zona["pagina"] == 2 and zona["origen"] == "ocr" and len(zona["cajas"]) == 1
    # La línea está arriba en la página (se dibujó a 300 px de 2200) y a la izquierda.
    assert 0.1 < zona["y"] < 0.2 and 0.05 < zona["x"] < 0.1 and 0 < zona["ancho"] < 1 and 0 < zona["alto"] < 0.05

    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert r.status_code == 201, r.text
    rel = db.scalar(select(Relacion).where(Relacion.origen_id == uuid.UUID(r.json()["id"]),
                                           Relacion.fragmento.is_not(None)))
    assert rel.fragmento_pagina == 2 and rel.fragmento_zona["cajas"] == zona["cajas"]
    detalle = cliente.get(f"/api/descripcion/registros/{r.json()['id']}", headers=archivista).json()
    [e] = [x for x in detalle["entidades"] if x["valor"] == "Rafael Cuervo"]
    assert e["pagina"] == 2 and e["zona"]["cajas"] == zona["cajas"]


def test_pdf_con_capa_de_texto_da_la_pagina_y_busca_la_zona_en_el_pdf(cliente, db, fondo, archivista):
    inst = _cargar(cliente, db, archivista, fondo, "oficio_digital.pdf", archivos.pdf_con_paginas(
        ["Primera hoja del expediente municipal de 1948", "Rafael Cuervo recibio los legajos del archivo"]))
    assert inst.origen_texto == "capa_de_texto"
    zona = evidencia.ubicar(db, inst.id, None, "recibio los legajos")
    assert zona["pagina"] == 2 and zona["origen"] == "capa_de_texto" and zona["cajas"]
    # La línea se escribió a 594 pt de 792 desde abajo: un 25 % desde arriba.
    assert 0.2 < zona["y"] < 0.26 and zona["x"] > 0.1


def test_si_el_texto_se_vuelve_a_extraer_la_evidencia_se_ubica_por_su_contenido(cliente, db, fondo, archivista):
    inst = _cargar(cliente, db, archivista, fondo, "acta_escaneada.pdf", archivos.pdf_escaneado_paginas(ESCANEADO))
    posicion = inst.texto_extraido.index("RECIBIO LOS LEGAJOS")
    assert evidencia.ubicar(db, inst.id, posicion, "RECIBIO LOS LEGAJOS")["pagina"] == 2
    # Una posición vieja (de otro texto) no engaña: se busca el fragmento.
    assert evidencia.ubicar(db, inst.id, 0, "recibio los legajos")["pagina"] == 2
    assert evidencia.ubicar(db, inst.id, None, "esto no está en el documento") is None


def test_un_ocr_que_no_cabe_se_recorta_y_las_posiciones_no_quedan_fuera(monkeypatch):
    from app.servicios import texto

    monkeypatch.setattr(texto, "MAXIMO_CARACTERES", 30)
    contenido, paginas = texto._unir_paginas([("a" * 20, 10, 10, 90.0, [[0, 20, 0, 0, 1, 1, 1]]),
                                              ("b" * 20, 10, 10, 90.0, [[0, 20, 0, 0, 1, 1, 1]])], "ocr")
    assert len(contenido) == 30 and [(p.inicio, p.fin) for p in paginas] == [(0, 20), (22, 30)]


# --- RF-AI-002 -----------------------------------------------------------------------------------


def test_iniciar_deja_la_propuesta_como_registro_y_cancelar_la_conserva(cliente, db, fondo, archivista, monkeypatch):
    inst = _cargar(cliente, db, archivista, fondo, "oficio_digital.pdf", archivos.pdf_con_paginas(
        ["Primera hoja del expediente municipal de 1948", "Rafael Cuervo recibio los legajos del archivo"]))
    m = MotorDePrueba(_respuesta("Rafael Cuervo recibio los legajos"))
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    espacio = iniciar(cliente, archivista, [inst.id])
    p = db.get(PropuestaIA, uuid.UUID(espacio["propuesta"]["propuesta_id"]))
    assert p.origen == "descripcion" and p.motor == "motor-de-prueba" and p.version_prompt == motor.VERSION_PROMPT
    assert p.generada_en is not None and p.duracion_ms is not None and p.estado == "generada"
    assert p.parametros["temperatura"] == motor.TEMPERATURA
    # Sobre qué texto propuso: la huella de lo enviado coincide con el texto del documento.
    [doc] = p.entrada["documentos"]
    assert doc["huella_enviada"] == hashlib.sha256(inst.texto_extraido.encode()).hexdigest()
    assert p.respuesta == _respuesta("Rafael Cuervo recibio los legajos")  # tal como llegó
    assert p.contenido["entidades"][0]["pagina"] == 2 and p.entidades == 1 and p.confianza_media == 0.9
    assert propuestas_ia.integra(p)

    trabajo_id = espacio["trabajo_id"]
    assert cliente.post(f"/api/descripcion/{trabajo_id}/cancelar", headers=archivista).status_code == 204
    db.expire_all()
    p = db.get(PropuestaIA, p.id)
    assert p.estado == "cancelada" and p.estado_en is not None
    vista = cliente.get(f"/api/descripcion/propuestas/{p.id}", headers=archivista)
    assert vista.status_code == 200 and vista.json()["integra"] and vista.json()["respuesta"] == p.respuesta
    crear_usuario(db, "lector@correo.com", "consulta")
    assert cliente.get(f"/api/descripcion/propuestas/{p.id}", headers=ingresar(cliente, "lector@correo.com")).status_code == 403


def test_lo_que_propuso_el_motor_no_se_puede_alterar_ni_borrar(cliente, db, fondo, archivista, monkeypatch):
    inst = _cargar(cliente, db, archivista, fondo, "oficio_digital.pdf", archivos.pdf_con_paginas(
        ["Primera hoja del expediente municipal de 1948", "Rafael Cuervo recibio los legajos del archivo"]))
    monkeypatch.setattr(motor, "motor_activo", lambda: MotorDePrueba(_respuesta("Rafael Cuervo")))
    pid = iniciar(cliente, archivista, [inst.id])["propuesta"]["propuesta_id"]
    for sentencia in ("UPDATE propuestas_ia SET contenido = '{}'::jsonb WHERE id = :i",
                      "UPDATE propuestas_ia SET motor = 'otro' WHERE id = :i",
                      "DELETE FROM propuestas_ia WHERE id = :i"):
        with pytest.raises(DBAPIError, match="evidencia"):
            with db.begin_nested():
                db.execute(text(sentencia), {"i": pid})
    # El estado sí cambia.
    with db.begin_nested():
        db.execute(text("UPDATE propuestas_ia SET estado = 'expirada' WHERE id = :i"), {"i": pid})
    # Y si alguien desactiva el disparador y la altera, la huella lo delata.
    db.execute(text("ALTER TABLE propuestas_ia DISABLE TRIGGER propuestas_ia_inalterables"))
    db.execute(text("UPDATE propuestas_ia SET contenido = jsonb_set(contenido, '{titulo}', '\"otro\"') WHERE id = :i"),
               {"i": pid})
    db.execute(text("ALTER TABLE propuestas_ia ENABLE TRIGGER propuestas_ia_inalterables"))
    db.expire_all()
    assert not propuestas_ia.integra(db.get(PropuestaIA, uuid.UUID(pid)))


def test_publicar_enlaza_propuesta_relaciones_y_decisiones(cliente, db, fondo, archivista, monkeypatch):
    inst = _cargar(cliente, db, archivista, fondo, "oficio_digital.pdf", archivos.pdf_con_paginas(
        ["Primera hoja del expediente municipal de 1948", "Rafael Cuervo recibio los legajos del archivo"]))
    monkeypatch.setattr(motor, "motor_activo", lambda: MotorDePrueba(_respuesta("Rafael Cuervo recibio")))
    espacio = iniciar(cliente, archivista, [inst.id])
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert r.status_code == 201, r.text
    rid = uuid.UUID(r.json()["id"])
    db.expire_all()
    p = db.get(PropuestaIA, uuid.UUID(espacio["propuesta"]["propuesta_id"]))
    assert p.estado == "publicada" and p.recurso_id == rid
    assert db.get(TrabajoDescripcion, uuid.UUID(espacio["trabajo_id"])).propuesta_id == p.id
    rel = db.scalar(select(Relacion).where(Relacion.origen_id == rid, Relacion.fragmento.is_not(None)))
    assert rel.propuesta_id == p.id
    [decision] = [e for e in eventos(db, "decision_ia", rid) if e.valor_nuevo["tipo"] == "agente"]
    assert decision.valor_nuevo["propuesta_id"] == str(p.id)
    detalle = cliente.get(f"/api/descripcion/registros/{rid}", headers=archivista).json()
    assert [x["id"] for x in detalle["propuestas_ia"]] == [str(p.id)] and detalle["propuestas_ia"][0]["integra"]


def test_el_motor_real_entrega_la_version_exacta_del_modelo_y_los_tokens(monkeypatch):
    import httpx

    class Respuesta:
        status_code = 200

        def json(self):
            return {"modelVersion": "gemini-x-flash-001", "usageMetadata": {"promptTokenCount": 120},
                    "candidates": [{"content": {"parts": [{"text": '{"titulo": "T", "alcance_contenido": "A", "entidades": []}'}]}}]}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: Respuesta())
    m = motor.MotorGemini("clave", "gemini-x-flash")
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    p = motor.proponer([motor.Documento(id=uuid.uuid4(), nombre="a.txt", texto="Oficio de 1948")], "unidad_documental")
    assert p.version_modelo == "gemini-x-flash-001" and p.parametros["uso_tokens"] == {"promptTokenCount": 120}
    assert p.respuesta == {"titulo": "T", "alcance_contenido": "A", "entidades": []} and "respuesta" not in p.a_dict()


def test_sin_motor_configurado_no_se_registra_una_propuesta(cliente, db, fondo, archivista, monkeypatch):
    inst = _cargar(cliente, db, archivista, fondo, "oficio_digital.pdf", archivos.pdf_con_paginas(
        ["Primera hoja del expediente municipal de 1948", "Rafael Cuervo recibio los legajos del archivo"]))
    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    espacio = iniciar(cliente, archivista, [inst.id])
    assert "propuesta_id" not in espacio["propuesta"]
    assert db.scalar(select(PropuestaIA).where(PropuestaIA.trabajo_id == uuid.UUID(espacio["trabajo_id"]))) is None


def test_los_documentos_anteriores_se_paginan_con_la_orden_de_consola(cliente, db, fondo, archivista, monkeypatch):
    """Un documento cargado antes del lote 5 (sin páginas) y una relación ya
    publicada sin página: la orden los completa, ubicando el fragmento por su
    contenido."""
    from contextlib import contextmanager

    from app import cli

    inst = _cargar(cliente, db, archivista, fondo, "acta_escaneada.pdf", archivos.pdf_escaneado_paginas(ESCANEADO))
    db.execute(text("DELETE FROM paginas_texto WHERE instanciacion_id = :i"), {"i": inst.id})
    rel = Relacion(origen_tipo="recurso_documental", origen_id=fondo.id, destino_tipo="recurso_documental",
                   destino_id=fondo.id, tipo_relacion="asociacion", codigo_ric="has_or_had_subject", origen="persona",
                   fragmento="RECIBIO LOS LEGAJOS", fragmento_instanciacion_id=inst.id, fragmento_inicio=3)
    db.add(rel)
    db.commit()

    @contextmanager
    def _misma():
        yield db

    monkeypatch.setattr(cli, "SessionLocal", _misma)
    assert cli.paginar_textos() == 0
    db.expire_all()
    assert db.scalar(select(PaginaTexto.numero).where(PaginaTexto.instanciacion_id == inst.id,
                                                      PaginaTexto.numero == 3)) == 3
    assert db.get(Relacion, rel.id).fragmento_pagina == 2
