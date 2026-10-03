"""
Cierre de la auditoría RiC, bloque 3 (descripción): DES-03 (EDTF fuera del
subconjunto), DES-07 (ISAD(G) completa: 26 elementos con fuente) y DES-11
(calificador «%» y dígitos sin precisar persistidos por la API).
"""

import re
import uuid

import pytest
from rdflib import Literal, Namespace
from sqlalchemy import select

from app.db.base import ahora
from app.models.descripcion import Fecha
from app.models.instanciacion import Instanciacion
from app.models.lote import LoteIngesta
from app.models.recurso_documental import RecursoDocumental
from app.servicios import exportacion_rico, fechas, isadg, ric_o, vocabulario
from tests.test_descripcion import aceptar_todo, archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_descripcion_contexto import OFICIO

RICO = Namespace(ric_o.RICO)


# --- DES-03 · EDTF ----------------------------------------------------------------------------


@pytest.mark.parametrize("edtf", ["1948-XX-12", "194X-03", "19XX-05-02", "{1948~,1949}", "../1952"])
def test_expresiones_de_nivel_2_o_fuera_del_subconjunto_se_rechazan(edtf):
    with pytest.raises(fechas.FechaInvalida):
        fechas.interpretar(edtf)


@pytest.mark.parametrize("edtf", ["1948-XX", "1948-03-XX", "1948-XX-XX", "194X", "19XX", "1948%", "/1952"])
def test_digitos_sin_precisar_desde_la_derecha_siguen_admitidos(edtf):
    assert fechas.interpretar(edtf).edtf == edtf


def test_calificador_ambos_y_decada_persisten_por_la_api(cliente, db, fondo, archivista, monkeypatch):
    """DES-11: «%» y «194X» llegan por POST /publicar y quedan normalizados."""
    from app.servicios import motor

    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "acta.pdf", OFICIO).id])
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json={
        "trabajo_id": espacio["trabajo_id"], "titulo": "Acta de la década", "entidades": [
            {"tipo": "fecha", "valor": "¿hacia 1948?", "edtf": "1948%", "fecha_subtipo": "simple"},
            {"tipo": "fecha", "valor": "años cuarenta", "edtf": "194X", "fecha_subtipo": "simple"}]})
    assert r.status_code == 201, r.text
    guardadas = {f.edtf: f for f in db.scalars(select(Fecha)).all()}
    assert (str(guardadas["1948%"].inicio), str(guardadas["1948%"].fin)) == ("1948-01-01", "1948-12-31")
    assert (str(guardadas["194X"].inicio), str(guardadas["194X"].fin)) == ("1940-01-01", "1949-12-31")
    legibles = {e["edtf"]: e["fecha_legible"] for e in r.json()["entidades"]}
    assert legibles["1948%"] == "c. 1948 (incierta)"  # aproximada («c.») e incierta a la vez
    assert legibles["194X"] == "década de 1940"
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "b.pdf", OFICIO).id])
    assert cliente.post("/api/descripcion/publicar", headers=archivista, json={
        "trabajo_id": espacio["trabajo_id"], "titulo": "Acta", "entidades": [
            {"tipo": "fecha", "valor": "12 de un mes", "edtf": "1948-XX-12", "fecha_subtipo": "simple"}]}
    ).status_code == 422


# --- DES-07 · ISAD(G) completa ------------------------------------------------------------------


TEXTOS = {
    "forma_ingreso": "Recibido en custodia del Concejo en 1990.",
    "valoracion": "Conservación total por valor histórico.",
    "nuevos_ingresos": "No se esperan nuevos ingresos.",
    "organizacion": "Orden cronológico dentro de cada expediente.",
    "instrumentos_descripcion": "Inventario de 1995 en papel.",
    "localizacion_originales": "Los originales están en el Archivo Regional de Boyacá.",
    "localizacion_copias": "Microfilme en el AGN, rollo 12.",
    "unidades_relacionadas": "Actas del Concejo, 1946-1950 (Archivo del Concejo).",
    "nota_publicaciones": "Citado en Historia de Tunja (1998).",
    "nota": "Encuadernado con tapas de cuero.",
    "nota_archivero": "Descripción revisada contra el inventario de 1995.",
    "reglas_descripcion": "ISAD(G) 2.ª ed.; RiC-CM 1.0; NTC 4095.",
}


