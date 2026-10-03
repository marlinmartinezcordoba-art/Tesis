"""
Pruebas del Módulo 5 · Preservación digital (sección 9 del prompt), con
archivos reales pasados por la ingesta de verdad (Siegfried/PRONOM) y
conversiones reales (Ghostscript a PDF/A-2b, Pillow a TIFF).
"""

import io
import shutil
import uuid
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.db.base import ahora
from app.models.alerta import Alerta
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.parametro import Parametro
from app.models.preservacion import Migracion, VerificacionIntegridad
from app.models.recurso_documental import RecursoDocumental
from app.servicios import almacen, formato, preservacion, procesamiento
from tests import archivos
from tests.conftest import crear_usuario, ingresar


@pytest.fixture(scope="module", autouse=True)
def herramientas():
    """Exigen las herramientas reales: si faltan, fallan (no se saltan)."""
    formato.herramienta.cache_clear()
    formato.herramienta()
    assert shutil.which(settings.ghostscript_binario), "Falta Ghostscript (gs) para las pruebas de migración."


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


def jpeg() -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", (400, 300), (180, 150, 110)).save(salida, format="JPEG", quality=85)
    return salida.getvalue()


def ingresar_archivo(cliente, db, cabeceras, fondo, nombre, contenido) -> Instanciacion:
    r = cliente.post("/api/ingesta/cargar", headers=cabeceras, data={"fondo_id": str(fondo.id)},
                     files=[("archivos", (nombre, contenido, "application/octet-stream"))])
    assert r.status_code == 200, r.text
    procesamiento.procesar_pendientes(db)
    db.expire_all()
    inst = db.get(Instanciacion, uuid.UUID(r.json()["resultados"][0]["id"]))
    assert inst.estado == "listo_para_descripcion"
    return inst


