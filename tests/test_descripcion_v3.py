"""
Pruebas del Módulo 2, versión 3 (secciones 11 y 12 del prompt): parte
documental con su recorte, idioma y condiciones de acceso y de uso,
secuencia y custodio, sub-actividad, calendario declarado, contexto del
vocabulario del fondo para el motor y aviso de OCR con confianza baja.
"""

import io
import uuid

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import EntidadVocabulario, Fecha, Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import almacen, motor, vocabulario
from app.servicios.consulta import CAMPOS_PROHIBIDOS
from tests import archivos
from tests.test_descripcion import MotorDePrueba, aceptar_todo, archivista, claves, documento, fondo, iniciar  # noqa: F401

TEXTO = ("La Secretaría de Gobierno de Tunja, en ejercicio de la policía local, remite al Concejo Municipal "
         "el informe de permisos de 1948, con el sello de la Alcaldía al pie.")


def publicar(cliente, cab, espacio, **datos):
    r = cliente.post("/api/descripcion/publicar", headers=cab,
                     json={"trabajo_id": espacio["trabajo_id"], "titulo": datos.pop("titulo", "Oficio de prueba"),
                           **datos})
    return r


def documento_imagen(db, fondo, nombre="oficio_sello.png"):
    """Un documento con archivo real (PNG) en el almacenamiento, para ver y recortar sus páginas."""
    i_id = uuid.uuid4()
    contenido = archivos.png_con_texto()
    ruta, tamano = almacen.guardar(io.BytesIO(contenido), fondo.id, i_id, nombre, limite_bytes=10_000_000)
    i = Instanciacion(id=i_id, fondo_id=fondo.id, nombre_original=nombre, ruta=ruta, tamano_bytes=tamano,
                      estado="listo_para_descripcion", paso="terminado", progreso=100, texto_extraido=TEXTO,
                      origen_texto="ocr", formato_puid="fmt/11", formato_nombre="PNG", formato_mime="image/png",
                      huella="0" * 64, paginas=1)
    db.add(i)
    db.commit()
    return i


def publicada(db, fondo, titulo, incluido_en, nivel="unidad_documental"):
    r = RecursoDocumental(id=uuid.uuid4(), nivel=nivel, titulo=titulo, fondo_id=fondo.id, incluido_en_id=incluido_en.id,
                          publicado_en=__import__("app.db.base", fromlist=["ahora"]).ahora())
    db.add(r)
    db.commit()
    return r


@pytest.fixture()
def sin_motor(monkeypatch):
    monkeypatch.setattr(motor, "motor_activo", lambda: None)


# --- Parte documental ---------------------------------------------------------------------------------


