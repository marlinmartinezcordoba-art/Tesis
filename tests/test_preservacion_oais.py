"""
Pruebas del Módulo 5 actualizado (sección 13 del prompt): segunda copia
con verificación independiente y alerta propia, restauración desde ella,
derechos, y el paquete de información de archivo (AIP) en BagIt con los
cuatro conjuntos PREMIS y las cinco categorías de la PDI. Archivos reales,
ingesta real (Siegfried/PRONOM) y migraciones reales (Ghostscript).
"""

import io
import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path

import bagit
import pytest
from lxml import etree
from sqlalchemy import select

from app.core.config import settings
from app.models.alerta import Alerta
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.preservacion import DeclaracionDerechos, Restauracion, SegundaCopia
from app.models.recurso_documental import RecursoDocumental
from app.servicios import almacen, preservacion, segunda_copia
from tests import archivos
from tests.conftest import crear_usuario, ingresar
from tests.test_preservacion import archivista, fondo, herramientas, ingresar_archivo  # noqa: F401  (fixtures)

PREMIS = "{http://www.loc.gov/premis/v3}"


def copia_de(db, inst) -> SegundaCopia:
    db.expire_all()
    return segunda_copia.vigente(db, inst.id)


def alertas_de(db, tipo):
    return db.scalars(select(Alerta).where(Alerta.tipo == tipo, Alerta.atendida_en.is_(None))).all()


def verificar(cliente, cabeceras, inst):
    r = cliente.post(f"/api/preservacion/instanciacion/{inst.id}/verificar", headers=cabeceras)
    assert r.status_code == 200, r.text
    return cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=cabeceras).json()


def expediente_con_documentos(db, fondo, admin, *instanciaciones) -> RecursoDocumental:
    """Fondo → serie → expediente → un documento publicado por cada
    instanciación (RiC-R024 includes y RiC-R025 has or had instantiation)."""
    serie = RecursoDocumental(id=uuid.uuid4(), nivel="serie", titulo="Correspondencia", fondo_id=fondo.id,
                              incluido_en_id=fondo.id, codigo_referencia="CO.AM.01")
    exp = RecursoDocumental(id=uuid.uuid4(), nivel="expediente", titulo="Oficios de 1948", fondo_id=fondo.id,
                            incluido_en_id=serie.id, codigo_referencia="CO.AM.01.003", fechas_extremas="1948")
    db.add_all([serie, exp])
    db.flush()
    for n, inst in enumerate(instanciaciones, 1):
        doc = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo=f"Oficio {113 + n}", fondo_id=fondo.id,
                                incluido_en_id=exp.id, codigo_referencia=f"CO.AM.01.003.{n:03d}",
                                publicado_por_id=admin.id)
        db.add(doc)
        db.flush()
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=doc.id, destino_tipo="instanciacion",
                        destino_id=inst.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                        origen="persona"))
    db.commit()
    return exp


def abrir_paquete(contenido: bytes, destino: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        nombres = z.namelist()
        assert all(not n.startswith("/") and ".." not in n for n in nombres)
        z.extractall(destino)
    [carpeta] = list(destino.iterdir())
    return carpeta


# --- Segunda copia ------------------------------------------------------------------------------


def test_la_segunda_copia_se_crea_sola_en_la_ingesta(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    copia = copia_de(db, inst)
    assert copia is not None and copia.estado == "sincronizada" and copia.motivo == "ingesta"
    lugar = settings.ubicaciones_segunda_copia[0]
    assert copia.ubicacion == str(lugar)
    archivo = segunda_copia.ruta_absoluta(copia)
    assert lugar.resolve() in archivo.parents  # en el segundo lugar, no junto a la primaria
    assert almacen.raiz().resolve() not in archivo.parents
    assert archivo.read_bytes() == almacen.ruta_absoluta(inst.ruta).read_bytes() and copia.huella == inst.huella
    evento = db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "segunda_copia_creada",
                                                       RegistroAuditoria.entidad_id == str(inst.id)))
    assert evento.usuario_id is None  # la creó el sistema, sin acción manual
    d = cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=archivista).json()
    assert d["almacenamiento"]["segunda_copia"]["estado"] == "sincronizada"


