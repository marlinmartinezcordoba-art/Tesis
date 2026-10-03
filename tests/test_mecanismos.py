"""
Mecanismos reutilizados (prompt de vocabularios v2 §3 y de preservación
v2.2 §6 y §13): cada acción técnica apunta al agente mecanismo (RiC-E13)
del vocabulario del fondo, con su versión exacta, y nunca a un nombre de
programa guardado como texto libre.
"""

import io
import subprocess
import uuid
import zipfile

from lxml import etree
from sqlalchemy import func, select

from app.core.config import settings
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import Actividad, EntidadVocabulario, Fecha, Relacion
from app.models.instanciacion import Instanciacion
from app.models.preservacion import Migracion, SegundaCopia, VerificacionIntegridad
from app.models.recurso_documental import RecursoDocumental
from app.servicios import mecanismos, motor, preservacion, vocabulario
from tests import archivos
from tests.test_descripcion import RESPUESTA_UNO, MotorDePrueba, aceptar_todo, archivista, documento, fondo, iniciar  # noqa: F401
from tests.test_preservacion import describir, herramientas, ingresar_archivo  # noqa: F401

PREMIS = "{http://www.loc.gov/premis/v3}"


def mecanismos_del_fondo(db, fondo, nombre=None):
    consulta = select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fondo.id,
                                                EntidadVocabulario.subtipo == "mecanismo")
    if nombre:
        consulta = consulta.where(EntidadVocabulario.nombre.ilike(f"{nombre}%"))
    return db.scalars(consulta).all()


def test_migracion_automatica_queda_vinculada_a_ghostscript_con_su_version_exacta(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "Oficio_114.pdf", archivos.pdf_con_texto())
    describir(db, fondo, original)
    r = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True})
    assert r.status_code == 200, r.text
    m = db.get(Migracion, uuid.UUID(r.json()["id"]))
    version = subprocess.run([settings.ghostscript_binario, "--version"], capture_output=True).stdout.decode().strip()
    gs = db.get(EntidadVocabulario, m.mecanismo_id)
    # El agente es el registro del vocabulario: subtipo mecanismo, con la versión exacta del programa.
    assert gs.clase == "agente" and gs.subtipo == "mecanismo" and gs.fondo_id == fondo.id
    assert gs.version == version and gs.nombre == f"Ghostscript {version}"
    # En la migración no queda el nombre del programa como texto: solo lo que hizo.
    assert m.herramienta is None and m.parametros == "pdfwrite, PDF/A-2b, perfil sRGB"
    assert r.json()["mecanismo"] == {"id": str(gs.id), "nombre": gs.nombre, "version": version}
    # Lo creó el servicio único de vocabularios, con su propio evento de auditoría.
    assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "mecanismo_registrado",
                                                     RegistroAuditoria.entidad_id == str(gs.id)))
    completada = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "migracion_completada",
                                                           RegistroAuditoria.entidad_id == str(original.id)))
    assert completada.valor_nuevo["mecanismo_id"] == str(gs.id)

    # Una segunda migración reutiliza el mismo mecanismo: nunca un duplicado.
    otro = ingresar_archivo(cliente, db, archivista, fondo, "Oficio_115.pdf", archivos.pdf_con_texto("Oficio 115"))
    r2 = cliente.post(f"/api/preservacion/instanciacion/{otro.id}/migrar", headers=archivista,
                      json={"destino": "pdfa_2b", "aprobada": True}).json()
    assert r2["mecanismo"]["id"] == str(gs.id)
    assert len(mecanismos_del_fondo(db, fondo, "Ghostscript")) == 1

    # En el paquete PREMIS, el agente que ejecutó la migración es ese mismo registro, con su versión.
    paquete = cliente.post(f"/api/preservacion/instanciacion/{original.id}/exportar-paquete", headers=archivista)
    with zipfile.ZipFile(io.BytesIO(paquete.content)) as z:
        premis = etree.fromstring(z.read(next(n for n in z.namelist() if n.endswith("premis.xml"))))
    evento = next(e for e in premis.findall(f"{PREMIS}event") if e.findtext(f"{PREMIS}eventType") == "migration")
    ejecutor = next(a for a in evento.findall(f"{PREMIS}linkingAgentIdentifier")
                    if a.findtext(f"{PREMIS}linkingAgentRole") == "executing program")
    assert ejecutor.findtext(f"{PREMIS}linkingAgentIdentifierValue") == str(gs.id)
    agente = next(a for a in premis.findall(f"{PREMIS}agent")
                  if a.findtext(f"{PREMIS}agentIdentifier/{PREMIS}agentIdentifierValue") == str(gs.id))
    assert agente.findtext(f"{PREMIS}agentVersion") == version


