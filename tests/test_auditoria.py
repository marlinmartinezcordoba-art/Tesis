"""
Pruebas del módulo transversal de auditoría (sección 10 del prompt) y la
prueba de integración de extremo a extremo (sección 11): un documento
recorre ingesta → descripción → vocabularios → instrumentos →
preservación, y cada paso comprometido queda exactamente una vez en la
auditoría, con quién, sobre qué y el antes y el después.
"""

import io
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from docx import Document
from sqlalchemy import select

from app.db.base import ahora
from app.main import app
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import EntidadVocabulario
from app.models.sesion import Sesion
from app.servicios import formato, motor, procesamiento, sesiones, trazabilidad, vocabulario
from app.servicios.auditoria import registrar
from tests import archivos
from tests.conftest import crear_usuario, ingresar
from tests.test_descripcion import OFICIO_114, RESPUESTA_UNO, MotorDePrueba, aceptar_todo

BOGOTA = ZoneInfo("America/Bogota")

# Las acciones que el prompt de cada módulo comprometió a dejar en auditoría.
COMPROMETIDAS = {
    "autenticacion": ["inicio_sesion", "cierre_sesion", "usuario_creado", "usuario_editado", "usuario_desactivado"],
    "sistema": ["fondo_registrado"],
    "ingesta": ["documento_cargado"],
    "descripcion": ["descripcion_publicada", "descripcion_editada", "decision_ia"],
    "vocabularios": ["fusion_vocabulario", "mecanismo_registrado"],
    "instrumentos": ["inventario_exportado", "guia_exportada", "rdf_exportado", "conformidad_rico_validada"],
    "preservacion": ["integridad_verificada", "migracion_aprobada", "migracion_completada", "segunda_copia_creada",
                     "paquete_exportado"],
    "auditoria": ["hallazgo_creado", "hallazgo_actualizado"],
}
# Cuántas veces, cuando no es una: las decisiones (una por propuesta del
# motor, más título y alcance), los mecanismos (Siegfried, RICORA, el motor
# y Ghostscript, cada uno una sola vez) y la segunda copia (de la original y
# de la migrada).
VECES = {"inicio_sesion": 2, "decision_ia": len(RESPUESTA_UNO["entidades"]) + 2, "mecanismo_registrado": 4,
         "segunda_copia_creada": 2}


def eventos(db, accion=None, **filtros):
    q = select(RegistroAuditoria)
    if accion:
        q = q.where(RegistroAuditoria.accion == accion)
    for campo, valor in filtros.items():
        q = q.where(getattr(RegistroAuditoria, campo) == valor)
    return db.scalars(q.order_by(RegistroAuditoria.id)).all()


# --- De extremo a extremo -----------------------------------------------------------------------