def test_verificacion_integra_en_las_dos_copias_no_genera_alerta(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    d = verificar(cliente, archivista, inst)
    assert d["estado_integridad"] == "integra" and d["verificaciones"][0]["segunda_copia"] == "integra"
    assert alertas_de(db, "integridad_alterada") == [] and alertas_de(db, "segunda_copia_alterada") == []


def test_alteracion_solo_de_la_segunda_copia_tiene_alerta_propia_y_se_rehace(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    copia = copia_de(db, inst)
    danada = segunda_copia.ruta_absoluta(copia)
    with open(danada, "ab") as f:
        f.write(b"% alterada en el segundo disco")
    d = verificar(cliente, archivista, inst)
    assert d["estado_integridad"] == "integra"  # la primaria está bien
    assert d["verificaciones"][0]["segunda_copia"] == "alterada"
    assert d["almacenamiento"]["segunda_copia"]["estado"] == "alterada"
    assert alertas_de(db, "integridad_alterada") == []  # no se confunde con la de la primaria
    [alerta] = alertas_de(db, "segunda_copia_alterada")
    assert alerta.entidad_id == str(inst.id) and "segunda copia" in alerta.mensaje
    panel = cliente.get("/api/preservacion/panel", headers=archivista, params={"fondo_id": str(fondo.id)}).json()
    assert panel["resumen"]["alerta_segunda_copia"] == 1 and panel["resumen"]["alerta_integridad"] == 0
    assert d["acciones"] == {"restaurar": False, "reponer_segunda_copia": True}
    # Rehacerla exige aprobación; la copia dañada no se borra.
    url = f"/api/preservacion/instanciacion/{inst.id}/segunda-copia/reponer"
    assert cliente.post(url, headers=archivista, json={"aprobada": False}).status_code == 422
    r = cliente.post(url, headers=archivista, json={"aprobada": True})
    assert r.status_code == 200, r.text
    assert r.json()["almacenamiento"]["segunda_copia"]["estado"] == "sincronizada"
    db.expire_all()
    assert db.get(SegundaCopia, copia.id).estado == "reemplazada" and danada.exists()
    assert alertas_de(db, "segunda_copia_alterada") == []
    # Una segunda copia que desaparece también se reporta con su alerta.
    segunda_copia.ruta_absoluta(copia_de(db, inst)).unlink()
    assert verificar(cliente, archivista, inst)["verificaciones"][0]["segunda_copia"] == "ausente"
    assert len(alertas_de(db, "segunda_copia_alterada")) == 1


def test_alteracion_de_la_primaria_se_restaura_desde_la_segunda_copia(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    primaria = almacen.ruta_absoluta(inst.ruta)
    original = primaria.read_bytes()
    primaria.write_bytes(original + b"% alterada")
    d = verificar(cliente, archivista, inst)
    assert d["estado_integridad"] == "alterada" and d["verificaciones"][0]["segunda_copia"] == "integra"
    [alerta] = alertas_de(db, "integridad_alterada")
    assert "restaurar" in alerta.mensaje and alertas_de(db, "segunda_copia_alterada") == []
    assert d["acciones"]["restaurar"] is True
    url = f"/api/preservacion/instanciacion/{inst.id}/restaurar"
    assert cliente.post(url, headers=archivista, json={"aprobada": False}).status_code == 422
    r = cliente.post(url, headers=archivista, json={"aprobada": True})
    assert r.status_code == 200, r.text
    assert r.json()["estado_integridad"] == "integra" and primaria.read_bytes() == original
    [rest] = db.scalars(select(Restauracion)).all()
    assert rest.estado_previo == "alterada"
    assert almacen.ruta_absoluta(rest.ruta_cuarentena).read_bytes() == original + b"% alterada"  # no se borró
    assert alertas_de(db, "integridad_alterada") == []
    assert db.scalar(select(RegistroAuditoria).where(RegistroAuditoria.accion == "copia_primaria_restaurada"))
    # Sin alerta no hay nada que restaurar.
    assert cliente.post(url, headers=archivista, json={"aprobada": True}).status_code == 409


def test_la_migracion_crea_la_segunda_copia_de_la_nueva(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    copia_original = copia_de(db, original)
    m = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    assert m["estado"] == "completada"
    nueva = db.get(Instanciacion, uuid.UUID(m["nueva_instanciacion"]["id"]))
    copia = copia_de(db, nueva)
    assert copia.motivo == "migracion" and copia.huella == nueva.huella
    assert segunda_copia.ruta_absoluta(copia).read_bytes() == almacen.ruta_absoluta(nueva.ruta).read_bytes()
    assert copia_de(db, original).id == copia_original.id  # la de la original no cambia


def test_cambio_del_lugar_de_la_segunda_copia(cliente, db, fondo, archivista, cabeceras_admin):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    anterior = copia_de(db, inst)
    conf = cliente.get("/api/preservacion/configuracion", headers=cabeceras_admin).json()
    primero, segundo = (str(u) for u in settings.ubicaciones_segunda_copia)
    assert conf["segunda_copia"]["actual"] == primero
    assert [u["ruta"] for u in conf["segunda_copia"]["ubicaciones"]] == [primero, segundo]
    base = {"frecuencia_dias": 30, "formatos": conf["formatos"]}
    # Solo se elige entre los lugares declarados en el servidor.
    for invalida in ("/tmp", str(almacen.raiz())):
        assert cliente.put("/api/preservacion/configuracion", headers=cabeceras_admin,
                           json=base | {"segunda_ubicacion": invalida}).status_code == 422
    r = cliente.put("/api/preservacion/configuracion", headers=cabeceras_admin, json=base | {"segunda_ubicacion": segundo})
    assert r.status_code == 200 and r.json()["segunda_copia"]["actual"] == segundo
    assert r.json()["segunda_copia"]["pendientes"] == 1
    assert preservacion.replicar_pendientes(db) == 1  # lo hace el trabajador
    nueva = copia_de(db, inst)
    assert nueva.ubicacion == segundo and nueva.motivo == "cambio_de_ubicacion"
    assert db.get(SegundaCopia, anterior.id).estado == "reemplazada"
    assert segunda_copia.ruta_absoluta(anterior).exists()  # la del lugar anterior se conserva
    assert preservacion.replicar_pendientes(db) == 0


# --- Derechos -----------------------------------------------------------------------------------


def test_derechos_se_heredan_y_la_declaracion_propia_prevalece(cliente, db, fondo, archivista, admin):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    exp = expediente_con_documentos(db, fondo, admin, inst)
    d = cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=archivista).json()
    assert d["derechos"] is None
    r = cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "recurso_documental", "entidad_id": str(fondo.id), "base": "estatuto", "acceso": "publico",
        "reproduccion": "permitida", "fundamento": "Ley 594 de 2000, art. 27; Ley 1712 de 2014, art. 4"})
    assert r.status_code == 200, r.text
    d = cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=archivista).json()["derechos"]
    assert d["heredada"] and d["nivel"] == "fondo" and d["acceso"] == "publico"
    cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "recurso_documental", "entidad_id": str(exp.id), "base": "estatuto", "acceso": "clasificado",
        "reproduccion": "condicionada", "fundamento": "Ley 1712 de 2014, art. 18 (datos personales)"})
    d = cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=archivista).json()["derechos"]
    assert d["nivel"] == "expediente" and d["acceso"] == "clasificado"  # el nivel más cercano
    cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "instanciacion", "entidad_id": str(inst.id), "base": "estatuto", "acceso": "publico",
        "reproduccion": "permitida", "fundamento": "Ley 1712 de 2014, art. 4 (versión anonimizada)"})
    cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "instanciacion", "entidad_id": str(inst.id), "base": "licencia", "acceso": "publico",
        "reproduccion": "permitida", "fundamento": "CC BY 4.0"})
    d = cliente.get(f"/api/preservacion/instanciacion/{inst.id}", headers=archivista).json()["derechos"]
    assert not d["heredada"] and d["base"] == "licencia"
    # La declaración reemplazada no se borra.
    propias = db.scalars(select(DeclaracionDerechos).where(DeclaracionDerechos.entidad_id == inst.id)).all()
    assert len(propias) == 2 and sum(p.vigente for p in propias) == 1
    assert cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "instanciacion", "entidad_id": str(uuid.uuid4()), "base": "otra", "acceso": "publico",
        "reproduccion": "permitida", "fundamento": "xxx"}).status_code == 404


