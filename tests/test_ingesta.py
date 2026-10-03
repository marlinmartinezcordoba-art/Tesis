"""
Pruebas del Módulo 1 · Ingesta y digitalización (sección 10 del prompt),
con Siegfried y Tesseract reales: no se simula la identificación de
formato ni el OCR, salvo para provocar fallas a propósito.
"""

import hashlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.base import ahora
from app.models.alerta import Alerta
from app.models.auditoria import RegistroAuditoria
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import almacen, formato, procesamiento, texto
from tests import archivos
from tests.conftest import crear_usuario, ingresar


@pytest.fixture(scope="module", autouse=True)
def herramientas():
    """Estas pruebas exigen las herramientas reales: si faltan, fallan
    (no se saltan), para que nadie crea que la ingesta está probada."""
    formato.herramienta.cache_clear()
    try:
        formato.herramienta()
    except formato.IdentificadorNoDisponible as exc:
        pytest.fail(f"Siegfried no está disponible para las pruebas: {exc}")


@pytest.fixture()
def fondo(db, admin):
    f = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Correspondencia municipal",
                          fechas_extremas="1930–1955", creado_por_id=admin.id)
    f.fondo_id = f.id
    db.add(f)
    db.commit()
    return f


@pytest.fixture()
def archivista(cliente, db):
    crear_usuario(db, "catalina@correo.com", "archivista", nombre="Catalina Torres")
    return ingresar(cliente, "catalina@correo.com")


def cargar(cliente, cabeceras, fondo, *archivos_, expediente=None):
    datos = {"fondo_id": str(fondo.id)}
    if expediente is not None:
        datos["expediente_id"] = str(expediente.id)
    r = cliente.post("/api/ingesta/cargar", headers=cabeceras, data=datos,
                     files=[("archivos", (nombre, contenido, "application/octet-stream")) for nombre, contenido in archivos_])
    assert r.status_code == 200, r.text
    return r.json()["resultados"]


def cola(cliente, cabeceras, fondo):
    r = cliente.get("/api/ingesta/cola", headers=cabeceras, params={"fondo_id": str(fondo.id)})
    assert r.status_code == 200, r.text
    return r.json()


def inst(db, id_):
    db.expire_all()
    return db.get(Instanciacion, uuid.UUID(str(id_)))


def eventos(db, accion, entidad_id=None):
    consulta = select(RegistroAuditoria).where(RegistroAuditoria.accion == accion)
    if entidad_id is not None:
        consulta = consulta.where(RegistroAuditoria.entidad_id == str(entidad_id))
    return db.scalars(consulta).all()


# --- Carga y procesamiento --------------------------------------------------------------


def test_carga_unica_llega_a_listo_para_descripcion(cliente, db, fondo, archivista):
    contenido = archivos.txt()
    [r] = cargar(cliente, archivista, fondo, ("acta_1948.txt", contenido))
    assert r["aceptado"] is True
    i = inst(db, r["id"])
    assert i.estado == "procesando" and i.paso == "en_espera"
    assert [e["nombre"] for e in cola(cliente, archivista, fondo)["procesando"]] == ["acta_1948.txt"]

    assert procesamiento.procesar_pendientes(db) == 1
    i = inst(db, r["id"])
    assert i.estado == "listo_para_descripcion" and i.progreso == 100
    assert i.huella == hashlib.sha256(contenido).hexdigest() and i.algoritmo_huella == "SHA-256"
    assert i.tamano_bytes == len(contenido)
    assert i.formato_puid == "x-fmt/111" and i.formato_no_identificado is False
    assert i.herramienta_identificacion.startswith("siegfried") and "PRONOM" in i.herramienta_identificacion
    assert i.origen_texto == "capa_de_texto" and "Concejo Municipal" in i.texto_extraido
    assert i.procesado_en is not None
    # El archivo queda en el almacenamiento con nombre propio, no el original.
    ruta = almacen.ruta_absoluta(i.ruta)
    assert ruta.read_bytes() == contenido and ruta.name == f"{i.id}.txt"
    assert str(settings.directorio_almacenamiento) in str(ruta)
    assert len(eventos(db, "documento_cargado", i.id)) == 1