def test_parte_documental_con_recorte_queda_unida_a_su_unidad_documental(cliente, db, fondo, archivista, sin_motor):
    d = documento_imagen(db, fondo)
    espacio = iniciar(cliente, archivista, [d.id])
    paginas = cliente.get(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/documentos/{d.id}/paginas", headers=archivista)
    assert paginas.json() == {"admite": True, "total": 1}
    imagen = cliente.get(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/documentos/{d.id}/paginas/1", headers=archivista)
    assert imagen.status_code == 200 and imagen.headers["content-type"] == "image/png"
    r = publicar(cliente, archivista, espacio, partes=[{
        "titulo": "Sello de la Alcaldía", "tipo_parte": {"valor": "Sello", "crear_nueva": True},
        "alcance": "Sello húmedo al pie del oficio.",
        "recorte": {"instanciacion_id": str(d.id), "pagina": 1, "x": 0.05, "y": 0.1, "ancho": 0.5, "alto": 0.3}}])
    assert r.status_code == 201, r.text
    [parte] = r.json()["partes"]
    assert parte["titulo"] == "Sello de la Alcaldía" and parte["tipo_parte"] == "Sello"
    # La parte es un Record Resource de nivel parte documental, dentro de la unidad documental.
    p = db.get(RecursoDocumental, uuid.UUID(parte["id"]))
    assert p.nivel == "parte_documental" and str(p.incluido_en_id) == r.json()["id"]
    assert db.scalar(select(Relacion).where(Relacion.codigo_ric == "has_or_had_constituent",
                                            Relacion.destino_id == p.id)).origen_id == uuid.UUID(r.json()["id"])
    # Su recorte es una instanciación propia, con huella y origen declarado.
    [rec] = parte["instanciaciones"]
    inst = db.get(Instanciacion, uuid.UUID(rec["id"]))
    assert inst.recorte_de_id == d.id and inst.recorte_zona["ancho"] == 0.5 and len(inst.huella) == 64
    with Image.open(almacen.ruta_absoluta(inst.ruta)) as img:
        assert img.format == "PNG" and img.size[0] > 100
    assert db.get(Instanciacion, d.id).ruta != inst.ruta  # el original no se toca
    from app.servicios import segunda_copia
    assert segunda_copia.vigente(db, inst.id) is not None  # con su segunda copia, como toda instanciación
    # La parte sabe de quién es parte; el recorte no aparece en la cola de por describir.
    detalle_parte = cliente.get(f"/api/descripcion/registros/{p.id}", headers=archivista).json()
    assert detalle_parte["parte_de"]["id"] == r.json()["id"]
    cola = cliente.get("/api/descripcion/cola", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert str(inst.id) not in {x["id"] for x in cola}
    # El tipo de parte quedó en el vocabulario y se verifica como cualquier otro.
    tipo = db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.clase == "tipo_parte"))
    assert tipo.nombre == "Sello"
    assert eventos_de(db, "recorte_creado")


def test_tipo_de_parte_parecido_pregunta_antes_de_crear(cliente, db, fondo, archivista, sin_motor):
    vocabulario.crear(db, fondo_id=fondo.id, clase="tipo_parte", nombre="Sello", subtipo=None, origen="persona",
                      confianza=None, motor=None, usuario_id=None)
    db.commit()
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, partes=[{"titulo": "Sello", "tipo_parte": {"valor": "Sello."}}])
    assert r.status_code == 409 and r.json()["coincidencias"][0]["nombre"] == "Sello"


def test_partes_solo_en_una_unidad_documental_y_el_recorte_de_sus_documentos(cliente, db, fondo, archivista, sin_motor):
    a, b = documento(db, fondo, "a.pdf", TEXTO), documento(db, fondo, "b.pdf", TEXTO)
    espacio = iniciar(cliente, archivista, [a.id, b.id], nivel="expediente")
    assert publicar(cliente, archivista, espacio, partes=[{"titulo": "Anexo"}]).status_code == 422
    otro = documento_imagen(db, fondo, "otro.png")
    espacio = iniciar(cliente, archivista, [documento_imagen(db, fondo).id])
    r = publicar(cliente, archivista, espacio, partes=[{"titulo": "Firma", "recorte": {
        "instanciacion_id": str(otro.id), "pagina": 1, "x": 0, "y": 0, "ancho": 0.5, "alto": 0.5}}])
    assert r.status_code == 422 and "documentos de esta descripción" in r.json()["detail"]


def test_recorte_fallido_no_deja_archivo(cliente, db, fondo, archivista, sin_motor):
    d = documento_imagen(db, fondo)
    espacio = iniciar(cliente, archivista, [d.id])
    antes = set(almacen.raiz().rglob("*.png"))
    # La segunda parte es inválida (título vacío): no queda ni la primera ni su archivo.
    r = publicar(cliente, archivista, espacio, partes=[
        {"titulo": "Sello", "recorte": {"instanciacion_id": str(d.id), "pagina": 1, "x": 0, "y": 0, "ancho": 0.3, "alto": 0.3}},
        {"titulo": " "}])
    assert r.status_code == 422
    assert set(almacen.raiz().rglob("*.png")) == antes
    assert db.scalar(select(Instanciacion).where(Instanciacion.recorte_de_id == d.id)) is None


# --- Idioma, acceso, uso ---------------------------------------------------------------------------------