# --- Paquete de información de archivo ----------------------------------------------------------------


def test_paquete_de_una_instanciacion_es_bagit_valido_con_premis_y_pdi(cliente, db, fondo, archivista, admin, tmp_path):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "Oficio 114 de 1948.pdf", archivos.pdf_con_texto())
    exp = expediente_con_documentos(db, fondo, admin, inst)
    cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "recurso_documental", "entidad_id": str(fondo.id), "base": "estatuto", "acceso": "publico",
        "reproduccion": "permitida", "fundamento": "Ley 594 de 2000, art. 27"})
    verificar(cliente, archivista, inst)
    m = cliente.post(f"/api/preservacion/instanciacion/{inst.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    r = cliente.post(f"/api/preservacion/instanciacion/{inst.id}/exportar-paquete", headers=archivista)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert f"ricora-aip-{inst.id}.zip" in r.headers["content-disposition"]
    bolsa = abrir_paquete(r.content, tmp_path)
    assert bolsa.name == f"ricora-aip-{inst.id}"

    # 1. BagIt válido según el validador de la Library of Congress.
    b = bagit.Bag(str(bolsa))
    b.validate()
    assert b.version == "1.0" and "sha256" in b.algorithms
    assert b.info["External-Identifier"] == f"urn:uuid:{inst.id}"

    # 2. Información de Contenido: el archivo, byte a byte.
    contenido = bolsa / "data" / "contenido" / "Oficio 114 de 1948.pdf"
    assert contenido.read_bytes() == almacen.ruta_absoluta(inst.ruta).read_bytes()

    # 3. PREMIS: Objeto, Eventos, Agentes y Derechos, en ese orden.
    if os.getenv("RICORA_PREMIS_MUESTRA"):  # la integración continua lo valida contra el esquema oficial
        shutil.copyfile(bolsa / "data" / "metadatos" / "premis.xml", os.environ["RICORA_PREMIS_MUESTRA"])
    raiz = etree.parse(str(bolsa / "data" / "metadatos" / "premis.xml")).getroot()
    assert raiz.tag == f"{PREMIS}premis" and raiz.get("version") == "3.0"
    orden = [etree.QName(h).localname for h in raiz]
    assert orden == sorted(orden, key=["object", "event", "agent", "rights"].index)
    assert set(orden) == {"object", "event", "agent", "rights"}
    [obj] = raiz.findall(f"{PREMIS}object")
    assert obj.get("{http://www.w3.org/2001/XMLSchema-instance}type") == "premis:file"
    t = lambda el, ruta: el.findtext(ruta.replace("p:", PREMIS))  # noqa: E731
    assert t(obj, "p:objectIdentifier/p:objectIdentifierValue") == str(inst.id)
    assert t(obj, "p:objectCharacteristics/p:fixity/p:messageDigestAlgorithm") == "SHA-256"
    assert t(obj, "p:objectCharacteristics/p:fixity/p:messageDigest") == inst.huella
    assert t(obj, "p:objectCharacteristics/p:size") == str(inst.tamano_bytes)
    assert t(obj, "p:objectCharacteristics/p:format/p:formatRegistry/p:formatRegistryKey") == inst.formato_puid
    assert t(obj, "p:originalName") == "Oficio 114 de 1948.pdf"
    almacenes = [s.findtext(f"{PREMIS}storageMedium") for s in obj.findall(f"{PREMIS}storage")]
    assert len(almacenes) == 2 and almacenes[0].startswith("Copia primaria") and almacenes[1].startswith("Segunda copia")
    assert t(obj, "p:relationship/p:relationshipSubType") == "is source of"  # la migrada a PDF/A
    eventos = raiz.findall(f"{PREMIS}event")
    tipos = [t(e, "p:eventType") for e in eventos]
    for tipo in ("ingestion", "message digest calculation", "format identification", "replication", "fixity check",
                 "migration", "information package creation"):
        assert tipo in tipos, tipo
    for e in eventos:  # cada evento con fecha, resultado, agente y objeto
        # Términos del diccionario PREMIS, en inglés (hallazgo PRE-02).
        assert t(e, "p:eventDateTime") and t(e, "p:eventOutcomeInformation/p:eventOutcome") in (
            "success", "failure", "warning")
        assert e.findall(f"{PREMIS}linkingAgentIdentifier") and e.findall(f"{PREMIS}linkingObjectIdentifier")
    migracion = eventos[tipos.index("migration")]
    roles = {t(a, "p:linkingAgentRole"): t(a, "p:linkingAgentIdentifierType")
             for a in migracion.findall(f"{PREMIS}linkingAgentIdentifier")}
    # Quien ejecutó la migración es el mecanismo del vocabulario del fondo
    # (RiC-E13), identificado por su registro, no por un nombre suelto.
    # La persona también es un agente del vocabulario del fondo, no una cuenta (hallazgo PRE-04).
    assert roles == {"authorizer": "RICORA vocabulario", "executing program": "RICORA vocabulario"}
    objetos = {t(o, "p:linkingObjectRole"): t(o, "p:linkingObjectIdentifierValue")
               for o in migracion.findall(f"{PREMIS}linkingObjectIdentifier")}
    assert objetos == {"source": str(inst.id), "outcome": m["nueva_instanciacion"]["id"]}
    # Los eventos que enlaza el objeto son exactamente los del archivo.
    enlazados = {t(x, "p:linkingEventIdentifierValue") for x in obj.findall(f"{PREMIS}linkingEventIdentifier")}
    assert enlazados == {t(e, "p:eventIdentifier/p:eventIdentifierValue") for e in eventos}
    agentes = {t(a, "p:agentType"): t(a, "p:agentName") for a in raiz.findall(f"{PREMIS}agent")}
    assert agentes["person"] == "Catalina Torres" and "software" in agentes
    nombres_software = [t(a, "p:agentName") for a in raiz.findall(f"{PREMIS}agent") if t(a, "p:agentType") == "software"]
    assert any("siegfried" in n.lower() for n in nombres_software)
    assert any("Ghostscript" in n for n in nombres_software)
    for a in raiz.findall(f"{PREMIS}agent"):
        if t(a, "p:agentType") == "software":  # cada programa con su versión exacta (PREMIS 3 agentVersion)
            assert t(a, "p:agentIdentifier/p:agentIdentifierType") == "RICORA vocabulario" and t(a, "p:agentVersion")
    [derecho] = raiz.findall(f"{PREMIS}rights/{PREMIS}rightsStatement")
    assert t(derecho, "p:rightsBasis") == "Statute"
    assert t(derecho, "p:statuteInformation/p:statuteCitation") == "Ley 594 de 2000, art. 27"
    assert {t(g, "p:act"): t(g, "p:restriction") for g in derecho.findall(f"{PREMIS}rightsGranted")} == {
        "disseminate": "Allow", "replicate": "Allow"}

    # 4. PDI: las cinco categorías de OAIS, pobladas desde lo que sabe el sistema.
    datos = json.loads((bolsa / "data" / "metadatos" / "pdi.json").read_text(encoding="utf-8"))
    rep = datos["informacion_de_contenido"]["informacion_de_representacion"]
    assert rep["puid"] == inst.formato_puid and rep["registro"] == "PRONOM"
    assert datos["informacion_de_contenido"]["objeto_de_datos"] == "contenido/Oficio 114 de 1948.pdf"
    pdi = datos["informacion_de_descripcion_de_preservacion"]
    assert list(pdi) == ["referencia", "contexto", "procedencia", "fijeza", "derechos_de_acceso"]
    assert pdi["referencia"]["identificador"] == str(inst.id)
    assert pdi["referencia"]["codigos_de_referencia"] == ["CO.AM.01.003.001"]
    [rr] = pdi["contexto"]["record_resources"]
    assert [n["nivel"] for n in rr["jerarquia"]] == ["fondo", "serie", "expediente", "unidad_documental"]
    assert rr["jerarquia"][2]["id"] == str(exp.id) and "RiC-R025" in rr["relacion"]
    assert pdi["contexto"]["migrada_a"][0]["id"] == m["nueva_instanciacion"]["id"]
    assert [e["tipo"] for e in pdi["procedencia"]["eventos"]] == tipos
    assert pdi["fijeza"]["valor"] == inst.huella and pdi["fijeza"]["segunda_copia"]["estado"] == "sincronizada"
    assert pdi["fijeza"]["verificaciones"][0]["segunda_copia"] == "integra"
    assert pdi["derechos_de_acceso"]["declaracion"]["fundamento"] == "Ley 594 de 2000, art. 27"
    assert (bolsa / "data" / "LEEME.txt").read_text(encoding="utf-8").startswith("PAQUETE DE INFORMACIÓN DE ARCHIVO")

    # 5. Un byte cambiado en el paquete lo invalida (el manifiesto sirve).
    with open(contenido, "ab") as f:
        f.write(b"x")
    with pytest.raises(bagit.BagValidationError):
        bagit.Bag(str(bolsa)).validate()
    # Y no queda nada temporal en el almacenamiento.
    assert list((almacen.raiz() / ".temporal").glob("aip-*")) == []


def test_paquete_del_expediente_incluye_todas_sus_instanciaciones(cliente, db, fondo, archivista, admin, tmp_path):
    a = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto("uno"))
    b = ingresar_archivo(cliente, db, archivista, fondo, "plano.png", archivos.png_con_texto())
    c = ingresar_archivo(cliente, db, archivista, fondo, "acta.txt", archivos.txt("tres"))
    exp = expediente_con_documentos(db, fondo, admin, a, b)
    # c está en otro expediente: no debe aparecer.
    expediente_con_documentos(db, fondo, admin, c)
    # La migración de a (aún sin publicar con su documento) también entra.
    m = cliente.post(f"/api/preservacion/instanciacion/{a.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    r = cliente.post(f"/api/preservacion/expediente/{exp.id}/exportar-paquete", headers=archivista)
    assert r.status_code == 200, r.text
    bolsa = abrir_paquete(r.content, tmp_path)
    bagit.Bag(str(bolsa)).validate()
    indice = json.loads((bolsa / "data" / "expediente.json").read_text(encoding="utf-8"))
    esperadas = {str(a.id), str(b.id), m["nueva_instanciacion"]["id"]}
    assert {i["id"] for i in indice["instanciaciones"]} == esperadas and indice["total"] == 3
    assert indice["expediente"]["codigo_referencia"] == "CO.AM.01.003"
    for i in indice["instanciaciones"]:
        carpeta = bolsa / "data" / i["carpeta"]
        assert (carpeta / "metadatos" / "premis.xml").exists() and (carpeta / "metadatos" / "pdi.json").exists()
        [archivo] = list((carpeta / "contenido").iterdir())
        assert bagit.hashlib.sha256(archivo.read_bytes()).hexdigest() == i["huella"]
    exportados = db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "paquete_exportado")).all()
    assert {e.entidad_id for e in exportados} == esperadas
    # Solo al nivel de expediente.
    assert cliente.post(f"/api/preservacion/expediente/{fondo.id}/exportar-paquete", headers=archivista).status_code == 422
    assert cliente.post(f"/api/preservacion/expediente/{uuid.uuid4()}/exportar-paquete",
                        headers=archivista).status_code == 404