def test_pdf_digital_usa_su_capa_de_texto(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("oficio.pdf", archivos.pdf_con_texto()))
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    assert i.estado == "listo_para_descripcion"
    assert i.formato_puid.startswith("fmt/") and i.formato_mime == "application/pdf"
    assert i.origen_texto == "capa_de_texto" and i.paginas == 1 and "presupuesto" in i.texto_extraido


def test_pdf_escaneado_pasa_por_ocr(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("escaneo_caja12.pdf", archivos.pdf_escaneado()))
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    assert i.estado == "listo_para_descripcion"
    assert i.origen_texto == "ocr" and i.paginas == 1
    assert "ARCHIVO MUNICIPAL" in i.texto_extraido


def test_imagen_pasa_por_ocr(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("oficio_114.png", archivos.png_con_texto()))
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    assert i.estado == "listo_para_descripcion" and i.formato_mime == "image/png"
    assert i.origen_texto == "ocr" and "OFICIO" in i.texto_extraido


def test_lote_mixto_cada_archivo_queda_en_su_estado(cliente, db, fondo, archivista):
    resultados = cargar(cliente, archivista, fondo,
                        ("acta.txt", archivos.txt()),
                        ("dañado.pdf", archivos.pdf_danado()),
                        ("oficio.png", archivos.png_con_texto()))
    assert all(r["aceptado"] for r in resultados)
    procesamiento.procesar_pendientes(db)
    estados = {r["nombre"]: inst(db, r["id"]).estado for r in resultados}
    assert estados == {"acta.txt": "listo_para_descripcion", "dañado.pdf": "error",
                       "oficio.png": "listo_para_descripcion"}
    danado = inst(db, resultados[1]["id"])
    assert "dañado" in danado.mensaje_error
    assert "Traceback" not in danado.mensaje_error and "Error" not in danado.mensaje_error
    c = cola(cliente, archivista, fondo)
    assert [e["nombre"] for e in c["errores"]] == ["dañado.pdf"]
    assert c["errores"][0]["mensaje_error"] == danado.mensaje_error


def test_archivo_que_excede_el_limite_no_afecta_a_los_demas(cliente, db, fondo, archivista, cabeceras_admin):
    assert cliente.put("/api/ingesta/limite", headers=cabeceras_admin, json={"limite_mb": 1}).json()["limite_mb"] == 1
    grande = b"x" * (1024 * 1024 + 10)
    resultados = cargar(cliente, archivista, fondo, ("plano.tif", grande), ("acta.txt", archivos.txt()))
    assert resultados[0]["aceptado"] is False and "Excede el límite de 1,0 MB" in resultados[0]["motivo"]
    assert resultados[1]["aceptado"] is True
    assert db.scalar(select(Instanciacion).where(Instanciacion.nombre_original == "plano.tif")) is None
    procesamiento.procesar_pendientes(db)
    assert inst(db, resultados[1]["id"]).estado == "listo_para_descripcion"
    assert len(eventos(db, "carga_rechazada")) == 1
    cambio = eventos(db, "parametro_cambiado", "ingesta_limite_mb")[-1]
    assert cambio.valor_anterior == {"ingesta_limite_mb": 500} and cambio.valor_nuevo == {"ingesta_limite_mb": 1}


def test_limite_por_defecto_y_solo_el_administrador_lo_cambia(cliente, archivista, cabeceras_admin):
    assert cliente.get("/api/ingesta/limite", headers=archivista).json() == {"limite_mb": 500, "limite_bytes": 500 * 1024 * 1024}
    assert cliente.put("/api/ingesta/limite", headers=archivista, json={"limite_mb": 900}).status_code == 403
    assert cliente.put("/api/ingesta/limite", headers=cabeceras_admin, json={"limite_mb": 0}).status_code == 422


def test_archivo_vacio_se_rechaza(cliente, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("vacio.txt", b""))
    assert r["aceptado"] is False and "vacío" in r["motivo"]


def test_nombre_malicioso_no_sale_del_almacenamiento(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("../../etc/acta.txt", archivos.txt()))
    i = inst(db, r["id"])
    assert i.nombre_original == "acta.txt"
    assert settings.directorio_almacenamiento.resolve() in almacen.ruta_absoluta(i.ruta).parents


# --- Duplicados -------------------------------------------------------------------------