def test_idioma_y_condiciones_se_guardan_y_sin_ellas_publica(cliente, db, fondo, archivista, sin_motor):
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, idiomas=["spa", "lat"],
                 condiciones_acceso="Consulta libre en sala.", condiciones_uso="Reproducción con permiso escrito.")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["idiomas"] == ["spa", "lat"] and d["origen_idiomas"] == "persona"
    assert (d["condiciones_acceso"], d["condiciones_uso"]) == ("Consulta libre en sala.", "Reproducción con permiso escrito.")
    publica = cliente.get(f"/api/catalogo/registros/{d['id']}", headers=archivista).json()
    assert publica["idiomas"] == ["spa", "lat"] and publica["condiciones_uso"] == "Reproducción con permiso escrito."
    assert not set(claves(publica)) & CAMPOS_PROHIBIDOS
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "b.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio)
    assert r.status_code == 201 and r.json()["idiomas"] == [] and r.json()["condiciones_acceso"] is None
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "c.pdf", TEXTO).id])
    assert publicar(cliente, archivista, espacio, idiomas=["español"]).status_code == 422


def test_el_motor_propone_el_idioma_y_su_decision_queda_en_auditoria(cliente, db, fondo, archivista, monkeypatch):
    m = MotorDePrueba({"titulo": "Oficio", "alcance_contenido": "Informe.", "entidades": [], "idiomas": ["spa"],
                       "confianza_idiomas": 0.95})
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    assert espacio["propuesta"]["idiomas"] == ["spa"]
    r = publicar(cliente, archivista, espacio, titulo="Oficio", alcance_contenido="Informe.", idiomas=["spa", "lat"])
    assert r.json()["origen_idiomas"] == "motor_editado"
    [ev] = [e for e in eventos_de(db, "decision_ia", r.json()["id"]) if e.valor_nuevo["tipo"] == "idioma"]
    assert ev.valor_nuevo["decision"] == "corregida"
    assert ev.valor_nuevo["propuesto"] == {"valor": "spa"} and ev.valor_nuevo["final"] == {"valor": "lat,spa"}


# --- Secuencia y custodio ----------------------------------------------------------------------------------


def test_secuencia_y_custodio_se_guardan_y_se_ven_en_el_catalogo(cliente, db, fondo, archivista, sin_motor):
    serie = publicada(db, fondo, "Correspondencia", fondo, nivel="serie")
    anterior = publicada(db, fondo, "Oficio 209 de 1948", serie)
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, incluido_en_id=str(serie.id), sigue_a_id=str(anterior.id), entidades=[
        {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "productor", "valor": "Secretaría de Gobierno",
         "crear_nueva": True},
        {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "custodio", "valor": "Archivo Histórico de Tunja",
         "crear_nueva": True}])
    assert r.status_code == 201, r.text
    d = r.json()
    assert [(x["titulo"], x["posicion"]) for x in d["secuencia"]] == [("Oficio 209 de 1948", "sigue_a")]
    fila = db.scalar(select(Relacion).where(Relacion.codigo_ric == "precedes_or_preceded"))
    assert fila.origen_id == anterior.id and str(fila.destino_id) == d["id"]  # del anterior al siguiente
    [custodio] = [e for e in d["entidades"] if e["rol"] == "custodio"]
    assert custodio["codigo_ric"] == "has_or_had_holder" and custodio["valor"] == "Archivo Histórico de Tunja"
    publica = cliente.get(f"/api/catalogo/registros/{d['id']}", headers=archivista).json()
    assert publica["secuencia"][0]["uri_rico"] == "rico:followsOrFollowed"
    assert any(e["rol"] == "custodio" for e in publica["entidades"])
    # Desde el anterior se lee la inversa.
    desde = cliente.get(f"/api/descripcion/registros/{anterior.id}", headers=archivista).json()
    assert [(x["titulo"], x["posicion"]) for x in desde["secuencia"]] == [(d["titulo"], "precede_a")]


def test_secuencia_solo_en_la_misma_serie(cliente, db, fondo, archivista, sin_motor):
    s1 = publicada(db, fondo, "Correspondencia", fondo, nivel="serie")
    s2 = publicada(db, fondo, "Actas", fondo, nivel="serie")
    otro = publicada(db, fondo, "Acta 3 de 1948", s2)
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, incluido_en_id=str(s1.id), precede_a_id=str(otro.id))
    assert r.status_code == 422 and "misma serie" in r.json()["detail"]