def describir(db, fondo, inst) -> RecursoDocumental:
    r = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo="Oficio 114", fondo_id=fondo.id,
                          incluido_en_id=fondo.id, publicado_en=ahora())
    db.add(r)
    db.flush()
    db.add(Relacion(origen_tipo="recurso_documental", origen_id=r.id, destino_tipo="instanciacion", destino_id=inst.id,
                    tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation", origen="persona"))
    db.commit()
    return r


def foto(db, inst) -> tuple:
    """Todo lo que identifica a la original, para comprobar que no cambia."""
    db.expire_all()
    i = db.get(Instanciacion, inst.id)
    ruta = almacen.ruta_absoluta(i.ruta)
    return (i.nombre_original, i.ruta, i.tamano_bytes, i.huella, i.formato_puid, i.estado,
            ruta.read_bytes() if ruta.exists() else None)


# --- Integridad ---------------------------------------------------------------------------------


def test_verificacion_integra_sin_alerta(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    r = cliente.post(f"/api/preservacion/instanciacion/{inst.id}/verificar", headers=archivista)
    assert r.status_code == 200 and r.json()["resultado"] == "integra"
    assert db.scalars(select(Alerta).where(Alerta.tipo == "integridad_alterada")).all() == []
    detalle = cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=archivista).json()
    assert detalle["estado_integridad"] == "integra" and detalle["verificaciones"][0]["resultado"] == "integra"
    assert detalle["verificaciones"][0]["por"] == "Catalina Torres"


def test_archivo_alterado_queda_en_historial_y_alerta_alta(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    with open(almacen.ruta_absoluta(inst.ruta), "ab") as f:
        f.write(b"% alteracion")  # alguien tocó el archivo en el disco
    r = cliente.post(f"/api/preservacion/instanciacion/{inst.id}/verificar", headers=archivista).json()
    assert r["resultado"] == "alterada" and r["huella_calculada"] != r["huella_registrada"]
    [alerta] = db.scalars(select(Alerta).where(Alerta.tipo == "integridad_alterada")).all()
    assert alerta.severidad == "alta" and alerta.entidad_id == str(inst.id)
    [v] = db.scalars(select(VerificacionIntegridad).where(VerificacionIntegridad.instanciacion_id == inst.id)).all()
    assert v.resultado == "alterada" and v.origen == "manual"
    panel = cliente.get("/api/preservacion/panel", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert panel["resumen"]["alerta_integridad"] == 1
    assert panel["atencion"][0]["tipo"] == "integridad_alterada"  # lo más grave primero
    # Un archivo que desapareció también se reporta.
    otro = ingresar_archivo(cliente, db, archivista, fondo, "otro.txt", archivos.txt("otro"))
    almacen.ruta_absoluta(otro.ruta).unlink()
    assert cliente.post(f"/api/preservacion/instanciacion/{otro.id}/verificar", headers=archivista).json()[
        "resultado"] == "ausente"


def test_verificacion_periodica_respeta_la_frecuencia(cliente, db, fondo, archivista):
    ingresar_archivo(cliente, db, archivista, fondo, "a.pdf", archivos.pdf_con_texto("uno"))
    ingresar_archivo(cliente, db, archivista, fondo, "b.txt", archivos.txt("dos"))
    assert preservacion.verificacion_periodica(db) == 2  # primera vez: corre
    assert preservacion.verificacion_periodica(db) is None  # recién hecha: no corre
    marca = db.get(Parametro, preservacion.CLAVE_ULTIMA_VERIFICACION)
    marca.valor = (ahora() - timedelta(days=29, hours=23)).isoformat()  # 30 días por defecto: aún no
    db.commit()
    assert preservacion.verificacion_periodica(db) is None
    marca.valor = (ahora() - timedelta(days=30, minutes=1)).isoformat()
    db.commit()
    assert preservacion.verificacion_periodica(db) == 2
    # Con frecuencia semanal, a los 8 días vuelve a correr; a los 6, no.
    db.add(Parametro(clave="preservacion_frecuencia_dias", valor=7))
    marca.valor = (ahora() - timedelta(days=6)).isoformat()
    db.commit()
    assert preservacion.verificacion_periodica(db) is None
    marca.valor = (ahora() - timedelta(days=8)).isoformat()
    db.commit()
    assert preservacion.verificacion_periodica(db) == 2
    periodicas = db.scalars(select(VerificacionIntegridad).where(VerificacionIntegridad.origen == "periodica")).all()
    assert len(periodicas) == 6 and all(v.resultado == "integra" for v in periodicas)


# --- Riesgo de obsolescencia --------------------------------------------------------------------


def test_riesgo_de_formato_con_razon_y_alerta_en_el_panel_central(cliente, db, fondo, archivista):
    pdf = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    png = ingresar_archivo(cliente, db, archivista, fondo, "plano.png", archivos.png_con_texto())
    d = cliente.get(f"/api/preservacion/instanciacion/{pdf.id}", headers=archivista).json()
    assert d["riesgo"]["nivel"] == "medio" and "PDF/A" in d["riesgo"]["razon"] and d["riesgo"]["destino_sugerido"] == "pdfa_2b"
    assert cliente.get(f"/api/preservacion/instanciacion/{png.id}", headers=archivista).json()["riesgo"]["nivel"] == "bajo"
    panel = cliente.get("/api/preservacion/panel", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert panel["resumen"] == {"total": 2, "alerta_integridad": 0, "alerta_segunda_copia": 0, "riesgo_obsolescencia": 1,
                                "buen_estado": 1}
    # Es el mismo panel central de alertas del sistema, no uno aparte.
    [alerta] = cliente.get("/api/alertas", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert alerta["tipo"] == "riesgo_obsolescencia" and alerta["modulo"] == "preservacion"


# --- Migración ----------------------------------------------------------------------------------


def test_migracion_soportada_crea_nueva_instanciacion_sin_tocar_la_original(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "Oficio_114.pdf", archivos.pdf_con_texto())
    recurso = describir(db, fondo, original)
    antes = foto(db, original)
    d = cliente.get(f"/api/preservacion/instanciacion/{original.id}", headers=archivista).json()
    assert next(x for x in d["destinos"] if x["clave"] == "pdfa_2b")["automatica"]
    r = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["estado"] == "completada" and m["modo"] == "automatica" and "Ghostscript" in m["herramienta"]
    nueva = m["nueva_instanciacion"]
    assert nueva["formato"]["puid"] == "fmt/477"  # PDF/A-2b según Siegfried
    assert nueva["derivada_de"]["id"] == str(original.id) and nueva["riesgo"]["nivel"] == "bajo"
    nueva_id = uuid.UUID(nueva["id"])
    # Enlazada por RiC-R015 migrated into y al mismo Record Resource.
    assert db.scalar(select(Relacion).where(Relacion.origen_id == original.id, Relacion.destino_id == nueva_id,
                                            Relacion.codigo_ric == "migrated_into"))
    assert db.scalar(select(Relacion).where(Relacion.origen_id == recurso.id, Relacion.destino_id == nueva_id,
                                            Relacion.codigo_ric == "has_or_had_instantiation"))
    assert db.scalar(select(RecursoDocumental).where(RecursoDocumental.id == recurso.id)).titulo == "Oficio 114"
    # La original sigue igual, byte a byte, y visible en el historial.
    assert foto(db, original) == antes
    historial = cliente.get(f"/api/preservacion/instanciacion/{original.id}", headers=archivista).json()
    assert historial["migraciones"][0]["resultado"]["id"] == str(nueva_id)
    assert historial["riesgo"]["mitigado_por"]["id"] == str(nueva_id)
    # No aparece como documento nuevo por describir.
    cola = cliente.get("/api/descripcion/cola", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert str(nueva_id) not in {c["id"] for c in cola}
    # La alerta de riesgo de la original se cierra sola.
    assert all(a.atendida_en for a in db.scalars(select(Alerta).where(Alerta.tipo == "riesgo_obsolescencia")))


def test_migracion_de_imagen_a_tiff(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "foto.jpg", jpeg())
    antes = foto(db, original)
    m = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "tiff", "aprobada": True}).json()
    assert m["estado"] == "completada" and m["nueva_instanciacion"]["formato"]["puid"] in preservacion.DESTINOS["tiff"].puids
    assert m["nueva_instanciacion"]["nombre"] == "foto (TIFF sin pérdida).tif"
    assert foto(db, original) == antes


def test_migracion_no_soportada_espera_el_archivo_y_luego_lo_enlaza(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "acta.pdf", archivos.pdf_con_texto())
    recurso = describir(db, fondo, original)
    antes = foto(db, original)
    total = len(db.scalars(select(Instanciacion).where(Instanciacion.fondo_id == fondo.id)).all())
    m = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "txt", "aprobada": True}).json()
    assert m["estado"] == "esperando_archivo" and m["modo"] == "manual" and m["nueva_instanciacion"] is None
    assert len(db.scalars(select(Instanciacion).where(Instanciacion.fondo_id == fondo.id)).all()) == total
    r = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar/cargar", headers=archivista,
                     data={"migracion_id": m["id"]},
                     files=[("archivo", ("acta.txt", archivos.txt(), "text/plain"))])
    assert r.status_code == 200, r.text
    nueva = r.json()["nueva_instanciacion"]
    assert r.json()["estado"] == "completada" and nueva["derivada_de"]["id"] == str(original.id)
    nueva_id = uuid.UUID(nueva["id"])
    assert db.scalar(select(Relacion).where(Relacion.origen_id == original.id, Relacion.destino_id == nueva_id,
                                            Relacion.codigo_ric == "migrated_into"))
    assert db.scalar(select(Relacion).where(Relacion.origen_id == recurso.id, Relacion.destino_id == nueva_id))
    assert foto(db, original) == antes
    # No se puede cargar dos veces para la misma solicitud.
    otra = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar/cargar", headers=archivista,
                        data={"migracion_id": m["id"]}, files=[("archivo", ("x.txt", b"x", "text/plain"))])
    assert otra.status_code == 409


def test_migracion_fallida_no_toca_la_original(cliente, db, fondo, archivista, monkeypatch):
    original = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    antes = foto(db, original)
    archivos_antes = {p for p in almacen.raiz().rglob("*") if p.is_file()}

    def rompe(entrada, salida):
        salida.write_bytes(b"no es un PDF/A")
        return preservacion.Ejecucion("Conversor roto", "0.1", "nada")

    monkeypatch.setitem(preservacion.CONVERSORES, "ghostscript_pdfa",
                        preservacion.Conversor("ghostscript_pdfa", "roto", "pdfa_2b", rompe))
    m = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    assert m["estado"] == "fallida" and "no es PDF/A-2b" in m["mensaje"]
    assert foto(db, original) == antes
    assert len(db.scalars(select(Instanciacion).where(Instanciacion.derivada_de_id == original.id)).all()) == 0
    # Ningún archivo huérfano quedó en el almacenamiento.
    assert {p for p in almacen.raiz().rglob("*") if p.is_file()} == archivos_antes


def test_ninguna_migracion_sin_aprobacion_explicita_y_auditada(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    sin = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                       json={"destino": "pdfa_2b", "aprobada": False})
    assert sin.status_code == 422
    assert db.scalars(select(Migracion)).all() == []
    # Ni la verificación periódica ni el panel migran nada por su cuenta.
    preservacion.verificacion_periodica(db)
    cliente.get("/api/preservacion/panel", headers=archivista, params={"fondo_id": str(fondo.id)})
    assert db.scalars(select(Migracion)).all() == []
    cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                 json={"destino": "pdfa_2b", "aprobada": True})
    [m] = db.scalars(select(Migracion)).all()
    [aprobacion] = db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "migracion_aprobada")).all()
    assert aprobacion.usuario_id == m.aprobada_por_id and aprobacion.valor_nuevo["migracion_id"] == str(m.id)
    assert db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "migracion_completada")).one()