def test_duplicado_confirmar_continua_hasta_listo(cliente, db, fondo, archivista):
    [original] = cargar(cliente, archivista, fondo, ("oficio_087.txt", archivos.txt()))
    procesamiento.procesar_pendientes(db)
    [copia] = cargar(cliente, archivista, fondo, ("oficio_087_copia.txt", archivos.txt()))
    procesamiento.procesar_pendientes(db)
    c = inst(db, copia["id"])
    assert c.estado == "duplicado_pendiente" and str(c.duplicado_de_id) == original["id"]
    assert c.formato_puid is None  # se detuvo antes de identificar el formato
    [pendiente] = cola(cliente, archivista, fondo)["duplicados"]
    assert pendiente["duplicado_de"]["nombre"] == "oficio_087.txt"

    r = cliente.post(f"/api/ingesta/{copia['id']}/confirmar-duplicado", headers=archivista)
    assert r.status_code == 200 and r.json()["estado"] == "procesando"
    procesamiento.procesar_pendientes(db)
    c = inst(db, copia["id"])
    assert c.estado == "listo_para_descripcion" and c.duplicado_confirmado is True
    assert c.formato_puid == "x-fmt/111"
    assert inst(db, original["id"]).estado == "listo_para_descripcion"
    assert len(eventos(db, "duplicado_confirmado", c.id)) == 1
    # Ya no se puede confirmar otra vez.
    assert cliente.post(f"/api/ingesta/{copia['id']}/confirmar-duplicado", headers=archivista).status_code == 409


def test_duplicado_cancelar_elimina_documento_y_archivo(cliente, db, fondo, archivista):
    [original] = cargar(cliente, archivista, fondo, ("acta.txt", archivos.txt()))
    procesamiento.procesar_pendientes(db)
    [copia] = cargar(cliente, archivista, fondo, ("acta_otra_vez.txt", archivos.txt()))
    procesamiento.procesar_pendientes(db)
    ruta = almacen.ruta_absoluta(inst(db, copia["id"]).ruta)
    assert ruta.exists()

    assert cliente.delete(f"/api/ingesta/{copia['id']}", headers=archivista).status_code == 204
    assert inst(db, copia["id"]) is None and not ruta.exists()
    o = inst(db, original["id"])
    assert o.estado == "listo_para_descripcion" and almacen.ruta_absoluta(o.ruta).exists()
    [evento] = eventos(db, "carga_cancelada", copia["id"])
    assert evento.valor_anterior["nombre"] == "acta_otra_vez.txt" and evento.valor_anterior["huella"]
    assert cola(cliente, archivista, fondo)["duplicados"] == []


def test_mismo_archivo_en_otro_fondo_no_es_duplicado(cliente, db, fondo, archivista, admin):
    otro = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Otro fondo")
    otro.fondo_id = otro.id
    db.add(otro)
    db.commit()
    cargar(cliente, archivista, fondo, ("acta.txt", archivos.txt()))
    [r] = cargar(cliente, archivista, otro, ("acta.txt", archivos.txt()))
    procesamiento.procesar_pendientes(db)
    assert inst(db, r["id"]).estado == "listo_para_descripcion"


# --- Formato no identificado, errores y reintento -------------------------------------------