def test_custodio_igual_al_productor_se_rechaza(cliente, db, fondo, archivista, sin_motor):
    a = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Alcaldía de Tunja", subtipo="entidad_corporativa",
                          origen="persona", confianza=None, motor=None, usuario_id=None)
    db.commit()
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "agente", "rol": "productor", "valor": a.nombre, "reutilizar_id": str(a.id)},
        {"tipo": "agente", "rol": "custodio", "valor": a.nombre, "reutilizar_id": str(a.id)}])
    assert r.status_code == 422 and "distinto del productor" in r.json()["detail"]


# --- Sub-actividad ---------------------------------------------------------------------------------------


def test_actividad_publicada_como_sub_actividad_de_otra_existente(cliente, db, fondo, archivista, sin_motor):
    mayor = vocabulario.crear(db, fondo_id=fondo.id, clase="actividad", nombre="Registro civil de 1948", subtipo=None,
                              origen="persona", confianza=None, motor=None, usuario_id=None)
    db.commit()
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "actividad", "valor": "Inscripción de nacimientos de marzo de 1948", "crear_nueva": True,
         "actividad_mayor_id": str(mayor.id)}])
    assert r.status_code == 201, r.text
    fila = db.scalar(select(Relacion).where(Relacion.codigo_ric == "has_direct_subevent"))
    assert fila.origen_id == mayor.id
    # La actividad mayor expone la lista de sus sub-actividades (vocabularios).
    vinculos = cliente.get(f"/api/vocabulario/{mayor.id}", headers=archivista).json()["ficha"]["vinculos"]
    assert [(v["etiqueta"], v["con"]["nombre"]) for v in vinculos] == [
        ("tiene como sub-actividad a", "Inscripción de nacimientos de marzo de 1948")]
    # Una actividad mayor que no es actividad se rechaza.
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "b.pdf", TEXTO).id])
    lugar = vocabulario.crear(db, fondo_id=fondo.id, clase="lugar", nombre="Tunja", subtipo=None, origen="persona",
                              confianza=None, motor=None, usuario_id=None)
    db.commit()
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "actividad", "valor": "Otra", "crear_nueva": True, "actividad_mayor_id": str(lugar.id)}])
    assert r.status_code == 422


# --- Grupo -------------------------------------------------------------------------------------------------


def test_agente_grupo_se_crea_desde_la_descripcion(cliente, db, fondo, archivista, sin_motor):
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "agente", "subtipo": "grupo", "rol": "productor", "valor": "Junta de Festejos", "crear_nueva": True}])
    assert r.status_code == 201, r.text
    [e] = r.json()["entidades"]
    assert e["subtipo"] == "grupo"
    assert db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.nombre == "Junta de Festejos")).subtipo == "grupo"


# --- Calendario ------------------------------------------------------------------------------------------


def test_la_fecha_declara_su_calendario(cliente, db, fondo, archivista, sin_motor):
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    r = publicar(cliente, archivista, espacio, entidades=[
        {"tipo": "fecha", "valor": "hacia 1948", "edtf": "1948~", "fecha_subtipo": "simple"}])
    [f] = [e for e in r.json()["entidades"] if e["tipo"] == "fecha"]
    assert f["calendario"] == "gregoriano" and f["edtf"] == "1948~"
    assert db.scalar(select(Fecha)).calendario == "gregoriano"
    publica = cliente.get(f"/api/catalogo/registros/{r.json()['id']}", headers=archivista).json()
    assert [e["calendario"] for e in publica["entidades"] if e["tipo"] == "fecha"] == ["gregoriano"]


# --- Contexto del vocabulario para el motor ----------------------------------------------------------------