def test_no_se_empaqueta_un_archivo_alterado(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    with open(almacen.ruta_absoluta(inst.ruta), "ab") as f:
        f.write(b"% alterada")
    r = cliente.post(f"/api/preservacion/instanciacion/{inst.id}/exportar-paquete", headers=archivista)
    assert r.status_code == 409 and "huella" in r.json()["detail"]
    assert db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "paquete_exportado")).all() == []


def test_permisos_de_las_acciones_nuevas(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    crear_usuario(db, "julian@correo.com", "revisor")
    revisor = ingresar(cliente, "julian@correo.com")
    for ruta, cuerpo in ((f"/api/preservacion/instanciacion/{inst.id}/exportar-paquete", None),
                         (f"/api/preservacion/expediente/{uuid.uuid4()}/exportar-paquete", None),
                         (f"/api/preservacion/instanciacion/{inst.id}/restaurar", {"aprobada": True}),
                         (f"/api/preservacion/instanciacion/{inst.id}/segunda-copia/reponer", {"aprobada": True})):
        assert cliente.post(ruta, headers=revisor, json=cuerpo).status_code == 403, ruta
        assert cliente.post(ruta, json=cuerpo).status_code == 401, ruta
    assert cliente.put("/api/preservacion/derechos", headers=revisor, json={}).status_code == 403
    # La configuración del segundo lugar, solo el administrador.
    assert cliente.put("/api/preservacion/configuracion", headers=archivista,
                       json={"frecuencia_dias": 30, "formatos": [], "segunda_ubicacion": "/tmp"}).status_code == 403