def test_formato_no_identificado_llega_a_listo_y_aparece_en_alertas(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("registro_antiguo.xyz", archivos.desconocido()))
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    assert i.estado == "listo_para_descripcion"
    assert i.formato_no_identificado is True and "extension only" in (i.formato_base or "")
    assert i.origen_texto == "sin_texto"

    alertas = cliente.get("/api/alertas", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    [alerta] = [a for a in alertas if a["entidad_id"] == r["id"]]
    assert alerta["tipo"] == "formato_no_identificado" and "registro_antiguo.xyz" in alerta["mensaje"]
    # Atenderla la saca de las pendientes y queda en auditoría.
    atendida = cliente.post(f"/api/alertas/{alerta['id']}/atender", headers=archivista, json={"nota": "Revisado"})
    assert atendida.status_code == 200 and atendida.json()["atendida_por"] == "Catalina Torres"
    assert cliente.get("/api/alertas", headers=archivista, params={"fondo_id": str(fondo.id)}).json() == []
    assert len(eventos(db, "alerta_atendida", alerta["id"])) == 1


def test_reintento_de_un_documento_en_error(cliente, db, fondo, archivista, monkeypatch):
    original = texto.extraer
    fallos = {"n": 0}

    def falla_una_vez(*a, **k):
        if fallos["n"] == 0:
            fallos["n"] += 1
            raise texto.ArchivoIlegible("El archivo no se pudo leer, puede estar dañado.")
        return original(*a, **k)

    monkeypatch.setattr(texto, "extraer", falla_una_vez)
    [r] = cargar(cliente, archivista, fondo, ("acta.txt", archivos.txt()))
    procesamiento.procesar_pendientes(db)
    assert inst(db, r["id"]).estado == "error"

    reintento = cliente.post(f"/api/ingesta/{r['id']}/reintentar", headers=archivista)
    assert reintento.status_code == 200 and reintento.json()["estado"] == "procesando"
    i = inst(db, r["id"])
    assert i.huella is None and i.mensaje_error is None  # vuelve a empezar desde el principio
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    assert i.estado == "listo_para_descripcion" and i.intentos == 2
    assert len(eventos(db, "reintento", i.id)) == 1


def test_descartar_un_documento_en_error(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("dañado.pdf", archivos.pdf_danado()))
    procesamiento.procesar_pendientes(db)
    ruta = almacen.ruta_absoluta(inst(db, r["id"]).ruta)
    assert cliente.delete(f"/api/ingesta/{r['id']}", headers=archivista).status_code == 204
    assert inst(db, r["id"]) is None and not ruta.exists()
    assert len(eventos(db, "carga_descartada", r["id"])) == 1


def test_no_se_puede_descartar_ni_reintentar_lo_que_ya_esta_listo(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("acta.txt", archivos.txt()))
    procesamiento.procesar_pendientes(db)
    assert cliente.delete(f"/api/ingesta/{r['id']}", headers=archivista).status_code == 409
    assert cliente.post(f"/api/ingesta/{r['id']}/reintentar", headers=archivista).status_code == 409
    assert inst(db, r["id"]).estado == "listo_para_descripcion"


def test_herramienta_ausente_da_error_legible(cliente, db, fondo, archivista, monkeypatch):
    monkeypatch.setattr(settings, "siegfried_binario", "/no/existe/sf")
    formato.herramienta.cache_clear()
    [r] = cargar(cliente, archivista, fondo, ("acta.txt", archivos.txt()))
    procesamiento.procesar_pendientes(db)
    formato.herramienta.cache_clear()
    i = inst(db, r["id"])
    assert i.estado == "error" and "Avise al administrador" in i.mensaje_error


def test_la_cola_nunca_devuelve_documentos_listos(cliente, db, fondo, archivista):
    cargar(cliente, archivista, fondo, ("a.txt", archivos.txt("uno")), ("b.txt", archivos.txt("dos")),
           ("c.pdf", archivos.pdf_danado()))
    procesamiento.procesar_pendientes(db)
    c = cola(cliente, archivista, fondo)
    todos = c["procesando"] + c["duplicados"] + c["errores"]
    assert [e["nombre"] for e in todos] == ["c.pdf"]
    assert all(e["estado"] != "listo_para_descripcion" for e in todos)
    assert c["listos_hoy"] == 2


def test_trabajador_retoma_un_documento_abandonado(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("acta.txt", archivos.txt()))
    i = inst(db, r["id"])
    i.tomado_en = ahora()  # otro trabajador lo tiene y da señales de vida
    db.commit()
    assert procesamiento.tomar_siguiente(db) is None
    i.tomado_en = ahora() - timedelta(minutes=11)  # dejó de dar señales
    db.commit()
    assert procesamiento.tomar_siguiente(db) == i.id


# --- Expediente de destino y fondos ------------------------------------------------------------


def test_expediente_de_destino_opcional(cliente, db, fondo, archivista):
    exp = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo="Correspondencia 1948",
                            fondo_id=fondo.id, incluido_en_id=fondo.id)
    db.add(exp)
    db.commit()
    lista = cliente.get(f"/api/fondos/{fondo.id}/expedientes", headers=archivista).json()
    assert [e["titulo"] for e in lista] == ["Correspondencia 1948"]
    [r] = cargar(cliente, archivista, fondo, ("oficio.txt", archivos.txt()), expediente=exp)
    assert inst(db, r["id"]).expediente_destino_id == exp.id
    assert cola(cliente, archivista, fondo)["procesando"][0]["expediente"] == "Correspondencia 1948"