def test_el_motor_recibe_el_vocabulario_del_fondo_y_referencia_la_entidad_existente(cliente, db, fondo, archivista,
                                                                                    monkeypatch):
    existente = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Secretaría de Gobierno de Tunja",
                                  subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None,
                                  usuario_id=None)
    ajena = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Ministerio de Hacienda",
                              subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None, usuario_id=None)
    vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="Ghostscript", version="10.05.1")
    db.commit()

    def responder(documentos, nivel):
        codigo = next(c.codigo for c in m.contextos[-1] if c.id == str(existente.id))
        return {"titulo": "Oficio", "alcance_contenido": "Informe.", "entidades": [
            {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "productor", "valor": "Secretaría de Gobierno de Tunja",
             "existente": codigo, "fragmento": "La Secretaría de Gobierno de Tunja", "documento": 1, "confianza": 0.9},
            {"tipo": "agente", "subtipo": "entidad_corporativa", "rol": "destinatario", "valor": "Concejo Municipal",
             "fragmento": "al Concejo Municipal", "documento": 1, "confianza": 0.9}]}

    m = MotorDePrueba(responder)
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "a.pdf", TEXTO).id])
    contexto = m.contextos[-1]
    # Recibe la entidad que el texto menciona, no la que no menciona, ni los mecanismos.
    assert str(existente.id) in {c.id for c in contexto} and str(ajena.id) not in {c.id for c in contexto}
    assert all(c.subtipo != "mecanismo" for c in contexto)
    productor, destinatario = espacio["propuesta"]["entidades"]
    assert productor["existente_id"] == str(existente.id) and destinatario["existente_id"] is None
    assert espacio["propuesta"]["contexto_enviado"]["agente"] >= 1
    # El contexto va en el pedido, no en la instrucción: la versión no cambia.
    assert espacio["propuesta"]["version_prompt"] == motor.VERSION_PROMPT


def test_coincidencia_exacta_con_el_contexto_se_referencia_aunque_el_motor_no_de_codigo(db, fondo):
    e = vocabulario.crear(db, fondo_id=fondo.id, clase="lugar", nombre="Tunja", subtipo=None, origen="persona",
                          confianza=None, motor=None, usuario_id=None)
    db.commit()
    contexto = vocabulario.contexto_para_motor(db, fondo.id, "los mercados de TUNJA en 1948")
    assert [c.nombre for c in contexto] == ["Tunja"]
    p = motor.normalizar({"titulo": "x", "alcance_contenido": "y", "entidades": [
        {"tipo": "lugar", "valor": "Tunja", "fragmento": "los mercados de TUNJA", "documento": 1, "confianza": 0.8}]},
        [motor.Documento(id=uuid.uuid4(), nombre="a", texto="los mercados de TUNJA en 1948")], "m", contexto)
    assert p.entidades[0].existente_id == str(e.id)
    # Un código de otro tipo no se acepta.
    p = motor.normalizar({"titulo": "x", "alcance_contenido": "y", "entidades": [
        {"tipo": "agente", "valor": "Alguien", "existente": contexto[0].codigo, "fragmento": "x", "documento": 1,
         "confianza": 0.8}]}, [motor.Documento(id=uuid.uuid4(), nombre="a", texto="x")], "m", contexto)
    assert p.entidades[0].existente_id is None


# --- Aviso de OCR con confianza baja ----------------------------------------------------------------------


def test_el_espacio_de_trabajo_avisa_la_confianza_baja_del_ocr(cliente, db, fondo, archivista, sin_motor):
    d = documento(db, fondo, "copia_borrosa.png", TEXTO)
    d.confianza_ocr, d.ocr_baja_confianza, d.origen_texto = 52.4, True, "ocr"
    db.commit()
    espacio = iniciar(cliente, archivista, [d.id])
    [doc] = espacio["documentos"]
    assert doc["ocr_baja_confianza"] is True and doc["confianza_ocr"] == 52.4 and espacio["umbral_ocr"] == 70


def test_la_pagina_de_un_trabajo_ajeno_no_se_entrega(cliente, db, fondo, archivista, sin_motor):
    from tests.conftest import crear_usuario, ingresar

    d = documento_imagen(db, fondo)
    espacio = iniciar(cliente, archivista, [d.id])
    crear_usuario(db, "otra@correo.com", "archivista")
    otra = ingresar(cliente, "otra@correo.com")
    r = cliente.get(f"/api/descripcion/trabajos/{espacio['trabajo_id']}/documentos/{d.id}/paginas/1", headers=otra)
    assert r.status_code == 404


def eventos_de(db, accion, entidad_id=None):
    q = select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
    if entidad_id:
        q = q.where(RegistroAuditoria.entidad_id == str(entidad_id))
    return db.scalars(q).all()