# --- Permisos y configuración -------------------------------------------------------------------


def test_configuracion_solo_administrador(cliente, db, fondo, archivista, cabeceras_admin):
    for metodo in ("get", "put"):
        kwargs = {"json": {"frecuencia_dias": 7, "formatos": []}} if metodo == "put" else {}
        assert getattr(cliente, metodo)("/api/preservacion/configuracion", headers=archivista, **kwargs).status_code == 403
    crear_usuario(db, "julian@correo.com", "revisor")
    revisor = ingresar(cliente, "julian@correo.com")
    assert cliente.get("/api/preservacion/configuracion", headers=revisor).status_code == 403
    conf = cliente.get("/api/preservacion/configuracion", headers=cabeceras_admin).json()
    assert conf["frecuencia_dias"] == 30 and [f["destino"] for f in conf["formatos"]] == ["pdfa_2b", "tiff"]
    # Ampliar la tabla sin tocar código: PostScript ya estaba; se agrega BMP → TIFF desactivado.
    formatos = conf["formatos"] + [{"id": "bmp", "origen": "Mapas de bits", "origen_mime": ["image/bmp"],
                                     "destino": "tiff", "conversor": "pillow_tiff", "activo": False}]
    r = cliente.put("/api/preservacion/configuracion", headers=cabeceras_admin,
                    json={"frecuencia_dias": 7, "formatos": formatos})
    assert r.status_code == 200 and r.json()["frecuencia_dias"] == 7 and len(r.json()["formatos"]) == 3
    # Un conversor que no produce ese destino se rechaza.
    malo = formatos + [{"id": "x", "origen": "X", "origen_mime": ["image/png"], "destino": "pdfa_2b",
                        "conversor": "pillow_tiff", "activo": True}]
    assert cliente.put("/api/preservacion/configuracion", headers=cabeceras_admin,
                       json={"frecuencia_dias": 7, "formatos": malo}).status_code == 422
    # Si se desactiva PDF → PDF/A, esa migración pasa a ser manual.
    sin_pdf = [dict(f, activo=False) if f["destino"] == "pdfa_2b" else f for f in formatos]
    cliente.put("/api/preservacion/configuracion", headers=cabeceras_admin, json={"frecuencia_dias": 7, "formatos": sin_pdf})
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    destinos = cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=archivista).json()["destinos"]
    assert not next(d for d in destinos if d["clave"] == "pdfa_2b")["automatica"]


def test_permisos_del_modulo(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    crear_usuario(db, "laura@correo.com", "consulta")
    crear_usuario(db, "julian@correo.com", "revisor")
    consulta, revisor = ingresar(cliente, "laura@correo.com"), ingresar(cliente, "julian@correo.com")
    assert cliente.get("/api/preservacion/panel", params={"fondo_id": str(fondo.id)}).status_code == 401
    assert cliente.get("/api/preservacion/panel", headers=consulta, params={"fondo_id": str(fondo.id)}).status_code == 403
    assert cliente.get("/api/preservacion/panel", headers=revisor, params={"fondo_id": str(fondo.id)}).status_code == 200
    for ruta, cuerpo in ((f"/api/preservacion/instanciacion/{inst.id}/verificar", None),
                         (f"/api/preservacion/instanciacion/{inst.id}/migrar", {"destino": "pdfa_2b", "aprobada": True})):
        assert cliente.post(ruta, headers=revisor, json=cuerpo).status_code == 403
    assert db.scalars(select(Migracion)).all() == []
