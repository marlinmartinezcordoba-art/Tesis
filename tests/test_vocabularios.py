"""
Pruebas del Módulo 3 · Vocabularios y control de autoridad (sección 9
del prompt), contra PostgreSQL real con pg_trgm.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import EntidadVocabulario, Relacion, SugerenciaFusion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import vocabulario
from app.db.base import ahora
from tests.conftest import crear_usuario, ingresar


@pytest.fixture()
def fondo(db, admin):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Correspondencia municipal")
    f.fondo_id = f.id
    db.add(f)
    db.commit()
    return f


@pytest.fixture()
def archivista(cliente, db):
    crear_usuario(db, "catalina@correo.com", "archivista", nombre="Catalina Torres")
    return ingresar(cliente, "catalina@correo.com")


def entidad(db, fondo, nombre, clase="agente", subtipo="entidad_corporativa", admin=None):
    e = vocabulario.crear(db, fondo_id=fondo.id, clase=clase, nombre=nombre, subtipo=subtipo if clase == "agente" else None,
                          origen="persona", confianza=None, motor=None, usuario_id=None)
    db.commit()
    return e


def documento_con(db, fondo, titulo, *entidades, forma=None):
    """Una descripción publicada conectada a las entidades dadas."""
    r = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo=titulo, fondo_id=fondo.id,
                          incluido_en_id=fondo.id, publicado_en=ahora(), forma_documental_id=forma.id if forma else None)
    db.add(r)
    db.flush()
    for e in entidades:
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=r.id, destino_tipo="entidad_vocabulario", destino_id=e.id,
                        tipo_relacion="procedencia", codigo_ric="has_creator", rol="productor", origen="persona"))
    db.commit()
    return r


def eventos(db, accion):
    return db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)).all()


# --- Verificación ------------------------------------------------------------------------------


def test_verificacion_detecta_parecidos_sin_falsos_positivos(cliente, db, fondo, archivista):
    entidad(db, fondo, "Alcaldía Municipal de Tunja")
    entidad(db, fondo, "Gobernación de Boyacá")
    entidad(db, fondo, "Juan Pérez", subtipo="persona")

    def v(valor, tipo="agente"):
        return [c["nombre"] for c in cliente.post("/api/vocabulario/verificar", headers=archivista,
                                                  json={"fondo_id": str(fondo.id), "tipo": tipo, "valor": valor}).json()]

    assert v("alcaldia municipal de tunja") == ["Alcaldía Municipal de Tunja"]
    assert v("Alcaldía de Tunja") == ["Alcaldía Municipal de Tunja"]
    assert v("Concejo Municipal de Sogamoso") == []
    assert v("Ministerio de Hacienda") == []
    assert v("Gobernación de Boyacá", tipo="lugar") == []  # solo dentro del mismo tipo


# --- Detección periódica ------------------------------------------------------------------------


def test_deteccion_sugiere_solo_pares_parecidos_y_poco_conectados(db, fondo):
    a = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    b = entidad(db, fondo, "Alcaldia municipal de Tunja.")
    c = entidad(db, fondo, "Gobernación de Boyacá")
    muy = entidad(db, fondo, "Concejo Municipal")
    muy2 = entidad(db, fondo, "Concejo Municipal de")
    for i in range(11):  # más de 10 conexiones: no es «poco conectada»
        documento_con(db, fondo, f"Acta {i}", muy)
    assert vocabulario.detectar_candidatos(db, fondo.id) == 1
    db.commit()
    [s] = db.scalars(select(SugerenciaFusion)).all()
    assert {s.entidad_a_id, s.entidad_b_id} == {a.id, b.id} and s.similitud >= 0.6 and s.estado == "pendiente"
    assert c.id not in (s.entidad_a_id, s.entidad_b_id) and muy2.id not in (s.entidad_a_id, s.entidad_b_id)
    # No se repite el mismo par en la siguiente búsqueda, y nada se fusionó.
    assert vocabulario.detectar_candidatos(db, fondo.id) == 0
    assert db.scalar(select(func.count()).select_from(EntidadVocabulario).where(EntidadVocabulario.estado == "fusionada")) == 0


def test_la_busqueda_periodica_respeta_el_intervalo(db, fondo, monkeypatch):
    entidad(db, fondo, "Alcaldía Municipal de Tunja")
    entidad(db, fondo, "Alcaldia municipal de Tunja.")
    assert vocabulario.deteccion_periodica(db) == 1
    assert vocabulario.deteccion_periodica(db) is None  # todavía no pasan 24 horas


# --- Fusión ----------------------------------------------------------------------------------------


def test_aprobar_sugerencia_redirige_relaciones_marca_fusionada_y_audita(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    b = entidad(db, fondo, "Alcaldia municipal de Tunja.")
    d1 = documento_con(db, fondo, "Oficio 114", a)
    d2 = documento_con(db, fondo, "Oficio 115", a)
    d3 = documento_con(db, fondo, "Oficio 087", b)
    cliente.post("/api/vocabulario/detectar", headers=archivista, params={"fondo_id": str(fondo.id)})
    [s] = cliente.get("/api/vocabulario/sugerencias-fusion", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert {e["conexiones"] for e in s["entidades"]} == {2, 1}

    r = cliente.post(f"/api/vocabulario/sugerencias-fusion/{s['id']}/aprobar", headers=archivista, json={})
    assert r.status_code == 200 and r.json()["definitiva"] == str(a.id) and r.json()["relaciones_movidas"] == 1
    db.expire_all()
    assert db.get(EntidadVocabulario, b.id).estado == "fusionada"
    assert db.get(EntidadVocabulario, b.id).fusionada_en_id == a.id
    relacion = db.scalar(select(Relacion).where(Relacion.origen_id == d3.id))
    assert relacion.destino_id == a.id and relacion.destino_original_id == b.id
    assert {d["titulo"] for d in cliente.get(f"/api/vocabulario/{a.id}", headers=archivista).json()["documentos"]} == {
        "Oficio 114", "Oficio 115", "Oficio 087"}
    [evento] = eventos(db, "fusion_vocabulario")
    assert evento.usuario_id is not None and evento.valor_nuevo["relaciones_movidas"] == 1
    assert evento.valor_anterior["absorbida"]["nombre"] == "Alcaldia municipal de Tunja."
    assert db.get(SugerenciaFusion, uuid.UUID(s["id"])).estado == "aprobada"
    assert d1 and d2
    # Una segunda aprobación (otra persona, mismo instante) no fusiona dos veces.
    assert cliente.post(f"/api/vocabulario/sugerencias-fusion/{s['id']}/aprobar", headers=archivista, json={}).status_code == 409
    assert len(eventos(db, "fusion_vocabulario")) == 1


def test_descartar_no_cambia_nada(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Alcaldía Municipal de Tunja")
    b = entidad(db, fondo, "Alcaldia municipal de Tunja.")
    documento_con(db, fondo, "Oficio 087", b)
    cliente.post("/api/vocabulario/detectar", headers=archivista, params={"fondo_id": str(fondo.id)})
    [s] = cliente.get("/api/vocabulario/sugerencias-fusion", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    antes = [(r.id, r.destino_id) for r in db.scalars(select(Relacion))]
    assert cliente.post(f"/api/vocabulario/sugerencias-fusion/{s['id']}/descartar", headers=archivista).status_code == 200
    db.expire_all()
    assert [(r.id, r.destino_id) for r in db.scalars(select(Relacion))] == antes
    assert db.get(EntidadVocabulario, a.id).estado == db.get(EntidadVocabulario, b.id).estado == "activa"
    assert eventos(db, "fusion_vocabulario") == []
    # Un par descartado no vuelve a sugerirse.
    assert cliente.post("/api/vocabulario/detectar", headers=archivista, params={"fondo_id": str(fondo.id)}).json()["nuevas"] == 0


def test_fusion_manual_igual_que_sugerencia(cliente, db, fondo, archivista):
    oficio = entidad(db, fondo, "Oficio", clase="forma_documental")
    oficio2 = entidad(db, fondo, "Oficios", clase="forma_documental")
    d = documento_con(db, fondo, "Oficio 114", forma=oficio2)
    r = cliente.post("/api/vocabulario/fusionar", headers=archivista,
                     json={"definitiva_id": str(oficio.id), "absorbida_id": str(oficio2.id)})
    assert r.status_code == 200 and r.json()["relaciones_movidas"] == 1
    db.expire_all()
    assert db.get(RecursoDocumental, d.id).forma_documental_id == oficio.id
    assert db.get(EntidadVocabulario, oficio2.id).estado == "fusionada"
    assert eventos(db, "fusion_vocabulario")[0].valor_nuevo["origen"] == "manual"
    # Entidades de tipos distintos no se fusionan.
    lugar = entidad(db, fondo, "Tunja", clase="lugar")
    assert cliente.post("/api/vocabulario/fusionar", headers=archivista,
                        json={"definitiva_id": str(oficio.id), "absorbida_id": str(lugar.id)}).status_code == 409


def test_fusionada_fuera_del_listado_pero_accesible(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Alcaldía Municipal")
    b = entidad(db, fondo, "Alcaldía Mpal.")
    oficio = documento_con(db, fondo, "Oficio antiguo", b)
    cliente.post("/api/vocabulario/fusionar", headers=archivista, json={"definitiva_id": str(a.id), "absorbida_id": str(b.id)})
    activos = cliente.get("/api/vocabulario", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert [e["nombre"] for e in activos] == ["Alcaldía Municipal"] and activos[0]["conexiones"] == 1
    fusionadas = cliente.get("/api/vocabulario", headers=archivista, params={"fondo_id": str(fondo.id), "estado": "fusionada"}).json()
    assert [e["nombre"] for e in fusionadas] == ["Alcaldía Mpal."] and fusionadas[0]["fusionada_en"]["nombre"] == "Alcaldía Municipal"
    detalle = cliente.get(f"/api/vocabulario/{b.id}", headers=archivista).json()
    assert detalle["entidad"]["estado"] == "fusionada"
    assert [d["titulo"] for d in detalle["documentos_historicos"]] == ["Oficio antiguo"]
    assert detalle["historial"][0]["relaciones_movidas"] == 1
    assert [x["nombre"] for x in cliente.get(f"/api/vocabulario/{a.id}", headers=archivista).json()["absorbidas"]] == ["Alcaldía Mpal."]
    # Desde la descripción del documento antiguo se llega a la entidad que citaba.
    agente = cliente.get(f"/api/descripcion/registros/{oficio.id}", headers=archivista).json()["entidades"][0]
    assert agente["valor"] == "Alcaldía Municipal" and agente["antes_de_fusion"] == {"id": str(b.id), "nombre": "Alcaldía Mpal."}
    # Nada se borró.
    assert db.get(EntidadVocabulario, b.id) is not None
    # Descripción ya no la ofrece para reutilizar, porque verificar solo mira activas.
    nombres = [c["nombre"] for c in cliente.post("/api/vocabulario/verificar", headers=archivista,
                                                  json={"fondo_id": str(fondo.id), "tipo": "agente", "valor": "Alcaldía Mpal."}).json()]
    assert "Alcaldía Mpal." not in nombres


def test_listado_filtra_busca_y_ordena(cliente, db, fondo, archivista):
    a = entidad(db, fondo, "Alcaldía Municipal")
    g = entidad(db, fondo, "Gobernador del Departamento", subtipo="cargo")
    entidad(db, fondo, "Boyacá", clase="lugar")
    for i in range(3):
        documento_con(db, fondo, f"Doc {i}", g)
    documento_con(db, fondo, "Doc x", a)

    def nombres(**p):
        return [e["nombre"] for e in cliente.get("/api/vocabulario", headers=archivista, params={"fondo_id": str(fondo.id), **p}).json()]

    assert nombres() == ["Gobernador del Departamento", "Alcaldía Municipal", "Boyacá"]
    assert nombres(orden="conexiones_asc") == ["Boyacá", "Alcaldía Municipal", "Gobernador del Departamento"]
    assert nombres(clase="lugar") == ["Boyacá"]
    assert nombres(q="alcaldia") == ["Alcaldía Municipal"]


# --- Permisos y auditoría ----------------------------------------------------------------------------


def test_ninguna_fusion_sin_permiso_ni_sin_auditoria(cliente, db, fondo):
    a = entidad(db, fondo, "Alcaldía Municipal")
    b = entidad(db, fondo, "Alcaldía Mpal.")
    crear_usuario(db, "julian@correo.com", "revisor")
    revisor = ingresar(cliente, "julian@correo.com")
    crear_usuario(db, "laura@correo.com", "consulta")
    consulta = ingresar(cliente, "laura@correo.com")
    datos = {"definitiva_id": str(a.id), "absorbida_id": str(b.id)}
    assert cliente.post("/api/vocabulario/fusionar", json=datos).status_code == 401
    assert cliente.post("/api/vocabulario/fusionar", headers=revisor, json=datos).status_code == 403
    assert cliente.post("/api/vocabulario/fusionar", headers=consulta, json=datos).status_code == 403
    assert cliente.get("/api/vocabulario", headers=revisor, params={"fondo_id": str(fondo.id)}).status_code == 200
    assert cliente.get("/api/vocabulario", headers=consulta, params={"fondo_id": str(fondo.id)}).status_code == 403
    entidad(db, fondo, "Gobernación de Boyacá")
    entidad(db, fondo, "Gobernacion de Boyaca")
    vocabulario.detectar_candidatos(db, fondo.id)
    db.commit()
    sug = db.scalar(select(SugerenciaFusion).where(SugerenciaFusion.estado == "pendiente"))
    for accion in ("aprobar", "descartar"):
        for quien in (revisor, consulta):
            assert cliente.post(f"/api/vocabulario/sugerencias-fusion/{sug.id}/{accion}", headers=quien, json={}).status_code == 403
    db.expire_all()
    assert db.get(EntidadVocabulario, b.id).estado == "activa"
    # Toda fusión que ocurre deja su registro de auditoría: una por una.
    crear_usuario(db, "cat@correo.com", "archivista")
    arch = ingresar(cliente, "cat@correo.com")
    fusionadas = 0
    for nombre in ("Alcaldía Mpal.", "Alcaldia Municipal", "ALCALDÍA MUNICIPAL"):
        x = db.scalar(select(EntidadVocabulario).where(EntidadVocabulario.nombre == nombre)) or entidad(db, fondo, nombre)
        assert cliente.post("/api/vocabulario/fusionar", headers=arch,
                            json={"definitiva_id": str(a.id), "absorbida_id": str(x.id)}).status_code == 200
        fusionadas += 1
    total_fusionadas = db.scalar(select(func.count()).select_from(EntidadVocabulario).where(EntidadVocabulario.estado == "fusionada"))
    assert total_fusionadas == fusionadas == len(eventos(db, "fusion_vocabulario"))


def test_parametros_de_deteccion_solo_administrador(cliente, archivista, cabeceras_admin):
    assert cliente.get("/api/vocabulario/parametros", headers=archivista).json() == {
        "similitud_pct": 60, "max_conexiones": 10, "horas_deteccion": 24}
    datos = {"similitud_pct": 70, "max_conexiones": 5, "horas_deteccion": 12}
    assert cliente.put("/api/vocabulario/parametros", headers=archivista, json=datos).status_code == 403
    assert cliente.put("/api/vocabulario/parametros", headers=cabeceras_admin, json=datos).json() == datos
    fuera = {"similitud_pct": 10, "max_conexiones": 5, "horas_deteccion": 12}
    assert cliente.put("/api/vocabulario/parametros", headers=cabeceras_admin, json=fuera).status_code == 422
    assert cliente.get("/api/vocabulario/parametros", headers=archivista).json() == datos