def test_expediente_de_otro_fondo_se_rechaza(cliente, db, fondo, archivista):
    otro = RecursoDocumental(id=uuid.uuid4(), nivel="fondo", titulo="Otro")
    otro.fondo_id = otro.id
    exp = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo="Ajeno", fondo_id=otro.id)
    db.add_all([otro, exp])
    db.commit()
    r = cliente.post("/api/ingesta/cargar", headers=archivista,
                     data={"fondo_id": str(fondo.id), "expediente_id": str(exp.id)},
                     files=[("archivos", ("a.txt", b"hola", "text/plain"))])
    assert r.status_code == 422


def test_solo_el_administrador_registra_fondos(cliente, db, archivista, cabeceras_admin):
    datos = {"titulo": "Archivo del Concejo", "fechas_extremas": "1910–1960"}
    assert cliente.post("/api/fondos", headers=archivista, json=datos).status_code == 403
    r = cliente.post("/api/fondos", headers=cabeceras_admin, json=datos)
    assert r.status_code == 201 and r.json()["documentos"] == 0
    assert cliente.post("/api/fondos", headers=cabeceras_admin, json={"titulo": "archivo del concejo"}).status_code == 409
    assert "Archivo del Concejo" in [f["titulo"] for f in cliente.get("/api/fondos", headers=archivista).json()]
    assert len(eventos(db, "fondo_registrado", r.json()["id"])) == 1


# --- Permisos -------------------------------------------------------------------------------


def _llamadas(fondo, id_):
    return [
        ("get", "/api/ingesta/cola", {"params": {"fondo_id": str(fondo.id)}}),
        ("get", "/api/ingesta/limite", {}),
        ("put", "/api/ingesta/limite", {"json": {"limite_mb": 10}}),
        ("post", "/api/ingesta/cargar", {"data": {"fondo_id": str(fondo.id)}, "files": [("archivos", ("a.txt", b"x"))]}),
        ("post", f"/api/ingesta/{id_}/confirmar-duplicado", {}),
        ("post", f"/api/ingesta/{id_}/reintentar", {}),
        ("delete", f"/api/ingesta/{id_}", {}),
    ]


def test_sin_sesion_ningun_endpoint_de_ingesta_responde(cliente, fondo):
    for metodo, ruta, extra in _llamadas(fondo, uuid.uuid4()):
        assert getattr(cliente, metodo if metodo != "delete" else "delete")(ruta, **extra).status_code == 401, ruta
    assert cliente.get("/api/alertas").status_code == 401
    assert cliente.get("/api/fondos").status_code == 401


def test_consulta_no_accede_a_ingesta(cliente, db, fondo):
    crear_usuario(db, "laura@correo.com", "consulta")
    cabeceras = ingresar(cliente, "laura@correo.com")
    for metodo, ruta, extra in _llamadas(fondo, uuid.uuid4()):
        assert getattr(cliente, metodo)(ruta, headers=cabeceras, **extra).status_code == 403, ruta
    assert cliente.get("/api/alertas", headers=cabeceras).status_code == 403


def test_revisor_solo_consulta_la_cola(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("c.pdf", archivos.pdf_danado()))
    procesamiento.procesar_pendientes(db)
    crear_usuario(db, "julian@correo.com", "revisor")
    cabeceras = ingresar(cliente, "julian@correo.com")
    assert cliente.get("/api/ingesta/cola", headers=cabeceras, params={"fondo_id": str(fondo.id)}).status_code == 200
    for metodo, ruta, extra in _llamadas(fondo, r["id"])[2:]:
        assert getattr(cliente, metodo)(ruta, headers=cabeceras, **extra).status_code == 403, ruta
    alerta = Alerta(tipo="formato_no_identificado", severidad="media", modulo="ingesta", entidad_tipo="instanciacion",
                    entidad_id=r["id"], mensaje="x", fondo_id=fondo.id)
    db.add(alerta)
    db.commit()
    assert cliente.post(f"/api/alertas/{alerta.id}/atender", headers=cabeceras, json={}).status_code == 403
    assert inst(db, r["id"]).estado == "error"