def test_ciclo_completo_de_los_siete_modulos_queda_en_auditoria(cliente, db, admin, buzon, monkeypatch):
    formato.herramienta.cache_clear()
    formato.herramienta()  # herramientas reales, como en producción
    inicio_prueba = max(e.id for e in eventos(db)) if eventos(db) else 0

    # Autenticación y sistema: la administradora registra el fondo y el equipo.
    adm = ingresar(cliente, admin.correo)
    fondo_id = cliente.post("/api/fondos", headers=adm, json={"titulo": "Correspondencia municipal"}).json()["id"]
    nueva = cliente.post("/api/auth/usuarios", headers=adm,
                         json={"nombre": "Julián Rojas", "correo": "julian@correo.com", "rol": "revisor"}).json()
    cliente.patch(f"/api/auth/usuarios/{nueva['usuario']['id']}", headers=adm, json={"rol": "consulta"})
    cliente.patch(f"/api/auth/usuarios/{nueva['usuario']['id']}", headers=adm, json={"activo": False})
    catalina = crear_usuario(db, "catalina@correo.com", "archivista", nombre="Catalina Torres")
    arch = ingresar(cliente, "catalina@correo.com")

    # 1. Ingesta: un oficio real, procesado con Siegfried.
    r = cliente.post("/api/ingesta/cargar", headers=arch, data={"fondo_id": fondo_id},
                     files=[("archivos", ("Oficio_114_1948.pdf", archivos.pdf_con_texto(OFICIO_114), "application/pdf"))])
    inst_id = r.json()["resultados"][0]["id"]
    procesamiento.procesar_pendientes(db)

    # 2. Descripción: propuesta del motor, aceptada y publicada.
    monkeypatch.setattr(motor, "motor_activo", lambda: MotorDePrueba(RESPUESTA_UNO))
    espacio = cliente.post("/api/descripcion/iniciar", headers=arch, json={"instanciacion_ids": [inst_id]}).json()
    datos = aceptar_todo(espacio)
    por_valor = {e["valor"]: e for e in datos["entidades"]}
    por_valor["Gobernador del Departamento"]["valor"] = "Gobernación de Boyacá"  # corregida
    por_valor["Gobernador del Departamento"]["subtipo"] = "entidad_corporativa"
    datos["entidades"].remove(por_valor["Boyacá"])  # rechazada; las demás, aceptadas
    publicada = cliente.post("/api/descripcion/publicar", headers=arch, json=datos)
    assert publicada.status_code == 201, publicada.text
    recurso_id = publicada.json()["id"]
    # Corrección con los datos de control del inventario.
    trabajo = cliente.post(f"/api/descripcion/registros/{recurso_id}/reabrir", headers=arch).json()["trabajo_id"]
    control = {"codigo_referencia": "CO-AM-114", "caja": "1", "carpeta": "3", "folios": 2, "soporte": "Papel"}
    assert cliente.patch(f"/api/descripcion/{recurso_id}", headers=arch,
                         json={"trabajo_id": trabajo, "control": control}).status_code == 200

    # 3. Vocabularios: la entidad publicada aparece; una variante se fusiona en ella.
    vocab = cliente.get("/api/vocabulario", headers=arch, params={"fondo_id": fondo_id}).json()
    alcaldia = next(e for e in vocab if e["nombre"] == "Alcaldía Municipal")
    assert alcaldia["conexiones"] == 1
    variante = vocabulario.crear(db, fondo_id=uuid.UUID(fondo_id), clase="agente", nombre="Alcaldia Mpal.",
                                 subtipo="entidad_corporativa", origen="persona", confianza=None, motor=None, usuario_id=None)
    db.commit()
    assert cliente.post("/api/vocabulario/fusionar", headers=arch,
                        json={"definitiva_id": alcaldia["id"], "absorbida_id": str(variante.id)}).status_code == 200

    # 4. Instrumentos: el inventario incluye el oficio con sus datos; la guía se exporta.
    inventario = cliente.post("/api/instrumentos/inventario/vista-previa", headers=arch, json={"recurso_id": fondo_id}).json()
    [fila] = inventario["filas"]
    assert fila["valores"]["codigo"] == "CO-AM-114" and fila["valores"]["fecha_inicial"] == "15/03/1948"
    assert inventario["pendientes"] == 0
    assert cliente.post("/api/instrumentos/inventario", headers=arch, json={"recurso_id": fondo_id}).status_code == 200
    monkeypatch.setattr(motor, "motor_activo", lambda: None)
    guia = cliente.post("/api/instrumentos/guia", headers=arch, json={"fondo_id": fondo_id}).json()["texto"]
    docx = cliente.post("/api/instrumentos/guia/exportar", headers=arch, json={"fondo_id": fondo_id, "texto": guia})
    assert "Correspondencia municipal" in " ".join(p.text for p in Document(io.BytesIO(docx.content)).paragraphs)
    indice = cliente.get("/api/instrumentos/indice", headers=arch, params={"fondo_id": fondo_id}).json()
    assert any(e["nombre"] == "Alcaldía Municipal" for g in indice["grupos"] for l in g["letras"] for e in l["entidades"])

    # 5. Preservación: verificación de integridad y migración aprobada a PDF/A.
    assert cliente.post(f"/api/preservacion/instanciacion/{inst_id}/verificar", headers=arch).json()["resultado"] == "integra"
    m = cliente.post(f"/api/preservacion/instanciacion/{inst_id}/migrar", headers=arch,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    assert m["estado"] == "completada"
    ficha = cliente.get(f"/api/instrumentos/catalogo/{recurso_id}", headers=arch).json()
    assert len(ficha["instanciaciones"]) == 2  # la original y su versión de conservación, en la misma descripción

    # Exportaciones de esta ronda: el paquete de preservación y el fondo en RiC-O.
    assert cliente.post(f"/api/preservacion/instanciacion/{inst_id}/exportar-paquete", headers=arch).status_code == 200
    assert cliente.get("/api/exportacion/rdf", headers=arch, params={"fondo_id": fondo_id}).status_code == 200
    conformidad = cliente.get("/api/exportacion/conformidad", headers=arch, params={"fondo_id": fondo_id}).json()
    assert conformidad["conforme"], conformidad

    # La administradora registra un hallazgo y lo pasa a corrección.
    h = cliente.post("/api/auditoria/hallazgos", headers=adm, json={
        "titulo": "Prueba de integración", "descripcion": "Hallazgo de la prueba de extremo a extremo.",
        "componentes": ["auditoria"]}).json()
    cliente.patch(f"/api/auditoria/hallazgos/{h['id']}", headers=adm, json={"estado": "en_correccion"})

    # 6. Cierre de sesión de la archivista.
    assert cliente.post("/api/auth/logout", headers=arch).status_code == 204

    # --- Cada acción comprometida quedó exactamente una vez, con su autor ---
    nuevos = [e for e in eventos(db) if e.id > inicio_prueba]
    for modulo, acciones in COMPROMETIDAS.items():
        for accion in acciones:
            del_modulo = [e for e in nuevos if e.accion == accion and e.modulo == modulo]
            esperado = VECES.get(accion, 1)
            if accion == "usuario_editado":
                esperado = 1  # el cambio de rol; la desactivación tiene su propia acción
            assert len(del_modulo) == esperado, f"{modulo}/{accion}: {len(del_modulo)} eventos"
    por = {e.accion: e for e in nuevos}
    # Las tres decisiones de validación, con su tipo bien calculado.
    decisiones = {(e.valor_nuevo["tipo"], (e.valor_nuevo["propuesto"] or {}).get("valor")): e.valor_nuevo["decision"]
                  for e in nuevos if e.accion == "decision_ia"}
    assert decisiones[("agente", "Alcaldía Municipal")] == "aceptada"
    assert decisiones[("agente", "Gobernador del Departamento")] == "corregida"
    assert decisiones[("lugar", "Boyacá")] == "rechazada"
    assert all(e.usuario_id == catalina.id for e in nuevos if e.accion == "decision_ia")
    assert por["documento_cargado"].usuario_id == catalina.id and por["fondo_registrado"].usuario_id == admin.id
    assert por["usuario_editado"].valor_anterior == {"rol": "revisor"} and por["usuario_editado"].valor_nuevo == {"rol": "consulta"}
    editada = por["descripcion_editada"]
    assert editada.valor_anterior["caja"] is None and editada.valor_nuevo["caja"] == "1"
    assert por["fusion_vocabulario"].valor_anterior["absorbida"]["nombre"] == "Alcaldia Mpal."
    assert por["migracion_completada"].valor_nuevo["formato"] == "fmt/477"
    assert por["cierre_sesion"].usuario_id == catalina.id and por["cierre_sesion"].valor_nuevo["motivo"] == "cierre_voluntario"

    # La trazabilidad propia de la archivista tiene todo lo suyo y nada de la administradora.
    arch2 = ingresar(cliente, "catalina@correo.com")
    propia = cliente.get("/api/auditoria/mi-trazabilidad", headers=arch2).json()["eventos"]
    acciones_propias = {e["accion"] for e in propia}
    assert {"documento_cargado", "descripcion_publicada", "fusion_vocabulario", "inventario_exportado",
            "migracion_aprobada"} <= acciones_propias
    assert all(e["usuario_id"] == str(catalina.id) for e in propia)
    assert "fondo_registrado" not in acciones_propias and "usuario_creado" not in acciones_propias
    # Y la historia de la descripción, lado a lado.
    historia = cliente.get(f"/api/auditoria/entidad/{recurso_id}", headers=arch2, params={"tipo": "recurso_documental"}).json()
    cambio = next(e for e in historia["eventos"] if e["accion"] == "descripcion_editada")
    assert {"campo": "caja", "antes": None, "despues": "1",
            "propiedad_rico": {"nombre": None, "estado": "literal_pendiente"}} in cambio["cambios"]


def test_cada_accion_del_codigo_tiene_nombre_legible():
    """Toda acción que algún módulo registra tiene su nombre en el catálogo
    (así ninguna aparece como código en las pantallas)."""
    import pathlib
    import re

    from app.servicios.auditoria import Accion

    usadas = set()
    for archivo in pathlib.Path("app").rglob("*.py"):
        texto = archivo.read_text()
        usadas |= set(re.findall(r'accion="([a-z_]+)"', texto))
        usadas |= {getattr(Accion, c) for c in re.findall(r"accion=Accion\.([A-Z_]+)", texto)}
        usadas |= set(re.findall(r'"(carga_[a-z]+)"', texto))
    faltan = sorted(a for a in usadas if a not in trazabilidad.ACCIONES)
    assert faltan == []
    for acciones in COMPROMETIDAS.values():
        assert all(a in trazabilidad.ACCIONES for a in acciones)


# --- Sesiones -------------------------------------------------------------------------------------


def test_inicio_cierre_y_expiracion_generan_sus_eventos_sin_intervencion(cliente, db):
    u = crear_usuario(db, "catalina@correo.com")
    ingresar(cliente, "catalina@correo.com")
    [inicio] = eventos(db, "inicio_sesion", usuario_id=u.id)
    sesion = db.get(Sesion, uuid.UUID(inicio.entidad_id))
    sesion.ultima_actividad = ahora() - timedelta(hours=2)  # se fue sin cerrar
    db.commit()
    assert sesiones.cerrar_vencidas(db) == 1  # lo que hace el trabajador cada minuto
    db.commit()
    [cierre] = eventos(db, "cierre_sesion", usuario_id=u.id)
    assert cierre.valor_nuevo["motivo"] == "expiracion"
    assert datetime.fromisoformat(cierre.valor_nuevo["fin"]) == sesion.ultima_actividad


# --- Panel consolidado ------------------------------------------------------------------------------


def test_horas_de_varias_sesiones_el_mismo_dia_y_persona_sin_sesiones(cliente, db, cabeceras_admin):
    catalina = crear_usuario(db, "catalina@correo.com", nombre="Catalina Torres")
    crear_usuario(db, "laura@correo.com", "consulta", nombre="Laura Gómez")
    martes = datetime(2026, 9, 22, tzinfo=BOGOTA)  # semana del lunes 21 de septiembre de 2026
    # Eventos de sesión como los deja autenticación, fechados en su hora real.
    for h_ini, h_fin in ((8, 10.5), (14, 15.25)):
        ini = martes + timedelta(hours=h_ini)
        fin = martes + timedelta(hours=h_fin)
        sid = uuid.uuid4()
        db.add(RegistroAuditoria(fecha=ini, usuario_id=catalina.id, modulo="autenticacion", accion="inicio_sesion",
                                 entidad_tipo="sesion", entidad_id=str(sid), valor_nuevo={"inicio": ini.isoformat()}))
        db.add(RegistroAuditoria(fecha=fin, usuario_id=catalina.id, modulo="autenticacion", accion="cierre_sesion",
                                 entidad_tipo="sesion", entidad_id=str(sid),
                                 valor_nuevo={"inicio": ini.isoformat(), "fin": fin.isoformat(), "motivo": "cierre_voluntario"}))
    # Una sesión del jueves que pasa de la medianoche cuenta en los dos días.
    jueves = martes + timedelta(days=2, hours=22)
    sid = uuid.uuid4()
    db.add(RegistroAuditoria(fecha=jueves, usuario_id=catalina.id, modulo="autenticacion", accion="inicio_sesion",
                             entidad_tipo="sesion", entidad_id=str(sid), valor_nuevo={"inicio": jueves.isoformat()}))
    db.add(RegistroAuditoria(fecha=jueves + timedelta(hours=3), usuario_id=catalina.id, modulo="autenticacion",
                             accion="cierre_sesion", entidad_tipo="sesion", entidad_id=str(sid),
                             valor_nuevo={"inicio": jueves.isoformat(), "fin": (jueves + timedelta(hours=3)).isoformat(),
                                          "motivo": "expiracion"}))
    db.add(RegistroAuditoria(fecha=martes + timedelta(hours=9), usuario_id=catalina.id, modulo="ingesta",
                             accion="documento_cargado", entidad_tipo="instanciacion", entidad_id="x"))
    db.add(RegistroAuditoria(fecha=martes + timedelta(hours=9, minutes=5), usuario_id=catalina.id, modulo="ingesta",
                             accion="documento_cargado", entidad_tipo="instanciacion", entidad_id="y"))
    db.commit()
    r = cliente.get("/api/auditoria/consolidado", headers=cabeceras_admin, params={"semana": "2026-09-23"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["semana"]["lunes"] == "2026-09-21"
    fila = next(f for f in datos["filas"] if f["nombre"] == "Catalina Torres")
    assert fila["segundos_conectado"] == int((2.5 + 1.25 + 3) * 3600)  # 2 h 30 + 1 h 15 + 3 h
    assert fila["dias_trabajados"] == 3 and fila["sesiones"] == 3  # martes, jueves y viernes (después de medianoche)
    assert fila["acciones"] == {"Documentos cargados": 2}
    # Quien no tuvo sesiones aparece con ceros, no se omite.
    laura = next(f for f in datos["filas"] if f["nombre"] == "Laura Gómez")
    assert laura["dias_trabajados"] == 0 and laura["segundos_conectado"] == 0 and laura["acciones"] == {}
    # Desglose sesión por sesión.
    desglose = cliente.get(f"/api/auditoria/consolidado/{catalina.id}", headers=cabeceras_admin,
                           params={"semana": "2026-09-21"}).json()
    assert [s["segundos"] for s in desglose["sesiones"]] == [9000, 4500, 10800]
    assert desglose["sesiones"][0]["acciones"] == {"Documentos cargados": 2}
    # Otra semana: ceros.
    otra = cliente.get("/api/auditoria/consolidado", headers=cabeceras_admin, params={"semana": "2026-09-07"}).json()
    assert next(f for f in otra["filas"] if f["nombre"] == "Catalina Torres")["segundos_conectado"] == 0


# --- Visibilidad ------------------------------------------------------------------------------------


def test_cada_archivista_solo_ve_lo_suyo(cliente, db):
    a = crear_usuario(db, "catalina@correo.com", nombre="Catalina Torres")
    b = crear_usuario(db, "andres@correo.com", nombre="Andrés Pérez")
    for u, entidad in ((a, "doc-1"), (b, "doc-1"), (b, "doc-2")):
        registrar(db, modulo="ingesta", accion="documento_cargado", usuario_id=u.id, entidad_tipo="instanciacion",
                  entidad_id=entidad)
    db.commit()
    cab_a = ingresar(cliente, "catalina@correo.com")
    propia = cliente.get("/api/auditoria/mi-trazabilidad", headers=cab_a).json()["eventos"]
    assert propia and all(e["usuario_id"] == str(a.id) for e in propia)
    # En la historia de una entidad tocada por los dos, solo ve su evento.
    historia = cliente.get("/api/auditoria/entidad/doc-1", headers=cab_a, params={"tipo": "instanciacion"}).json()
    assert historia["solo_propias"] and [e["usuario"] for e in historia["eventos"]] == ["Catalina Torres"]
    # Ni el panel consolidado ni el desglose de un compañero.
    assert cliente.get("/api/auditoria/consolidado", headers=cab_a).status_code == 403
    assert cliente.get(f"/api/auditoria/consolidado/{b.id}", headers=cab_a).status_code == 403
    # El filtro por tipo y fechas funciona sobre lo propio.
    hoy = ahora().astimezone(BOGOTA).date()
    filtrada = cliente.get("/api/auditoria/mi-trazabilidad", headers=cab_a,
                           params={"accion": "documento_cargado", "desde": str(hoy), "hasta": str(hoy)}).json()["eventos"]
    assert len(filtrada) == 1
    manana = hoy + timedelta(days=1)
    assert cliente.get("/api/auditoria/mi-trazabilidad", headers=cab_a,
                       params={"accion": "documento_cargado", "desde": str(manana)}).json()["eventos"] == []


def test_administrador_ve_toda_la_historia_y_consulta_no_entra(cliente, db, cabeceras_admin):
    a = crear_usuario(db, "catalina@correo.com", nombre="Catalina Torres")
    b = crear_usuario(db, "andres@correo.com", nombre="Andrés Pérez")
    for u in (a, b):
        registrar(db, modulo="ingesta", accion="documento_cargado", usuario_id=u.id, entidad_tipo="instanciacion",
                  entidad_id="doc-1")
    db.commit()
    historia = cliente.get("/api/auditoria/entidad/doc-1", headers=cabeceras_admin, params={"tipo": "instanciacion"}).json()
    assert sorted(e["usuario"] for e in historia["eventos"]) == ["Andrés Pérez", "Catalina Torres"]
    crear_usuario(db, "laura@correo.com", "consulta")
    consulta = ingresar(cliente, "laura@correo.com")
    assert cliente.get("/api/auditoria/mi-trazabilidad", headers=consulta).status_code == 403
    # Sin acceso al módulo de la entidad, tampoco a su historia.
    crear_usuario(db, "dig@correo.com", "digitalizador")
    digitalizador = ingresar(cliente, "dig@correo.com")
    assert cliente.get("/api/auditoria/entidad/x", headers=digitalizador,
                       params={"tipo": "entidad_vocabulario"}).status_code == 403


def test_ningun_evento_se_edita_ni_se_borra_por_ninguna_ruta(cliente, db, cabeceras_admin):
    rutas = [r for r in app.routes if getattr(r, "path", "").startswith("/api/auditoria")]
    # Solo se escriben los hallazgos de conformidad y las etiquetas de versión
    # (prompt v7); ninguna ruta escribe en el registro.
    escritura = {r.path for r in rutas if not r.methods <= {"GET", "HEAD"}}
    assert rutas and escritura == {"/api/auditoria/hallazgos", "/api/auditoria/hallazgos/{hallazgo_id}",
                                   "/api/auditoria/versiones-prompt/{version}"}
    registrar(db, modulo="ingesta", accion="documento_cargado", usuario_id=None, entidad_tipo="instanciacion",
              entidad_id="doc-1")
    db.commit()
    for metodo in ("put", "patch", "delete", "post"):
        r = getattr(cliente, metodo)("/api/auditoria/entidad/doc-1", headers=cabeceras_admin, params={"tipo": "instanciacion"})
        assert r.status_code == 405
    assert cliente.post("/api/auditoria/registrar", headers=cabeceras_admin, json={}).status_code in (404, 405)
    assert len(eventos(db, entidad_id="doc-1")) == 1
    # Tampoco un evento de decisión de IA, ni por la base de datos.
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    decision = registrar(db, modulo="descripcion", accion="decision_ia", usuario_id=None,
                         entidad_tipo="recurso_documental", entidad_id="doc-2", nuevo={"decision": "rechazada"})
    db.commit()
    for sentencia in ("UPDATE registro_auditoria SET valor_nuevo = '{\"decision\": \"aceptada\"}' WHERE id = :i",
                      "DELETE FROM registro_auditoria WHERE id = :i"):
        punto = db.begin_nested()
        with pytest.raises(DBAPIError):
            db.execute(text(sentencia), {"i": decision.id})
        punto.rollback()
    db.expire_all()
    assert db.get(RegistroAuditoria, decision.id).valor_nuevo == {"decision": "rechazada"}