def test_cada_uno_de_los_26_elementos_tiene_fuente_y_motivo_si_no_se_exporta():
    from rdflib import URIRef

    owl = ric_o._owl()
    assert len(isadg.ELEMENTOS) == 26
    assert set(isadg.CAMPOS_TEXTO.values()) <= set(isadg.ELEMENTOS)
    for elemento, (nombre, fuente, rico) in isadg.ELEMENTOS.items():
        assert nombre and fuente, elemento
        assert rico or elemento in isadg.SIN_PROPIEDAD_RICO, f"{elemento} sin propiedad ni motivo"
        for nombre_rico in re.findall(r"rico:([A-Za-z]+)", rico or ""):  # toda propiedad citada existe en el OWL
            assert (URIRef(ric_o.RICO + nombre_rico), None, None) in owl, nombre_rico


def test_publicar_con_todos_los_elementos_y_la_ficha_los_devuelve(cliente, db, fondo, archivista, monkeypatch):
    from app.servicios import motor

    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    d = documento(db, fondo, "acta.pdf", OFICIO)
    espacio = iniciar(cliente, archivista, [d.id])
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json={
        "trabajo_id": espacio["trabajo_id"], "titulo": "Acta de la sesión", "alcance_contenido": "Sesión ordinaria.",
        "condiciones_acceso": "Libre.", "condiciones_uso": "Con cita de la fuente.", "idiomas": ["spa"],
        "historia_archivistica": "Llegó con el fondo del Concejo.", "isadg": TEXTOS, "escrituras": ["latn"]})
    assert r.status_code == 201, r.text
    recurso_id = r.json()["id"]
    detalle = cliente.get(f"/api/descripcion/registros/{recurso_id}", headers=archivista).json()
    assert detalle["isadg"]["escrituras"] == ["Latn"] and detalle["isadg"]["nota"] == TEXTOS["nota"]
    ficha = cliente.get(f"/api/descripcion/registros/{recurso_id}/isadg", headers=archivista).json()
    por = {e["elemento"]: e for e in ficha["elementos"]}
    assert ficha["total"] == 26
    for campo, elemento in isadg.CAMPOS_TEXTO.items():
        assert TEXTOS[campo] in (por[elemento]["valor"] or ""), elemento
    assert "Latn (latina)" in por["3.4.3"]["valor"] and "spa" in por["3.4.3"]["valor"]
    assert por["3.4.4"]["valor"].startswith("Formatos digitales: Acrobat PDF 1.4")
    assert por["3.7.1"]["valor"].startswith("Descrito por Catalina Torres")
    assert por["3.7.3"]["valor"].startswith("Publicada el")
    # Un elemento que no existe o una escritura no ISO 15924 no se aceptan.
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "c.pdf", OFICIO).id])
    for malo in ({"isadg": {"inventado": "x"}}, {"escrituras": ["Latin"]}):
        assert cliente.post("/api/descripcion/publicar", headers=archivista, json={
            "trabajo_id": espacio["trabajo_id"], "titulo": "Otra acta"} | malo).status_code == 422


def test_forma_de_ingreso_sale_del_lote_y_las_caracteristicas_del_original(cliente, db, fondo, archivista, admin,
                                                                           monkeypatch):
    from app.servicios import motor

    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    secretaria = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Secretaría de Gobierno",
                                   subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None,
                                   usuario_id=None)
    lote = LoteIngesta(id=uuid.uuid4(), fondo_id=fondo.id, numero="L-2026-0001", forma_ingreso="transferencia_primaria",
                       dependencia_origen_id=secretaria.id, acta_numero="AT-014", acta_fecha_edtf="2026-09-30",
                       estado="confirmado", creado_en=ahora(), confirmado_en=ahora())
    db.add(lote)
    db.flush()
    d = documento(db, fondo, "acta.pdf", OFICIO)
    d.lote_id = lote.id
    db.commit()
    espacio = iniciar(cliente, archivista, [d.id])
    r = cliente.post("/api/descripcion/publicar", headers=archivista,
                     json={"trabajo_id": espacio["trabajo_id"], "titulo": "Acta transferida"})
    recurso_id = r.json()["id"]
    assert cliente.post(f"/api/descripcion/registros/{recurso_id}/original-fisico", headers=archivista, json={
        "soporte": "papel", "ubicacion": "Caja 3, carpeta 2",
        "caracteristicas_fisicas": "Manchas de humedad en los folios 1 a 3."}).status_code == 201
    por = {e["elemento"]: e for e in cliente.get(f"/api/descripcion/registros/{recurso_id}/isadg",
                                                 headers=archivista).json()["elementos"]}
    assert por["3.2.4"]["valor"].startswith("Transferencia primaria desde Secretaría de Gobierno, acta AT-014")
    assert "Manchas de humedad" in por["3.4.4"]["valor"]
    assert "Caja 3, carpeta 2" in por["3.5.1"]["valor"]
    # En RDF: la nota física en la instanciación del original (RiC-A31).
    db.expire_all()
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    assert (None, RICO.physicalCharacteristicsNote, Literal("Manchas de humedad en los folios 1 a 3.")) in g