# --- Confianza del OCR (versión actualizada del módulo 1, sección 3bis) ---


def test_ocr_guarda_su_confianza_como_promedio_por_palabra(cliente, db, fondo, archivista, monkeypatch):
    # El promedio se calcula sobre la confianza de cada palabra que da Tesseract.
    capturadas = []
    original = texto.promedio

    def espia(lecturas):
        capturadas.extend(c for lectura in lecturas for c in lectura.confianzas)
        return original(lecturas)

    monkeypatch.setattr(texto, "promedio", espia)
    [r] = cargar(cliente, archivista, fondo, ("oficio_114.png", archivos.png_con_texto()))
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    assert i.origen_texto == "ocr" and capturadas
    assert i.confianza_ocr == pytest.approx(round(sum(capturadas) / len(capturadas), 1))
    assert i.palabras_ocr == len(capturadas)
    assert i.confianza_ocr >= 70 and i.ocr_baja_confianza is False
    alertas = cliente.get("/api/alertas", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert not [a for a in alertas if a["entidad_id"] == r["id"]]


def test_documento_con_capa_de_texto_deja_la_confianza_vacia_y_no_en_cero(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("oficio.pdf", archivos.pdf_con_texto()))
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    assert i.origen_texto == "capa_de_texto"
    assert i.confianza_ocr is None and i.palabras_ocr is None and i.ocr_baja_confianza is False


def test_confianza_bajo_el_umbral_marca_alerta_sin_bloquear(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("copia_borrosa.png", archivos.png_degradado()))
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    # La marca no detiene nada: el documento sigue a descripción.
    assert i.estado == "listo_para_descripcion"
    assert i.confianza_ocr is not None and i.confianza_ocr < 70 and i.ocr_baja_confianza is True
    alertas = cliente.get("/api/alertas", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    [alerta] = [a for a in alertas if a["entidad_id"] == r["id"]]
    assert alerta["tipo"] == "ocr_baja_confianza" and "copia_borrosa.png" in alerta["mensaje"]
    # La descripción recibe la confianza y la marca junto al documento.
    [fila] = [d for d in cliente.get("/api/descripcion/cola", headers=archivista,
                                     params={"fondo_id": str(fondo.id)}).json() if d["id"] == r["id"]]
    assert fila["ocr_baja_confianza"] is True and fila["confianza_ocr"] == i.confianza_ocr


def test_el_umbral_es_configurable_y_solo_lo_cambia_el_administrador(cliente, db, fondo, archivista, cabeceras_admin):
    assert cliente.get("/api/ingesta/umbral-ocr", headers=archivista).json() == {"umbral": 70}
    assert cliente.put("/api/ingesta/umbral-ocr", headers=archivista, json={"umbral": 50}).status_code == 403
    assert cliente.put("/api/ingesta/umbral-ocr", headers=cabeceras_admin, json={"umbral": 101}).status_code == 422
    assert cliente.put("/api/ingesta/umbral-ocr", headers=cabeceras_admin, json={"umbral": 40}).json() == {"umbral": 40}
    assert len(eventos(db, "parametro_cambiado", "ingesta_umbral_ocr")) == 1
    # Con umbral 40, la misma copia borrosa ya no queda marcada.
    [r] = cargar(cliente, archivista, fondo, ("copia_borrosa.png", archivos.png_degradado()))
    procesamiento.procesar_pendientes(db)
    assert inst(db, r["id"]).ocr_baja_confianza is False


def test_ocr_sin_palabras_reconocidas_es_confianza_cero():
    # Cero significa extracción fallida, distinto de vacío (no aplicó).
    assert texto.promedio([texto.Lectura("", [])]) == (0.0, 0)
    assert texto.promedio([texto.Lectura("a", [90.0]), texto.Lectura("b", [50.0, 70.0])]) == (70.0, 3)


def test_reintento_recalcula_la_confianza(cliente, db, fondo, archivista):
    [r] = cargar(cliente, archivista, fondo, ("copia_borrosa.png", archivos.png_degradado()))
    procesamiento.procesar_pendientes(db)
    i = inst(db, r["id"])
    procesamiento.reiniciar(i)
    assert i.confianza_ocr is None and i.ocr_baja_confianza is False