def test_un_mecanismo_ya_registrado_en_el_vocabulario_se_reutiliza(cliente, db, fondo, archivista):
    version = subprocess.run([settings.ghostscript_binario, "--version"], capture_output=True).stdout.decode().strip()
    previo = vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="Ghostscript", version=version)
    db.commit()
    original = ingresar_archivo(cliente, db, archivista, fondo, "Oficio_114.pdf", archivos.pdf_con_texto())
    r = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    assert r["mecanismo"]["id"] == str(previo.id)


def test_migracion_manual_no_inventa_un_mecanismo(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "Oficio_114.pdf", archivos.pdf_con_texto())
    r = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "odt", "aprobada": True}).json()
    assert r["estado"] == "esperando_archivo" and r["mecanismo"] is None


def test_identificacion_verificacion_y_segunda_copia_apuntan_a_su_mecanismo(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "Oficio_114.pdf", archivos.pdf_con_texto())
    sf = db.get(EntidadVocabulario, inst.mecanismo_identificacion_id)
    # Siegfried, con la versión del programa y la de sus firmas PRONOM.
    assert sf.subtipo == "mecanismo" and sf.nombre.startswith("Siegfried ") and "firmas" in sf.version
    cliente.post(f"/api/preservacion/instanciacion/{inst.id}/verificar", headers=archivista)
    v = db.scalar(select(VerificacionIntegridad).where(VerificacionIntegridad.instanciacion_id == inst.id))
    sistema = db.get(EntidadVocabulario, v.mecanismo_id)
    assert sistema.nombre == f"{settings.nombre_sistema} {mecanismos.VERSION_SISTEMA}"
    copia = db.scalar(select(SegundaCopia).where(SegundaCopia.instanciacion_id == inst.id))
    assert copia.mecanismo_id == sistema.id
    d = cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=archivista).json()
    assert d["formato"]["mecanismo"]["id"] == str(sf.id)
    # La ficha del mecanismo muestra lo que hizo en el sistema.
    ficha = cliente.get(f"/api/vocabulario/{sistema.id}", headers=archivista).json()["ficha"]
    assert ficha["usos_tecnicos"]["verificaciones_integridad"] >= 1 and ficha["usos_tecnicos"]["segundas_copias"] == 1


def test_lo_que_propone_el_motor_queda_vinculado_a_su_mecanismo(cliente, db, fondo, archivista, monkeypatch):
    m = MotorDePrueba(RESPUESTA_UNO)
    monkeypatch.setattr(motor, "motor_activo", lambda: m)
    doc = documento(db, fondo, "a.pdf", "Oficio de la Alcaldía de Tunja al Concejo, 3 de marzo de 1948.")
    espacio = iniciar(cliente, archivista, [doc.id])
    r = cliente.post("/api/descripcion/publicar", headers=archivista, json=aceptar_todo(espacio))
    assert r.status_code == 201, r.text
    [mec] = mecanismos_del_fondo(db, fondo, "Motor de análisis")
    assert mec.version == m.nombre
    # Nada de lo propuesto por el motor queda solo con el nombre en texto.
    for modelo in (EntidadVocabulario, Relacion, Fecha, Actividad, RecursoDocumental):
        sueltos = db.scalar(select(func.count()).select_from(modelo).where(modelo.motor.is_not(None),
                                                                          modelo.motor_id.is_(None)))
        assert sueltos == 0, modelo.__tablename__
    recurso = db.get(RecursoDocumental, uuid.UUID(r.json()["id"]))
    assert recurso.motor_id == mec.id
    assert db.scalar(select(func.count()).select_from(Relacion).where(Relacion.motor_id == mec.id)) > 0
    decisiones = db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "decision_ia")).all()
    assert decisiones and all(d.valor_nuevo["mecanismo_id"] == str(mec.id) for d in decisiones)


