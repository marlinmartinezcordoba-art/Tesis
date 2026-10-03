"""
Pruebas del Módulo 3, versión 2 (sección 11 del prompt actualizado): ficha
de agente ISAAR-CPF en cuatro áreas, nivel de detalle, grupo, identificadores
con esquema, mecanismo con versión, hitos institucionales, ficha ampliada de
lugar, árbol de funciones SKOS sin ciclos, sub-actividades, jerarquía de
mandatos y los vínculos que se declaran desde vocabularios.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import EntidadVocabulario, Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import vocabulario
from tests.conftest import crear_usuario, ingresar
from tests.test_vocabularios import documento_con, entidad


@pytest.fixture()
def fondo(db, admin):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Concejo Municipal de Tunja")
    f.fondo_id = f.id
    db.add(f)
    db.commit()
    return f


@pytest.fixture()
def archivista(cliente, db):
    crear_usuario(db, "catalina@correo.com", "archivista", nombre="Catalina Torres")
    return ingresar(cliente, "catalina@correo.com")


def ficha(cliente, cab, e):
    r = cliente.get(f"/api/vocabulario/{e.id}", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def eventos(db, accion, entidad_id=None):
    q = select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
    if entidad_id:
        q = q.where(RegistroAuditoria.entidad_id == str(entidad_id))
    return db.scalars(q).all()


def vincular(cliente, cab, e, tipo, con, con_tipo="entidad_vocabulario", **extra):
    return cliente.post(f"/api/vocabulario/{e.id}/vinculos", headers=cab,
                        json={"tipo": tipo, "con_id": str(con.id), "con_tipo": con_tipo, **extra})


# --- Ficha de agente: cuatro áreas -----------------------------------------------------------------


def test_ficha_de_agente_guarda_sus_cuatro_areas_con_existencia_abierta(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Secretaría de Gobierno de Tunja")
    r = cliente.patch(f"/api/vocabulario/{a.id}", headers=archivista, json={
        "existencia_edtf": "1948/", "historia": "Creada por el Acuerdo 12 de 1948.", "estatuto_juridico": "publica",
        "estructura": "Despacho y dos inspecciones.", "contexto_general": "Posguerra del 9 de abril.",
        "fuentes": "Gaceta municipal, 1948."})
    assert r.status_code == 200, r.text
    f = r.json()["ficha"]
    # Área de descripción, con la fecha abierta hacia adelante.
    assert f["campos"]["existencia_edtf"] == "1948/" and f["existencia_legible"] == "desde 1948 (fin desconocido)"
    db.expire_all()
    e = db.get(EntidadVocabulario, a.id)
    assert e.existencia_inicio.isoformat() == "1948-01-01" and e.existencia_fin is None
    # Identificación: formas del nombre e identificadores.
    assert cliente.post(f"/api/vocabulario/{a.id}/nombres", headers=archivista,
                        json={"tipo": "otra", "nombre": "Secretaría de Gobierno"}).status_code == 201
    assert cliente.post(f"/api/vocabulario/{a.id}/identificadores", headers=archivista,
                        json={"esquema": "interno", "valor": "SG-01"}).status_code == 201
    # Relaciones (área 3) y control (área 4).
    alcaldia = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    assert vincular(cliente, archivista, alcaldia, "subordinado", a).status_code == 201
    f = ficha(cliente, archivista, a)["ficha"]
    assert [n["nombre"] for n in f["nombres"]] == ["Secretaría de Gobierno"]
    assert f["identificadores"][0]["esquema"] == "interno" and f["identificadores"][0]["externo"] is False
    assert [v["etiqueta"] for v in f["vinculos"]] == ["está o estuvo subordinado a"]
    assert f["control"]["reglas"].startswith("ISAAR (CPF), 2.ª edición")
    assert f["control"]["nivel_detalle"] == "completo"
    # Las fechas de control salen de auditoría, nunca de un campo capturado a mano.
    assert f["control"]["revisada_en"] is not None
    assert cliente.patch(f"/api/vocabulario/{a.id}", headers=archivista,
                         json={"revisada_en": "2020-01-01"}).status_code == 422


def test_el_nombre_autorizado_no_se_cambia_desde_vocabularios(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    r = cliente.patch(f"/api/vocabulario/{a.id}", headers=archivista, json={"nombre": "Otra cosa"})
    assert r.status_code == 422 and "verifica contra el vocabulario" in r.json()["detail"]


def test_nivel_de_detalle_pasa_a_completo_y_el_filtro_lo_respeta(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    b = entidad(db, fondo, "Concejo Municipal de Tunja")
    assert db.get(EntidadVocabulario, a.id).nivel_detalle == "minimo"
    # Un campo que no es del área de descripción no cambia el nivel.
    cliente.patch(f"/api/vocabulario/{a.id}", headers=archivista, json={"fuentes": "Gaceta"})
    db.expire_all()
    assert db.get(EntidadVocabulario, a.id).nivel_detalle == "minimo"
    cliente.patch(f"/api/vocabulario/{a.id}", headers=archivista, json={"historia": "Primera alcaldía del distrito."})
    db.expire_all()
    assert db.get(EntidadVocabulario, a.id).nivel_detalle == "completo"
    params = {"fondo_id": str(fondo.id), "clase": "agente"}
    completos = cliente.get("/api/vocabulario", headers=archivista, params={**params, "nivel_detalle": "completo"}).json()
    minimos = cliente.get("/api/vocabulario", headers=archivista, params={**params, "nivel_detalle": "minimo"}).json()
    assert [e["id"] for e in completos] == [str(a.id)] and [e["id"] for e in minimos] == [str(b.id)]
    # El cambio de nivel queda en auditoría con el valor anterior y el nuevo.
    [ev] = [x for x in eventos(db, "entidad_enriquecida", a.id) if "historia" in (x.valor_nuevo or {})]
    assert ev.valor_anterior["nivel_detalle"] == "minimo" and ev.valor_nuevo["nivel_detalle"] == "completo"
    # Al vaciar el área de descripción vuelve a mínimo.
    cliente.patch(f"/api/vocabulario/{a.id}", headers=archivista, json={"historia": ""})
    db.expire_all()
    assert db.get(EntidadVocabulario, a.id).nivel_detalle == "minimo"


def test_relacion_entre_agentes_es_una_fila_con_su_inversa_fecha_y_nota(cliente, db, fondo, archivista):
    junta = entidad(db, fondo, "Junta de Ornato y Mejoras")
    secretaria = entidad(db, fondo, "Secretaría de Obras Públicas")
    r = vincular(cliente, archivista, junta, "sucesor", secretaria, fecha_edtf="1952", nota="Asumió sus funciones.")
    assert r.status_code == 201, r.text
    [desde_junta] = [v for v in r.json()["ficha"]["vinculos"] if v["vinculo"] == "sucesor"]
    assert desde_junta["etiqueta"] == "tiene como sucesor a" and desde_junta["propiedad_rico"] == "rico:hasSuccessor"
    assert desde_junta["codigo_cm"] == "RiC-R016"
    assert desde_junta["vigencia_legible"] == "1952" and desde_junta["nota"] == "Asumió sus funciones."
    [desde_secretaria] = [v for v in ficha(cliente, archivista, secretaria)["ficha"]["vinculos"] if v["vinculo"] == "sucesor"]
    assert desde_secretaria["etiqueta"] == "es sucesor de" and desde_secretaria["propiedad_rico"] == "rico:isSuccessorOf"
    assert desde_secretaria["codigo_cm"] == "RiC-R016i"
    assert desde_secretaria["relacion_id"] == desde_junta["relacion_id"]  # una sola fila
    assert db.scalar(select(Relacion).where(Relacion.codigo_ric == "has_successor")).fecha_edtf == "1952"
    # Sin ciclos en la sucesión ni en la subordinación.
    assert vincular(cliente, archivista, secretaria, "sucesor", junta).status_code == 422
    # La asociativa (R044) es simétrica: no se repite al revés.
    assert vincular(cliente, archivista, junta, "asociado", secretaria).status_code == 201
    assert vincular(cliente, archivista, secretaria, "asociado", junta).status_code == 422


def test_jerarquia_entre_cargos_usa_la_misma_relacion(cliente, db, fondo, archivista):
    alcalde = entidad(db, fondo, "Alcalde de Tunja", subtipo="cargo")
    secretario = entidad(db, fondo, "Secretario de Gobierno", subtipo="cargo")
    assert vincular(cliente, archivista, alcalde, "subordinado", secretario).status_code == 201
    [v] = ficha(cliente, archivista, secretario)["ficha"]["vinculos"]
    assert v["codigo_ric"] == "has_or_had_subordinate" and v["propiedad_rico"] == "rico:isOrWasSubordinateTo"


def test_anular_un_vinculo_no_lo_borra(cliente, db, fondo, archivista):
    a, b = entidad(db, fondo, "Alcaldía de Tunja"), entidad(db, fondo, "Personería de Tunja")
    rel = vincular(cliente, archivista, a, "asociado", b).json()["ficha"]["vinculos"][0]["relacion_id"]
    r = cliente.post(f"/api/vocabulario/{b.id}/vinculos/{rel}/anular", headers=archivista)
    assert r.status_code == 200 and r.json()["ficha"]["vinculos"] == []
    fila = db.get(Relacion, uuid.UUID(rel))
    assert fila.estado == "anulada" and fila.anulada_en is not None
    assert len(eventos(db, "vinculo_anulado", b.id)) == 1


# --- Subtipos, identificadores, mecanismo -------------------------------------------------------------


def test_agente_grupo_se_guarda_lista_y_filtra(cliente, db, fondo, archivista):
    g = entidad(db, fondo, "Junta de Festejos del Cuarto Centenario", subtipo="grupo")
    entidad(db, fondo, "Alcaldía de Tunja")
    lista = cliente.get("/api/vocabulario", headers=archivista, params={"fondo_id": str(fondo.id), "clase": "agente"}).json()
    assert {e["subtipo"] for e in lista} == {"grupo", "entidad_corporativa"}
    assert ficha(cliente, archivista, g)["ficha"]["clase_rico"] == "rico:Group"


def test_identificador_externo_conserva_su_esquema_y_se_distingue_del_interno(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Gustavo Rojas Pinilla", subtipo="persona")
    assert cliente.post(f"/api/vocabulario/{a.id}/identificadores", headers=archivista,
                        json={"esquema": "wikidata", "valor": "Q318229"}).status_code == 201
    assert cliente.post(f"/api/vocabulario/{a.id}/identificadores", headers=archivista,
                        json={"esquema": "interno", "valor": "AGT-0007"}).status_code == 201
    ids = {i["esquema"]: i for i in ficha(cliente, archivista, a)["ficha"]["identificadores"]}
    assert ids["wikidata"]["externo"] is True and ids["wikidata"]["uri"] == "http://www.wikidata.org/entity/Q318229"
    assert ids["interno"]["externo"] is False and ids["interno"]["uri"] is None
    # Validación de forma y sin repetir.
    assert cliente.post(f"/api/vocabulario/{a.id}/identificadores", headers=archivista,
                        json={"esquema": "wikidata", "valor": "318229"}).status_code == 422
    assert cliente.post(f"/api/vocabulario/{a.id}/identificadores", headers=archivista,
                        json={"esquema": "wikidata", "valor": "Q318229"}).status_code == 422
    assert cliente.post(f"/api/vocabulario/{a.id}/identificadores", headers=archivista,
                        json={"esquema": "doi", "valor": "x"}).status_code == 422


def test_mecanismo_guarda_su_version_y_se_reutiliza(cliente, db, fondo, archivista):
    gs = vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="Ghostscript", version="10.05.1")
    db.commit()
    otra_vez = vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="Ghostscript", version="10.05.1")
    assert otra_vez.id == gs.id  # nunca un registro duplicado
    nueva = vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="Ghostscript", version="10.06.0")
    db.commit()
    assert nueva.id != gs.id  # otra versión es otro mecanismo
    f = ficha(cliente, archivista, gs)
    assert f["entidad"]["version"] == "10.05.1" and f["ficha"]["clase_rico"] == "rico:Mechanism"
    assert f["ficha"]["falta_version"] is False
    # La versión es obligatoria: no se puede dejar vacía.
    assert cliente.patch(f"/api/vocabulario/{gs.id}", headers=archivista, json={"version": ""}).status_code == 422
    # Dos versiones de un mismo programa no se sugieren para fusión.
    assert vocabulario.detectar_candidatos(db, fondo.id) == 0


def test_mecanismo_sin_version_queda_marcado(cliente, db, fondo, archivista):
    m = entidad(db, fondo, "Motor de análisis", subtipo="mecanismo")
    assert ficha(cliente, archivista, m)["ficha"]["falta_version"] is True


# --- Línea de tiempo institucional (rico:Event) -------------------------------------------------------


def test_hitos_se_guardan_con_su_fecha_y_se_listan_cronologicamente(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Archivo Histórico de Tunja")
    for tipo, desc, fecha in (("traslado", "Traslado a la casa del Fundador", "1975~"),
                              ("creacion", "Creación por el Acuerdo 3", "1948-03-12"),
                              ("reforma", "Pasa a depender de la Secretaría de Cultura", "196X")):
        assert cliente.post(f"/api/vocabulario/{a.id}/hitos", headers=archivista,
                            json={"tipo": tipo, "descripcion": desc, "edtf": fecha}).status_code == 201
    hitos = ficha(cliente, archivista, a)["ficha"]["hitos"]
    assert [h["tipo"] for h in hitos] == ["creacion", "reforma", "traslado"]
    assert hitos[0]["fecha_legible"] == "12 de marzo de 1948" and hitos[2]["fecha_legible"] == "c. 1975"
    assert hitos[0]["clase_rico"] == "rico:Event" and hitos[0]["propiedad_rico"] == "rico:affectsOrAffected"
    # Un hito cuenta como dato del área de descripción.
    db.expire_all()
    assert db.get(EntidadVocabulario, a.id).nivel_detalle == "completo"
    assert cliente.post(f"/api/vocabulario/{a.id}/hitos", headers=archivista,
                        json={"tipo": "otro", "descripcion": "x", "edtf": "1948-02-30"}).status_code == 422


# --- Lugar ampliado ------------------------------------------------------------------------------------


def test_lugar_con_coordenadas_tipo_superior_y_nombres_historicos(cliente, db, fondo, archivista):
    boyaca = entidad(db, fondo, "Boyacá", clase="lugar")
    tunja = entidad(db, fondo, "Tunja", clase="lugar")
    r = cliente.patch(f"/api/vocabulario/{tunja.id}", headers=archivista,
                      json={"latitud": 5.5353, "longitud": -73.3678, "tipo_lugar": "municipio"})
    assert r.status_code == 200, r.text
    assert vincular(cliente, archivista, tunja, "lugar_superior", boyaca).status_code == 201
    for nombre, vigencia in (("Hunza", "/1539"), ("Muy Noble y Muy Leal Ciudad de Tunja", "1541/1819")):
        assert cliente.post(f"/api/vocabulario/{tunja.id}/nombres", headers=archivista,
                            json={"tipo": "historica", "nombre": nombre, "vigencia_edtf": vigencia}).status_code == 201
    f = ficha(cliente, archivista, tunja)["ficha"]
    assert f["campos"]["latitud"] == 5.5353 and f["campos"]["tipo_lugar"] == "municipio"
    [sup] = [v for v in f["vinculos"] if v["vinculo"] == "lugar_superior"]
    assert sup["etiqueta"] == "está dentro de" and sup["con"]["nombre"] == "Boyacá"
    assert sup["propiedad_rico"] == "rico:isOrWasContainedBy" and sup["codigo_cm"] == "RiC-R007i"
    assert [(n["nombre"], n["vigencia_legible"]) for n in f["nombres"]] == [
        ("Hunza", "hasta 1539 (inicio desconocido)"), ("Muy Noble y Muy Leal Ciudad de Tunja", "de 1541 a 1819")]
    # Desde el superior se ve lo que contiene.
    assert [c["con"]["nombre"] for c in ficha(cliente, archivista, boyaca)["ficha"]["contiene"]] == ["Tunja"]
    # Un solo superior directo, sin ciclos, coordenadas válidas y juntas.
    pais = entidad(db, fondo, "Colombia", clase="lugar")
    assert vincular(cliente, archivista, tunja, "lugar_superior", pais).status_code == 422
    assert vincular(cliente, archivista, boyaca, "lugar_superior", tunja).status_code == 422
    assert cliente.patch(f"/api/vocabulario/{pais.id}", headers=archivista, json={"latitud": 95}).status_code == 422
    assert cliente.patch(f"/api/vocabulario/{pais.id}", headers=archivista, json={"latitud": 4.6}).status_code == 422
    assert cliente.patch(f"/api/vocabulario/{pais.id}", headers=archivista, json={"tipo_lugar": "galaxia"}).status_code == 422


# --- Árbol de funciones (SKOS) --------------------------------------------------------------------------


def test_arbol_de_funciones_se_arma_con_skos_y_no_admite_ciclos(cliente, db, fondo, archivista):
    gobierno = entidad(db, fondo, "Gobierno municipal", clase="tipo_actividad")
    policia = entidad(db, fondo, "Policía local", clase="tipo_actividad")
    permisos = entidad(db, fondo, "Permisos de espectáculos", clase="tipo_actividad")
    hacienda = entidad(db, fondo, "Hacienda", clase="tipo_actividad")
    for hijo, padre in ((policia, gobierno), (permisos, policia)):
        r = cliente.put(f"/api/vocabulario/{hijo.id}/concepto-superior", headers=archivista,
                        json={"superior_id": str(padre.id)})
        assert r.status_code == 200, r.text
    arbol = cliente.get("/api/vocabulario/funciones/arbol", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert [n["nombre"] for n in arbol] == ["Gobierno municipal", "Hacienda"]
    assert arbol[0]["especificos"][0]["nombre"] == "Policía local"
    assert arbol[0]["especificos"][0]["especificos"][0]["nombre"] == "Permisos de espectáculos"  # tres niveles
    # Ciclo directo e indirecto: rechazados.
    for x, y in ((gobierno, permisos), (gobierno, gobierno)):
        assert cliente.put(f"/api/vocabulario/{x.id}/concepto-superior", headers=archivista,
                           json={"superior_id": str(y.id)}).status_code == 422
    f = ficha(cliente, archivista, policia)["ficha"]["skos"]
    assert f["broader"]["nombre"] == "Gobierno municipal" and [n["nombre"] for n in f["narrower"]] == ["Permisos de espectáculos"]
    # La jerarquía SKOS no es una relación de RiC-O: no deja filas en «relaciones».
    assert db.scalar(select(Relacion).where(Relacion.origen_id == policia.id)) is None
    assert len(eventos(db, "concepto_superior_cambiado", policia.id)) == 1
    # Solo los tipos de actividad forman el árbol.
    agente = entidad(db, fondo, "Alcaldía")
    assert cliente.put(f"/api/vocabulario/{agente.id}/concepto-superior", headers=archivista,
                       json={"superior_id": str(gobierno.id)}).status_code == 422
    assert hacienda.id  # queda como función de primer nivel


def test_tipo_de_actividad_con_su_serie_documental(cliente, db, fondo, archivista):
    policia = entidad(db, fondo, "Policía local", clase="tipo_actividad")
    serie = RecursoDocumental(id=uuid.uuid4(), nivel="serie", titulo="Permisos", fondo_id=fondo.id, incluido_en_id=fondo.id)
    expediente = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo="Permisos 1948", fondo_id=fondo.id,
                                   incluido_en_id=serie.id)
    db.add_all([serie, expediente])
    db.commit()
    assert vincular(cliente, archivista, policia, "serie_producida", serie, "recurso_documental").status_code == 201
    [v] = ficha(cliente, archivista, policia)["ficha"]["vinculos"]
    assert v["con"]["nombre"] == "Permisos" and v["propiedad_rico"] == "rico:isRelatedTo" and v["estado_mapeo"] == "general"
    arbol = cliente.get("/api/vocabulario/funciones/arbol", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert arbol[0]["series"] == [{"id": str(serie.id), "titulo": "Permisos", "nivel": "serie"}]
    # Solo series o subseries, nunca un expediente.
    assert vincular(cliente, archivista, policia, "serie_producida", expediente, "recurso_documental").status_code == 422


# --- Actividades y mandatos -------------------------------------------------------------------------------


def test_sub_actividades_se_listan_y_no_se_confunden_con_skos(cliente, db, fondo, archivista):
    tramite = entidad(db, fondo, "Registro civil de 1948", clase="actividad")
    diligencia = entidad(db, fondo, "Inscripción de nacimientos de 1948", clase="actividad")
    assert vincular(cliente, archivista, diligencia, "actividad_mayor", tramite).status_code == 201
    mayor = ficha(cliente, archivista, diligencia)["ficha"]["vinculos"]
    assert [(v["etiqueta"], v["con"]["nombre"], v["propiedad_rico"]) for v in mayor] == [
        ("es sub-actividad de", "Registro civil de 1948", "rico:isDirectSubeventOf")]
    menores = ficha(cliente, archivista, tramite)["ficha"]["vinculos"]
    assert [(v["etiqueta"], v["con"]["nombre"]) for v in menores] == [("tiene como sub-actividad a", "Inscripción de nacimientos de 1948")]
    assert db.get(EntidadVocabulario, diligencia.id).concepto_superior_id is None  # no es SKOS
    # Una sub-actividad tiene una sola actividad mayor, sin ciclos.
    otra = entidad(db, fondo, "Censo de 1948", clase="actividad")
    assert vincular(cliente, archivista, diligencia, "actividad_mayor", otra).status_code == 422
    assert vincular(cliente, archivista, tramite, "actividad_mayor", diligencia).status_code == 422
    # Solo entre actividades.
    tipo = entidad(db, fondo, "Registro civil", clase="tipo_actividad")
    assert vincular(cliente, archivista, tipo, "actividad_mayor", tramite).status_code == 422


def test_mandato_derivado_se_navega_en_ambos_sentidos_sin_ciclos(cliente, db, fondo, archivista):
    ley = entidad(db, fondo, "Ley 4 de 1913", clase="mandato")
    decreto = entidad(db, fondo, "Decreto 1333 de 1986", clase="mandato")
    resolucion = entidad(db, fondo, "Resolución 22 de 1987", clase="mandato")
    assert vincular(cliente, archivista, decreto, "mandato_superior", ley).status_code == 201
    assert vincular(cliente, archivista, resolucion, "mandato_superior", decreto).status_code == 201
    vinculos = {v["con"]["nombre"]: v["etiqueta"] for v in ficha(cliente, archivista, decreto)["ficha"]["vinculos"]}
    assert vinculos == {"Ley 4 de 1913": "desarrolla o deriva de", "Resolución 22 de 1987": "es norma superior de"}
    assert vincular(cliente, archivista, ley, "mandato_superior", resolucion).status_code == 422  # ciclo
    fila = db.scalar(select(Relacion).where(Relacion.destino_id == decreto.id, Relacion.rol == "jerarquia_normativa"))
    assert fila.codigo_ric == "regulates_or_regulated" and fila.origen_id == ley.id


def test_mandato_que_crea_un_agente_y_entidad_que_lo_expidio(cliente, db, fondo, archivista):
    acuerdo = entidad(db, fondo, "Acuerdo 12 de 1948", clase="mandato")
    secretaria = entidad(db, fondo, "Secretaría de Gobierno")
    concejo = entidad(db, fondo, "Concejo Municipal de Tunja")
    assert vincular(cliente, archivista, secretaria, "creado_por", acuerdo).status_code == 201
    assert vincular(cliente, archivista, acuerdo, "expedido_por", concejo).status_code == 201
    v = {x["vinculo"]: x for x in ficha(cliente, archivista, acuerdo)["ficha"]["vinculos"]}
    assert v["creado_por"]["etiqueta"] == "crea o establece a" and v["creado_por"]["propiedad_rico"] == "rico:authorizes"
    assert v["expedido_por"]["etiqueta"] == "fue expedido por" and v["expedido_por"]["propiedad_rico"] == "rico:issuedBy"
    [desde_agente] = ficha(cliente, archivista, secretaria)["ficha"]["vinculos"]
    assert desde_agente["etiqueta"] == "fue creado o establecido por"
    # Es distinto de regular una actividad: queda con su rol propio.
    fila = db.scalar(select(Relacion).where(Relacion.codigo_ric == "authorizes"))
    assert fila.rol == "creacion" and fila.origen_id == acuerdo.id and fila.destino_id == secretaria.id


def test_mandato_que_crea_una_competencia(cliente, db, fondo, archivista):
    ley = entidad(db, fondo, "Ley 92 de 1938", clase="mandato")
    registro = entidad(db, fondo, "Registro civil", clase="tipo_actividad")
    assert vincular(cliente, archivista, registro, "competencia_creada_por", ley).status_code == 201
    [v] = ficha(cliente, archivista, registro)["ficha"]["vinculos"]
    assert v["etiqueta"] == "es una competencia creada por" and v["propiedad_rico"] == "rico:isOrWasRegulatedBy"


def test_no_se_vincula_entre_fondos_ni_con_una_fusionada(cliente, db, fondo, archivista, admin):
    otro = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Otro fondo")
    otro.fondo_id = otro.id
    db.add(otro)
    db.commit()
    a = entidad(db, fondo, "Alcaldía de Tunja")
    b = entidad(db, otro, "Alcaldía de Paipa")
    assert vincular(cliente, archivista, a, "asociado", b).status_code == 422
    c = entidad(db, fondo, "Alcaldia de Tunja.")
    vocabulario.fusionar(db, definitiva=a, absorbida=c, usuario_id=None)
    db.commit()
    d = entidad(db, fondo, "Personería de Tunja")
    assert vincular(cliente, archivista, d, "asociado", c).status_code == 422
    assert cliente.patch(f"/api/vocabulario/{c.id}", headers=archivista, json={"historia": "x"}).status_code == 409


# --- Fusión con la ficha completa ---------------------------------------------------------------------------


def test_fusion_lleva_la_ficha_a_la_definitiva_y_queda_en_auditoria(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    b = entidad(db, fondo, "Alcaldía de Tunja")
    secretaria = entidad(db, fondo, "Secretaría de Gobierno")
    documento_con(db, fondo, "Oficio 114", a)
    cliente.post(f"/api/vocabulario/{b.id}/hitos", headers=archivista,
                 json={"tipo": "creacion", "descripcion": "Creación", "edtf": "1948"})
    cliente.post(f"/api/vocabulario/{b.id}/identificadores", headers=archivista, json={"esquema": "interno", "valor": "AL-1"})
    # b es superior de la secretaría; a es subordinada de b (al fusionar quedaría a → a: se anula).
    vincular(cliente, archivista, b, "subordinado", secretaria)
    vincular(cliente, archivista, b, "subordinado", a)
    r = cliente.post("/api/vocabulario/fusionar", headers=archivista,
                     json={"definitiva_id": str(a.id), "absorbida_id": str(b.id)})
    assert r.status_code == 200, r.text
    f = ficha(cliente, archivista, a)["ficha"]
    assert [h["descripcion"] for h in f["hitos"]] == ["Creación"]
    assert [i["valor"] for i in f["identificadores"]] == ["AL-1"]
    assert [n["nombre"] for n in f["nombres"]] == ["Alcaldía de Tunja"]  # el nombre absorbido, como otra forma
    assert [v["con"]["nombre"] for v in f["vinculos"]] == ["Secretaría de Gobierno"]
    assert f["control"]["nivel_detalle"] == "completo"
    assert db.scalar(select(Relacion).where(Relacion.origen_id == a.id, Relacion.destino_id == a.id)).estado == "anulada"
    [ev] = eventos(db, "fusion_vocabulario")
    assert ev.valor_nuevo["registros_ficha_movidos"] >= 3


# --- Permisos ------------------------------------------------------------------------------------------------


def test_sin_permiso_de_escritura_no_se_enriquece(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Alcaldía de Tunja")
    crear_usuario(db, "consulta@correo.com", "consulta")
    consulta = ingresar(cliente, "consulta@correo.com")
    crear_usuario(db, "revisor@correo.com", "revisor")
    revisor = ingresar(cliente, "revisor@correo.com")
    for cab in (consulta, revisor):
        assert cliente.patch(f"/api/vocabulario/{a.id}", headers=cab, json={"historia": "x"}).status_code == 403
        assert cliente.post(f"/api/vocabulario/{a.id}/hitos", headers=cab,
                            json={"tipo": "otro", "descripcion": "x", "edtf": "1948"}).status_code == 403
    assert cliente.get(f"/api/vocabulario/{a.id}", headers=revisor).status_code == 200


def test_anular_una_forma_del_nombre_o_un_hito_no_los_borra(cliente, db, fondo, archivista):
    from app.models.descripcion import Hito, NombreEntidad

    a = entidad(db, fondo, "Alcaldía de Tunja")
    f = cliente.post(f"/api/vocabulario/{a.id}/nombres", headers=archivista,
                     json={"tipo": "otra", "nombre": "Alcaldía"}).json()["ficha"]
    nid = f["nombres"][0]["id"]
    hid = cliente.post(f"/api/vocabulario/{a.id}/hitos", headers=archivista,
                       json={"tipo": "creacion", "descripcion": "Creación", "edtf": "1948"}).json()["ficha"]["hitos"][0]["id"]
    assert cliente.post(f"/api/vocabulario/{a.id}/registros/nombre/{nid}/anular", headers=archivista).status_code == 200
    r = cliente.post(f"/api/vocabulario/{a.id}/registros/hito/{hid}/anular", headers=archivista)
    assert r.status_code == 200 and r.json()["ficha"]["nombres"] == [] and r.json()["ficha"]["hitos"] == []
    assert db.get(NombreEntidad, uuid.UUID(nid)).estado == "anulado" and db.get(Hito, uuid.UUID(hid)).estado == "anulado"
    # Sin hitos ni campos de descripción, la ficha vuelve a mínima.
    db.expire_all()
    assert db.get(EntidadVocabulario, a.id).nivel_detalle == "minimo"
    assert cliente.post(f"/api/vocabulario/{a.id}/registros/hito/{hid}/anular", headers=archivista).status_code == 422
