"""
Pruebas del Módulo 2 · Descripción multinivel (sección 9 del prompt).
El motor de análisis se reemplaza por uno de prueba que responde lo que
respondería Gemini; todo lo demás (candado, vocabulario, publicación,
auditoría) es el código real contra PostgreSQL real.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import ahora
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import EntidadVocabulario, Relacion, TrabajoDescripcion, TrabajoInstanciacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import motor, vocabulario
from app.servicios.consulta import CAMPOS_PROHIBIDOS
from tests.conftest import crear_usuario, ingresar

OFICIO_114 = ("Señor Gobernador del Departamento. Por medio de la presente, la Alcaldía Municipal informa a su "
              "despacho sobre el estado actual del archivo del municipio, con fecha 15 de marzo de 1948, solicitando "
              "se sirva disponer lo pertinente para su conservación. Atentamente, el Alcalde Municipal de Boyacá.")
OFICIO_115 = ("Tunja, 2 de abril de 1948. El Gobernador del Departamento responde a la Alcaldía Municipal que "
              "se enviará un funcionario para organizar el archivo del concejo.")


class MotorDePrueba:
    nombre = "motor-de-prueba"

    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.llamadas = []
        self.contextos = []

    def analizar(self, documentos, nivel, contexto=None):
        self.llamadas.append((documentos, nivel))
        self.contextos.append(contexto)
        return self.respuesta(documentos, nivel) if callable(self.respuesta) else self.respuesta


RESPUESTA_UNO = {
    "titulo": "Oficio de la Alcaldía Municipal sobre el estado del archivo",
    "alcance_contenido": "La Alcaldía informa al Gobernador sobre el estado del archivo municipal y pide medidas de conservación.",
    "confianza_alcance": 0.85,
    "entidades": [
        {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "productor", "valor": "Alcaldía Municipal",
         "fragmento": "la Alcaldía Municipal informa a su despacho", "documento": 1, "confianza": 0.93},
        {"tipo": "agente", "subtipo": "cargo", "rol": "destinatario", "valor": "Gobernador del Departamento",
         "fragmento": "Señor Gobernador del Departamento", "documento": 1, "confianza": 0.9},
        {"tipo": "fecha", "valor": "15 de marzo de 1948", "fecha_normalizada": "1948-03-15",
         "fragmento": "con fecha 15 de marzo de 1948", "documento": 1, "confianza": 0.97},
        {"tipo": "lugar", "valor": "Boyacá", "fragmento": "el Alcalde Municipal de Boyacá", "documento": 1, "confianza": 0.4},
        {"tipo": "actividad", "valor": "Conservación del archivo municipal",
         "fragmento": "disponer lo pertinente para su conservación", "documento": 1, "confianza": 0.75},
        {"tipo": "forma_documental", "valor": "Oficio", "fragmento": "Por medio de la presente", "documento": 1, "confianza": 0.8},
    ],
}


@pytest.fixture()
def fondo(db, admin):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Correspondencia municipal", creado_por_id=admin.id)
    f.fondo_id = f.id
    db.add(f)
    db.commit()
    return f


def documento(db, fondo, nombre, texto):
    i = Instanciacion(id=uuid.uuid4(), fondo_id=fondo.id, nombre_original=nombre, ruta=f"x/{nombre}", tamano_bytes=len(texto),
                      estado="listo_para_descripcion", paso="terminado", progreso=100, texto_extraido=texto,
                      origen_texto="capa_de_texto", formato_puid="fmt/18", formato_nombre="Acrobat PDF 1.4")
    db.add(i)
    db.commit()
    return i


@pytest.fixture()
def archivista(cliente, db):
    crear_usuario(db, "catalina@correo.com", "archivista", nombre="Catalina Torres")
    return ingresar(cliente, "catalina@correo.com")


@pytest.fixture()
def motor_prueba(monkeypatch):
    m = MotorDePrueba(RESPUESTA_UNO)
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    return m


def iniciar(cliente, cab, ids, nivel=None, codigo=200):
    r = cliente.post("/api/descripcion/iniciar", headers=cab,
                     json={"instanciacion_ids": [str(i) for i in ids], **({"nivel": nivel} if nivel else {})})
    assert r.status_code == codigo, r.text
    return r.json()


def aceptar_todo(espacio, **cambios):
    """Lo que envía la pantalla cuando el archivista acepta todas las propuestas."""
    entidades = []
    for e in espacio["propuesta"]["entidades"]:
        entidades.append({k: e[k] for k in ("tipo", "valor", "subtipo", "rol", "fecha_normalizada", "edtf", "fecha_subtipo",
                                             "tipo_clave", "agente_clave", "mandato_clave", "fragmento",
                                             "documento_id", "inicio", "clave")} | {"crear_nueva": True})
    datos = {"trabajo_id": espacio["trabajo_id"], "titulo": espacio["propuesta"]["titulo"],
             "alcance_contenido": espacio["propuesta"]["alcance"], "entidades": entidades}
    datos.update(cambios)
    return datos


def eventos(db, accion, entidad_id=None):
    q = select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
    if entidad_id:
        q = q.where(RegistroAuditoria.entidad_id == str(entidad_id))
    return db.scalars(q).all()


def claves(objeto):
    if isinstance(objeto, dict):
        for k, v in objeto.items():
            yield k
            yield from claves(v)
    elif isinstance(objeto, list):
        for v in objeto:
            yield from claves(v)


# --- De principio a fin ----------------------------------------------------------------------


def test_documento_individual_de_la_cola_a_la_publicacion(cliente, db, fondo, archivista, motor_prueba):
    d = documento(db, fondo, "Oficio_114_1948.pdf", OFICIO_114)
    cola = cliente.get("/api/descripcion/cola", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert [c["nombre"] for c in cola] == ["Oficio_114_1948.pdf"] and cola[0]["en_edicion_por"] is None

    espacio = iniciar(cliente, archivista, [d.id])
    assert espacio["nivel"] == "unidad_documental"
    assert espacio["documentos"][0]["texto"] == OFICIO_114
    p = espacio["propuesta"]
    assert p["disponible"] is True and p["motor"] == "motor-de-prueba" and len(p["entidades"]) == 6
    # Cada fragmento quedó ubicado en el texto y apunta a su documento.
    for e in p["entidades"]:
        assert e["fragmento_localizado"] and OFICIO_114[e["inicio"]:].startswith(e["fragmento"])
        assert e["documento_id"] == str(d.id)

    datos = aceptar_todo(espacio)
    datos["entidades"][1]["valor"] = "Gobernador de Boyacá"  # el archivista corrige una
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 201, r.text
    registro = r.json()
    assert registro["nivel"] == "unidad_documental" and registro["incluido_en"]["id"] == str(fondo.id)
    assert registro["forma_documental"]["nombre"] == "Oficio"
    assert [i["nombre"] for i in registro["instanciaciones"]] == ["Oficio_114_1948.pdf"]
    por_valor = {e["valor"]: e for e in registro["entidades"]}
    assert por_valor["Alcaldía Municipal"]["codigo_ric"] == "has_creator" and por_valor["Alcaldía Municipal"]["origen"] == "motor"
    assert por_valor["Gobernador de Boyacá"]["codigo_ric"] == "has_addressee"
    assert por_valor["Gobernador de Boyacá"]["origen"] == "motor_editado"
    assert por_valor["15 de marzo de 1948"]["codigo_ric"] == "is_creation_date_of"
    assert por_valor["15 de marzo de 1948"]["fecha_normalizada"] == "1948-03-15"
    assert por_valor["Boyacá"]["codigo_ric"] == "has_or_had_subject"
    assert por_valor["Conservación del archivo municipal"]["codigo_ric"] == "documents"
    assert registro["origen_titulo"] == "motor" and registro["origen_alcance"] == "motor"
    # El título quedó limpio: ninguna marca de estado mezclada en el texto.
    assert registro["titulo"] == RESPUESTA_UNO["titulo"]

    # Sale de la cola por sí sola, y la marca en edición se liberó.
    assert cliente.get("/api/descripcion/cola", headers=archivista, params={"fondo_id": str(fondo.id)}).json() == []
    assert db.scalar(select(func.count()).select_from(TrabajoInstanciacion).where(TrabajoInstanciacion.abierto)) == 0
    [evento] = eventos(db, "descripcion_publicada", registro["id"])
    assert evento.valor_nuevo["titulo"] == RESPUESTA_UNO["titulo"]


def test_conjunto_como_expediente_sintetiza_y_cita_el_documento_correcto(cliente, db, fondo, archivista, monkeypatch):
    a = documento(db, fondo, "Oficio_114_1948.pdf", OFICIO_114)
    b = documento(db, fondo, "Oficio_115_1948.pdf", OFICIO_115)
    respuesta = {
        "titulo": "Correspondencia sobre la organización del archivo municipal, 1948",
        "alcance_contenido": "Intercambio entre la Alcaldía y la Gobernación sobre el estado del archivo y el envío de un funcionario.",
        "entidades": [
            {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "productor", "valor": "Alcaldía Municipal",
             "fragmento": "la Alcaldía Municipal informa", "documento": 1, "confianza": 0.9},
            {"tipo": "lugar", "valor": "Tunja", "fragmento": "Tunja, 2 de abril de 1948", "documento": 2, "confianza": 0.9},
            {"tipo": "fecha", "valor": "2 de abril de 1948", "edtf": "1948-04-02", "fragmento": "2 de abril de 1948", "documento": 2, "confianza": 0.9},
        ],
    }
    m = MotorDePrueba(respuesta)
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    iniciar(cliente, archivista, [a.id, b.id], codigo=422)  # varios sin nivel: hay que elegirlo
    espacio = iniciar(cliente, archivista, [a.id, b.id], nivel="expediente")
    # El motor recibió los dos documentos, cada uno con su nombre.
    [(documentos, nivel)] = m.llamadas
    assert [d.nombre for d in documentos] == ["Oficio_114_1948.pdf", "Oficio_115_1948.pdf"] and nivel == "expediente"
    citas = {e["valor"]: e["documento_id"] for e in espacio["propuesta"]["entidades"]}
    assert citas == {"Alcaldía Municipal": str(a.id), "Tunja": str(b.id), "2 de abril de 1948": str(b.id)}

    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert r.status_code == 201, r.text
    registro = r.json()
    assert registro["nivel"] == "expediente"
    assert sorted(i["nombre"] for i in registro["instanciaciones"]) == ["Oficio_114_1948.pdf", "Oficio_115_1948.pdf"]


def test_fragmento_que_no_esta_en_el_texto_rebaja_la_confianza(cliente, db, fondo, archivista, monkeypatch):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    respuesta = {"titulo": "x", "alcance_contenido": "", "entidades": [
        {"tipo": "agente", "rol": "productor", "valor": "Juan Inventado", "fragmento": "firmado por Juan Inventado",
         "documento": 1, "confianza": 0.99}]}
    monkeypatch.setattr(motor, "motor_activo", lambda: MotorDePrueba(respuesta))
    [e] = iniciar(cliente, archivista, [d.id])["propuesta"]["entidades"]
    assert e["fragmento_localizado"] is False and e["confianza"] <= 0.3 and e["documento_id"] is None


def test_entidad_con_confianza_baja_no_bloquea_la_publicacion(cliente, db, fondo, archivista, motor_prueba):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    baja = [e for e in espacio["propuesta"]["entidades"] if e["confianza"] < 0.7]
    assert [e["valor"] for e in baja] == ["Boyacá"]
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert r.status_code == 201
    boyaca = next(e for e in r.json()["entidades"] if e["valor"] == "Boyacá")
    assert boyaca["confianza"] == 0.4 and boyaca["estado_revision"] == "validado"


def test_sin_motor_se_describe_a_mano(cliente, db, fondo, archivista, monkeypatch):
    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    assert espacio["propuesta"]["disponible"] is False and "a mano" in espacio["propuesta"]["aviso"]
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json={
        "trabajo_id": espacio["trabajo_id"], "titulo": "Oficio sobre el archivo", "alcance_contenido": "Texto propio.",
        "entidades": [{"tipo": "fecha", "valor": "1948", "edtf": "1948", "fecha_subtipo": "simple"}]})
    assert r.status_code == 201
    registro = r.json()
    assert registro["origen_titulo"] == "persona" and registro["entidades"][0]["origen"] == "persona"


def test_motor_que_falla_no_impide_describir(cliente, db, fondo, archivista, monkeypatch):
    class Roto:
        nombre = "roto"

        def analizar(self, *_):
            raise motor.MotorError("El motor de análisis respondió con un error (503).")

    monkeypatch.setattr(motor, "motor_activo", lambda: Roto())
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    assert "503" in espacio["propuesta"]["aviso"] and espacio["propuesta"]["entidades"] == []


# --- Vocabulario ------------------------------------------------------------------------------


def test_verificacion_encuentra_parecidos_y_no_confunde_distintos(cliente, db, fondo, archivista, admin):
    vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Alcaldía Municipal de Tunja", subtipo="entidad_corporativa",
                      origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    vocabulario.crear(db, fondo_id=fondo.id, clase="lugar", nombre="Alcaldía Municipal de Tunja", subtipo=None,
                      origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    db.commit()

    def verificar(tipo, valor):
        return cliente.post("/api/descripcion/verificar-vocabulario", headers=archivista,
                            json={"fondo_id": str(fondo.id), "tipo": tipo, "valor": valor}).json()

    [c] = verificar("agente", "alcaldia municipal de tunja")
    assert c["nombre"] == "Alcaldía Municipal de Tunja" and c["similitud"] == 1.0
    assert verificar("agente", "Alcaldía Municipal")[0]["nombre"] == "Alcaldía Municipal de Tunja"
    assert verificar("agente", "Gobernación de Boyacá") == []
    assert verificar("agente", "Juan Pérez") == []
    assert len(verificar("lugar", "Alcaldía de Tunja")) == 1  # solo compara dentro del mismo tipo


def test_reutilizar_no_crea_entidad_duplicada(cliente, db, fondo, archivista, admin, motor_prueba):
    existente = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Alcaldía Municipal", subtipo="entidad_corporativa",
                                  origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    db.commit()
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    datos = aceptar_todo(espacio)
    datos["entidades"][0].pop("crear_nueva")
    # Sin decidir: el sistema pregunta y no publica nada.
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 409 and r.json()["coincidencias"][0]["id"] == str(existente.id)
    assert db.scalar(select(func.count()).select_from(RecursoDocumental).where(RecursoDocumental.nivel == "unidad_documental")) == 0

    antes = db.scalar(select(func.count()).select_from(EntidadVocabulario).where(EntidadVocabulario.clase == "agente"))
    datos["entidades"][0]["reutilizar_id"] = str(existente.id)
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 201, r.text
    despues = db.scalar(select(func.count()).select_from(EntidadVocabulario).where(EntidadVocabulario.clase == "agente"))
    assert despues == antes + 1  # solo el Gobernador es nuevo
    productor = next(e for e in r.json()["entidades"] if e["codigo_ric"] == "has_creator")
    assert productor["entidad_id"] == str(existente.id)


def test_crear_nueva_cuando_el_archivista_dice_que_es_distinta(cliente, db, fondo, archivista, admin, motor_prueba):
    vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Alcaldía Municipal de Tunja", subtipo="entidad_corporativa",
                      origen="persona", confianza=None, motor=None, usuario_id=admin.id)
    db.commit()
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert r.status_code == 201
    nombres = set(db.scalars(select(EntidadVocabulario.nombre).where(EntidadVocabulario.clase == "agente")))
    assert {"Alcaldía Municipal", "Alcaldía Municipal de Tunja"} <= nombres


def test_la_verificacion_de_vocabulario_es_una_dependencia_real(cliente, db, fondo, archivista, motor_prueba, monkeypatch):
    llamadas = []
    original = vocabulario.verificar

    def espia(db_, fondo_id, clase, valor, *a, **k):
        llamadas.append((clase, valor))
        return original(db_, fondo_id, clase, valor, *a, **k)

    monkeypatch.setattr(vocabulario, "verificar", espia)
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    cliente.post("/api/descripcion/verificar-vocabulario", headers=archivista,
                 json={"fondo_id": str(fondo.id), "tipo": "agente", "valor": "Alcaldía"})
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio)).status_code == 201
    assert ("agente", "Alcaldía") in llamadas
    # Al publicar, cada agente, lugar, actividad y forma documental nuevos pasaron por el servicio.
    assert {c for c, _ in llamadas} == {"agente", "lugar", "forma_documental", "actividad"}


# --- Concurrencia -------------------------------------------------------------------------------


def test_bloqueo_entre_dos_archivistas(cliente, db, fondo, archivista, motor_prueba):
    from fastapi.testclient import TestClient

    from app.main import app
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    crear_usuario(db, "julian@correo.com", "archivista", nombre="Julián Rincón")
    with TestClient(app) as otro_cliente:
        otro = ingresar(otro_cliente, "julian@correo.com")
        espacio = iniciar(cliente, archivista, [d.id])
        # El segundo archivista no puede abrir el mismo documento.
        r = otro_cliente.post("/api/descripcion/iniciar", headers=otro, json={"instanciacion_ids": [str(d.id)]})
        assert r.status_code == 409 and "Catalina Torres" in r.json()["detail"]
        cola = otro_cliente.get("/api/descripcion/cola", headers=otro, params={"fondo_id": str(fondo.id)}).json()
        assert cola[0]["en_edicion_por"] == "Catalina Torres"
        # Tampoco puede publicar ni cancelar el trabajo ajeno.
        assert otro_cliente.post(f"/api/descripcion/{espacio['trabajo_id']}/cancelar", headers=otro).status_code == 404
        # Liberación por cancelación explícita.
        assert cliente.post(f"/api/descripcion/{espacio['trabajo_id']}/cancelar", headers=archivista).status_code == 204
        segundo = iniciar(otro_cliente, otro, [d.id])
        # Liberación por expiración: 30 minutos sin actividad.
        trabajo = db.get(TrabajoDescripcion, uuid.UUID(segundo["trabajo_id"]))
        trabajo.ultima_actividad = ahora() - timedelta(minutes=31)
        db.commit()
        tercero = iniciar(cliente, archivista, [d.id])
        db.refresh(trabajo)
        assert trabajo.estado == "expirado"
        r = otro_cliente.post("/api/descripcion/publicar", headers=otro, json=aceptar_todo(segundo))
        assert r.status_code == 409 and "liberó" in r.json()["detail"]
        assert cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(tercero)).status_code == 201
    assert len(eventos(db, "edicion_liberada", trabajo.id)) == 1


def test_el_latido_mantiene_la_marca(cliente, db, fondo, archivista, motor_prueba):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    trabajo = db.get(TrabajoDescripcion, uuid.UUID(espacio["trabajo_id"]))
    trabajo.ultima_actividad = ahora() - timedelta(minutes=25)
    db.commit()
    assert cliente.post(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/latido", headers=archivista).status_code == 204
    db.refresh(trabajo)
    assert ahora() - trabajo.ultima_actividad < timedelta(minutes=1)


def test_la_base_de_datos_impide_dos_marcas_sobre_el_mismo_documento(db, fondo, admin):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    for _ in range(2):
        t = TrabajoDescripcion(id=uuid.uuid4(), usuario_id=admin.id, fondo_id=fondo.id, nivel="unidad_documental")
        db.add(t)
        db.flush()
        db.add(TrabajoInstanciacion(trabajo_id=t.id, instanciacion_id=d.id, abierto=True))
        if _ == 0:
            db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.flush()


# --- Corrección posterior ---------------------------------------------------------------------------


def test_reabrir_y_editar_queda_en_auditoria_con_antes_y_despues(cliente, db, fondo, archivista, motor_prueba):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    espacio = iniciar(cliente, archivista, [d.id])
    registro = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio)).json()
    boyaca = next(e for e in registro["entidades"] if e["valor"] == "Boyacá")

    r = cliente.post(f"/api/descripcion/registros/{registro['id']}/reabrir", headers=archivista)
    assert r.status_code == 200
    trabajo_id = r.json()["trabajo_id"]
    r = cliente.patch(f"/api/descripcion/{registro['id']}", headers=archivista, json={
        "trabajo_id": trabajo_id, "titulo": "Oficio sobre la conservación del archivo municipal",
        "anular_relaciones": [boyaca["relacion_id"]],
        "agregar_entidades": [{"tipo": "lugar", "valor": "Tunja", "crear_nueva": True}]})
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["titulo"] == "Oficio sobre la conservación del archivo municipal" and nuevo["origen_titulo"] == "persona"
    valores = {e["valor"] for e in nuevo["entidades"]}
    assert "Boyacá" not in valores and "Tunja" in valores
    # La relación quitada no se borró: quedó anulada.
    anulada = db.get(Relacion, uuid.UUID(boyaca["relacion_id"]))
    assert anulada.estado == "anulada" and anulada.anulada_en is not None
    [evento] = eventos(db, "descripcion_editada", registro["id"])
    assert evento.valor_anterior["titulo"] == RESPUESTA_UNO["titulo"]
    assert evento.valor_nuevo["titulo"] == "Oficio sobre la conservación del archivo municipal"
    assert any("Boyacá" in x for x in evento.valor_anterior["entidades"])
    assert any("Tunja" in x for x in evento.valor_nuevo["entidades"])


def test_reapertura_tambien_se_bloquea_entre_personas(cliente, db, fondo, archivista, motor_prueba):
    from fastapi.testclient import TestClient

    from app.main import app
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    registro = cliente.post("/api/descripcion/publicar", headers=archivista,
                            json=aceptar_todo(iniciar(cliente, archivista, [d.id]))).json()
    cliente.post(f"/api/descripcion/registros/{registro['id']}/reabrir", headers=archivista)
    crear_usuario(db, "julian@correo.com", "archivista", nombre="Julián Rincón")
    with TestClient(app) as otro_cliente:
        otro = ingresar(otro_cliente, "julian@correo.com")
        r = otro_cliente.post(f"/api/descripcion/registros/{registro['id']}/reabrir", headers=otro)
        assert r.status_code == 409 and "Catalina Torres" in r.json()["detail"]


# --- Reglas de la cola y de la consulta pública ---------------------------------------------------------


def test_la_cola_nunca_devuelve_un_documento_ya_descrito(cliente, db, fondo, archivista, motor_prueba):
    a = documento(db, fondo, "a.pdf", OFICIO_114)
    b = documento(db, fondo, "b.pdf", OFICIO_115)
    documento(db, fondo, "c.pdf", "texto")
    en_proceso = Instanciacion(id=uuid.uuid4(), fondo_id=fondo.id, nombre_original="d.pdf", ruta="x/d", tamano_bytes=1,
                               estado="procesando")
    db.add(en_proceso)
    db.commit()
    cliente.post("/api/descripcion/publicar", headers=archivista,
                 json=aceptar_todo(iniciar(cliente, archivista, [a.id, b.id], nivel="expediente")))
    cola = cliente.get("/api/descripcion/cola", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert [c["nombre"] for c in cola] == ["c.pdf"]


def test_la_consulta_publica_no_expone_origen_confianza_ni_revision(cliente, db, fondo, archivista, motor_prueba):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    registro = cliente.post("/api/descripcion/publicar", headers=archivista,
                            json=aceptar_todo(iniciar(cliente, archivista, [d.id]))).json()
    interna = cliente.get(f"/api/descripcion/registros/{registro['id']}", headers=archivista).json()
    assert {"origen", "confianza", "estado_revision"} <= set(claves(interna))  # la vista interna sí los tiene

    crear_usuario(db, "laura@correo.com", "consulta")
    consulta = ingresar(cliente, "laura@correo.com")
    r = cliente.get(f"/api/catalogo/registros/{registro['id']}", headers=consulta)
    assert r.status_code == 200
    publica = r.json()
    assert publica["titulo"] == RESPUESTA_UNO["titulo"] and len(publica["entidades"]) == 5
    assert not (set(claves(publica)) & CAMPOS_PROHIBIDOS)
    assert "motor-de-prueba" not in r.text and "0.93" not in r.text


def test_nivel_superior_valido(cliente, db, fondo, archivista, motor_prueba):
    exp = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo="Correspondencia 1948", fondo_id=fondo.id,
                            incluido_en_id=fondo.id, publicado_en=ahora())
    db.add(exp)
    db.commit()
    a = documento(db, fondo, "a.pdf", OFICIO_114)
    b = documento(db, fondo, "b.pdf", OFICIO_115)
    opciones = cliente.get("/api/descripcion/niveles-superiores", headers=archivista,
                           params={"fondo_id": str(fondo.id), "nivel": "unidad_documental"}).json()
    assert [o["nivel"] for o in opciones] == ["fondo", "expediente"]
    r = cliente.post("/api/descripcion/publicar", headers=archivista,
                     json=aceptar_todo(iniciar(cliente, archivista, [a.id]), incluido_en_id=str(exp.id)))
    assert r.status_code == 201 and r.json()["incluido_en"]["titulo"] == "Correspondencia 1948"
    # Un expediente no puede quedar dentro de otro expediente.
    r = cliente.post("/api/descripcion/publicar", headers=archivista,
                     json=aceptar_todo(iniciar(cliente, archivista, [b.id]), incluido_en_id=str(r.json()["id"])))
    assert r.status_code == 422


def test_la_publicacion_es_todo_o_nada(cliente, db, fondo, archivista, motor_prueba):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    datos = aceptar_todo(iniciar(cliente, archivista, [d.id]))
    datos["entidades"].append({"tipo": "forma_documental", "valor": "Acta", "crear_nueva": True})  # dos formas: inválido
    antes = db.scalar(select(func.count()).select_from(Relacion))
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=datos)
    assert r.status_code == 422
    assert db.scalar(select(func.count()).select_from(Relacion)) == antes
    assert db.scalar(select(func.count()).select_from(EntidadVocabulario)) == 0
    assert db.scalar(select(func.count()).select_from(RecursoDocumental).where(RecursoDocumental.nivel == "unidad_documental")) == 0
    # La marca sigue tomada para que el archivista corrija y publique.
    datos["entidades"].pop()
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json=datos).status_code == 201


# --- Permisos --------------------------------------------------------------------------------------


def test_permisos_de_descripcion(cliente, db, fondo, motor_prueba):
    d = documento(db, fondo, "a.pdf", OFICIO_114)
    assert cliente.get("/api/descripcion/cola", params={"fondo_id": str(fondo.id)}).status_code == 401
    crear_usuario(db, "laura@correo.com", "consulta")
    consulta = ingresar(cliente, "laura@correo.com")
    assert cliente.get("/api/descripcion/cola", headers=consulta, params={"fondo_id": str(fondo.id)}).status_code == 403
    assert cliente.post("/api/descripcion/iniciar", headers=consulta, json={"instanciacion_ids": [str(d.id)]}).status_code == 403
    crear_usuario(db, "julian@correo.com", "revisor")
    revisor = ingresar(cliente, "julian@correo.com")
    assert cliente.get("/api/descripcion/cola", headers=revisor, params={"fondo_id": str(fondo.id)}).status_code == 200
    for ruta, cuerpo in (("/api/descripcion/iniciar", {"instanciacion_ids": [str(d.id)]}),
                         ("/api/descripcion/verificar-vocabulario", {"fondo_id": str(fondo.id), "tipo": "agente", "valor": "x"}),
                         ("/api/descripcion/publicar", {"trabajo_id": str(uuid.uuid4()), "titulo": "xxx"})):
        assert cliente.post(ruta, headers=revisor, json=cuerpo).status_code == 403, ruta
    assert cliente.patch(f"/api/descripcion/{uuid.uuid4()}", headers=revisor, json={"trabajo_id": str(uuid.uuid4())}).status_code == 403