def test_fusionar_dos_mecanismos_mueve_sus_acciones_tecnicas(cliente, db, fondo, archivista, admin):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "Oficio_114.pdf", archivos.pdf_con_texto())
    sf = db.get(EntidadVocabulario, inst.mecanismo_identificacion_id)
    # Una archivista lo había registrado a mano con otro nombre y la misma versión.
    a_mano = vocabulario.mecanismo(db, fondo_id=fondo.id, nombre="sf (Siegfried)", version=sf.version)
    db.commit()
    vocabulario.fusionar(db, definitiva=a_mano, absorbida=sf, usuario_id=admin.id)
    db.commit()
    db.expire_all()
    assert db.get(Instanciacion, inst.id).mecanismo_identificacion_id == a_mano.id
    # Lo que se registre después también va a la definitiva.
    assert mecanismos.de_identificacion(db, fondo.id, inst.herramienta_identificacion).id == a_mano.id


def test_las_filas_anteriores_se_vinculan_sin_borrar_su_texto(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "Oficio_114.pdf", archivos.pdf_con_texto())
    # Como quedaron antes de la migración 0013: con el programa en texto y sin mecanismo.
    inst.mecanismo_identificacion_id = None
    db.add(Migracion(instanciacion_origen_id=inst.id, destino="pdfa_2b", destino_nombre="PDF/A-2b", modo="automatica",
                     estado="completada", herramienta="Ghostscript 9.56.1 (pdfwrite, PDF/A-2b, perfil sRGB)",
                     aprobada_por_id=inst.cargado_por_id))
    vieja = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo="Oficio", fondo_id=fondo.id,
                              incluido_en_id=fondo.id, motor="gemini-1.5-flash")
    db.add(vieja)
    db.commit()
    assert mecanismos.vincular_anteriores(db) >= 3
    db.commit()
    db.expire_all()
    m = db.scalar(select(Migracion).where(Migracion.herramienta.is_not(None)))
    gs = db.get(EntidadVocabulario, m.mecanismo_id)
    assert gs.nombre == "Ghostscript 9.56.1" and gs.version == "9.56.1" and m.parametros == "pdfwrite, PDF/A-2b, perfil sRGB"
    assert m.herramienta.startswith("Ghostscript")  # lo que se vio entonces no se borra
    assert db.get(Instanciacion, inst.id).mecanismo_identificacion_id is not None
    assert db.get(EntidadVocabulario, db.get(RecursoDocumental, vieja.id).motor_id).version == "gemini-1.5-flash"
    assert mecanismos.vincular_anteriores(db) == 0  # idempotente


def test_separar_y_version_de_siegfried():
    assert mecanismos.separar("Ghostscript 10.02.1 (pdfwrite, PDF/A-2b)") == ("Ghostscript", "10.02.1", "pdfwrite, PDF/A-2b")
    assert mecanismos.separar("Pillow 11.0.0 (TIFF)") == ("Pillow", "11.0.0", "TIFF")
    assert mecanismos.separar("Conversión externa, cargada por la archivista") is None
    assert mecanismos.version_siegfried(
        "siegfried 1.11.9 · PRONOM DROID_SignatureFile_V125.xml; container-signature-20260119.xml") == (
        "Siegfried", "1.11.9 (firmas DROID_SignatureFile_V125, container-signature-20260119)")
    assert preservacion.Ejecucion("Ghostscript", "10", "x").programa == "Ghostscript"