def test_organizacion_nuevos_ingresos_y_nota_salen_en_rico(db, fondo, admin):
    serie = RecursoDocumental(id=uuid.uuid4(), nivel="serie", titulo="Actas", fondo_id=fondo.id, incluido_en_id=fondo.id,
                              publicado_en=ahora(), organizacion="Cronológica.", nuevos_ingresos="Anuales.",
                              nota="Serie abierta.")
    db.add(serie)
    db.commit()
    g = exportacion_rico.exportar(db, db.get(RecursoDocumental, fondo.id)).grafo
    s = exportacion_rico.uri(serie.id)
    assert (s, RICO.structure, Literal("Cronológica.")) in g
    assert (s, RICO.accruals, Literal("Anuales.")) in g
    assert (s, RICO.generalDescription, Literal("Serie abierta.")) in g


# --- DES-10 · las otras formas del nombre también se buscan ----------------------------------------


def test_la_verificacion_encuentra_la_entidad_por_otra_forma_del_nombre(cliente, db, fondo, archivista, admin):
    from app.servicios import autoridad

    alcaldia = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Alcaldía Municipal de Tunja",
                                 subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None,
                                 usuario_id=None)
    autoridad.agregar_nombre(db, alcaldia, tipo="otra", nombre="Cabildo de Tunja", idioma=None, regla=None,
                             vigencia_edtf="1539/1821", usuario_id=admin.id)
    db.commit()
    r = cliente.post("/api/descripcion/verificar-vocabulario", headers=archivista,
                     json={"fondo_id": str(fondo.id), "tipo": "agente", "valor": "Cabildo de Tunja"})
    assert r.status_code == 200, r.text
    [c] = r.json()
    assert c["id"] == str(alcaldia.id) and c["forma"] == "Cabildo de Tunja" and c["similitud"] == 1.0


def test_el_contexto_del_motor_incluye_la_entidad_citada_por_su_otra_forma(db, fondo, admin):
    from app.servicios import autoridad

    alcaldia = vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre="Alcaldía Municipal de Tunja",
                                 subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None,
                                 usuario_id=None)
    autoridad.agregar_nombre(db, alcaldia, tipo="otra", nombre="Cabildo de Tunja", idioma=None, regla=None,
                             vigencia_edtf=None, usuario_id=admin.id)
    db.commit()
    contexto = vocabulario.contexto_para_motor(db, fondo.id, "En sesión del Cabildo de Tunja se acordó el arreglo.")
    assert [c.id for c in contexto if c.tipo == "agente"] == [str(alcaldia.id)]


def test_corregir_un_elemento_isadg_queda_en_la_auditoria(cliente, db, fondo, archivista, monkeypatch):
    from app.models.auditoria import RegistroAuditoria
    from app.servicios import motor

    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    espacio = iniciar(cliente, archivista, [documento(db, fondo, "acta.pdf", OFICIO).id])
    recurso_id = cliente.post("/api/descripcion/publicar", headers=archivista, json={
        "trabajo_id": espacio["trabajo_id"], "titulo": "Acta", "isadg": {"organizacion": "Cronológica."}}).json()["id"]
    trabajo = cliente.post(f"/api/descripcion/registros/{recurso_id}/reabrir", headers=archivista).json()["trabajo_id"]
    r = cliente.patch(f"/api/descripcion/{recurso_id}", headers=archivista, json={
        "trabajo_id": trabajo, "isadg": {"organizacion": "Por asunto.", "nota_archivero": "Revisada."}})
    assert r.status_code == 200, r.text
    [ev] = db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "descripcion_editada")).all()
    assert ev.valor_anterior["organizacion"] == "Cronológica." and ev.valor_nuevo["organizacion"] == "Por asunto."
    assert ev.valor_nuevo["nota_archivero"] == "Revisada."
