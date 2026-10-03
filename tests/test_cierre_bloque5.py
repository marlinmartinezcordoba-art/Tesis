"""
Cierre del bloque 5 de la auditoría RiC (Preservación): PRE-01, PRE-02,
PRE-04, PRE-06, PRE-09, PRE-12, PRE-13 y PRE-14.

Herramientas reales, sin simulaciones: veraPDF y JHOVE (Java), ClamAV con
una firma propia de la cadena de prueba EICAR (las firmas oficiales pesan
cerca de 1 GB y no hacen falta para probar el flujo), Ghostscript, Pillow,
Tesseract y Siegfried.
"""

import hashlib
import io
import os
import subprocess
import uuid
import zipfile

import pytest
from lxml import etree
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.db.base import ahora
from app.models.alerta import Alerta
from app.models.descripcion import EntidadVocabulario, IdentificadorEntidad, Relacion
from app.models.instanciacion import Instanciacion
from app.models.preservacion import ComprobacionTecnica
from app.models.recurso_documental import RecursoDocumental
from app.servicios import almacen, comprobaciones, mecanismos, parametros, preservacion, procesamiento, recorte
from tests import archivos
from tests.test_preservacion import archivista, fondo, herramientas, ingresar_archivo  # noqa: F401  (fixtures)

PREMIS = "{http://www.loc.gov/premis/v3}"
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@pytest.fixture(scope="module", autouse=True)
def validadores():
    """Exigen veraPDF, JHOVE y ClamAV: si faltan, fallan (no se saltan)."""
    assert (os.path.isdir(os.path.join(settings.directorio_validadores, "lib"))
            and os.path.exists(os.path.join(settings.directorio_validadores, "jhove.conf"))), \
        "Faltan veraPDF y JHOVE (RICORA_VALIDADORES)."
    assert subprocess.run([settings.clamscan, "--version"], capture_output=True).returncode == 0, "Falta ClamAV."


def premis_de(cliente, cabeceras, inst) -> etree._Element:
    r = cliente.get(f"/api/preservacion/instanciacion/{inst.id}/premis", headers=cabeceras)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/xml")
    return etree.fromstring(r.content)


def t(el, ruta):
    return el.findtext(ruta.replace("p:", PREMIS))


def muestra(raiz, nombre: str) -> None:
    """La integración continua valida estas muestras contra el esquema
    oficial PREMIS 3.0 (scripts/validar_premis.py): un evento nuevo que no
    valide rompe la CI."""
    carpeta = os.getenv("RICORA_PREMIS_MUESTRAS")
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
        with open(os.path.join(carpeta, f"premis-{nombre}.xml"), "wb") as f:
            f.write(etree.tostring(raiz, xml_declaration=True, encoding="UTF-8"))


def eventos(raiz) -> dict[str, list]:
    salida: dict[str, list] = {}
    for e in raiz.findall(f"{PREMIS}event"):
        salida.setdefault(t(e, "p:eventType"), []).append(e)
    return salida


def publicar(db, fondo, *instancias, titulo="Oficio 114") -> RecursoDocumental:
    r = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo=titulo, fondo_id=fondo.id,
                          incluido_en_id=fondo.id, publicado_en=ahora(), codigo_referencia="CO.AM.01.114")
    db.add(r)
    db.flush()
    for inst in instancias:
        db.add(Relacion(origen_tipo="recurso_documental", origen_id=r.id, destino_tipo="instanciacion",
                        destino_id=inst.id, tipo_relacion="asociacion", codigo_ric="has_or_had_instantiation",
                        origen="persona"))
    db.commit()
    return r


def tiff() -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", (300, 200), (120, 140, 160)).save(salida, format="TIFF", compression="tiff_lzw")
    return salida.getvalue()


# --- PRE-01 · PREMIS por API, sin zip, con el esquema fijado ---------------------------------------


def test_premis_de_una_instanciacion_por_api_con_esquema_fijado(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "Oficio 114.pdf", archivos.pdf_con_texto())
    raiz = premis_de(cliente, archivista, inst)
    assert raiz.tag == f"{PREMIS}premis" and raiz.get("version") == "3.0"
    ubicacion = raiz.get("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation")
    assert ubicacion.endswith("/premis-v3-0.xsd")  # versión fijada, no «premis.xsd» (que cambia)
    assert [etree.QName(h).localname for h in raiz][:2] == ["object", "event"]
    assert t(raiz, "p:object/p:objectIdentifier/p:objectIdentifierValue") == str(inst.id)
    # Solo con permiso del módulo de preservación.
    assert cliente.get(f"/api/preservacion/instanciacion/{inst.id}/premis").status_code == 401


# --- PRE-02 · Hora exacta de cada paso, resultado en el vocabulario PREMIS y OCR ------------------


def test_eventos_de_ingesta_con_hora_por_paso_y_extraccion_de_texto(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.png", archivos.png_con_texto())
    db.refresh(inst)
    assert inst.origen_texto == "ocr"
    # Cada paso guarda su hora: ya no comparten la del final del proceso.
    assert inst.cargado_en <= inst.huella_en <= inst.formato_en <= inst.texto_en <= inst.procesado_en
    assert len({inst.huella_en, inst.formato_en, inst.texto_en}) == 3
    raiz = premis_de(cliente, archivista, inst)
    ev = eventos(raiz)
    fecha = lambda tipo: t(ev[tipo][0], "p:eventDateTime")  # noqa: E731
    assert fecha("message digest calculation") == inst.huella_en.isoformat(timespec="microseconds")
    assert fecha("format identification") == inst.formato_en.isoformat(timespec="microseconds")
    # El OCR es un evento PREMIS «metadata extraction» con Tesseract y su versión exacta.
    [ocr] = ev["metadata extraction"]
    assert fecha("metadata extraction") == inst.texto_en.isoformat(timespec="microseconds")
    assert "OCR" in t(ocr, "p:eventDetailInformation/p:eventDetail")
    assert t(ocr, "p:eventOutcomeInformation/p:eventOutcome") in ("success", "warning")
    assert "Confianza media del OCR" in t(ocr, "p:eventOutcomeInformation/p:eventOutcomeDetail/p:eventOutcomeDetailNote")
    programa = t(ocr, "p:linkingAgentIdentifier/p:linkingAgentIdentifierValue")
    agente = next(a for a in raiz.findall(f"{PREMIS}agent")
                  if t(a, "p:agentIdentifier/p:agentIdentifierValue") == programa)
    assert t(agente, "p:agentName").startswith("Tesseract") and "(spa)" in t(agente, "p:agentVersion")
    assert db.get(EntidadVocabulario, uuid.UUID(programa)).subtipo == "mecanismo"
    # Todos los resultados en los términos del diccionario PREMIS, en inglés.
    resultados = {t(e, "p:eventOutcomeInformation/p:eventOutcome") for e in raiz.findall(f"{PREMIS}event")}
    assert resultados <= {"success", "failure", "warning", "pending"}
    muestra(raiz, "ocr")


def test_capa_de_texto_del_pdf_tambien_es_un_evento(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    [e] = eventos(premis_de(cliente, archivista, inst))["metadata extraction"]
    assert "capa de texto" in t(e, "p:eventDetailInformation/p:eventDetail")
    assert mecanismos.etiqueta(db, db.get(Instanciacion, inst.id).mecanismo_texto_id, "").startswith("pypdfium2")


# --- PRE-04 · La persona es el agente del vocabulario del fondo -----------------------------------


def test_la_persona_del_premis_es_un_agente_persona_del_vocabulario(cliente, db, fondo, archivista):
    a = ingresar_archivo(cliente, db, archivista, fondo, "a.pdf", archivos.pdf_con_texto())
    b = ingresar_archivo(cliente, db, archivista, fondo, "b.pdf", archivos.pdf_con_texto("Otro oficio de 1949."))
    personas = {}
    for inst in (a, b):
        raiz = premis_de(cliente, archivista, inst)
        [ingreso] = eventos(raiz)["ingestion"]
        roles = {t(x, "p:linkingAgentRole"): (t(x, "p:linkingAgentIdentifierType"), t(x, "p:linkingAgentIdentifierValue"))
                 for x in ingreso.findall(f"{PREMIS}linkingAgentIdentifier")}
        tipo, valor = roles["implementer"]
        assert tipo == "RICORA vocabulario"
        [persona] = [x for x in raiz.findall(f"{PREMIS}agent") if t(x, "p:agentType") == "person"]
        assert t(persona, "p:agentName") == "Catalina Torres"
        personas[inst.id] = valor
    # Un solo agente para la misma persona en todo el fondo, con su vínculo a la cuenta.
    assert len(set(personas.values())) == 1
    e = db.get(EntidadVocabulario, uuid.UUID(next(iter(personas.values()))))
    assert (e.clase, e.subtipo, e.fondo_id) == ("agente", "persona", fondo.id)
    [ident] = db.scalars(select(IdentificadorEntidad).where(IdentificadorEntidad.entidad_id == e.id)).all()
    assert ident.esquema == "interno" and ident.valor == f"usuario:{a.cargado_por_id}"


# --- PRE-06 · El recorte se crea (no ingresa) y tiene su fuente ------------------------------------


def test_recorte_tiene_evento_de_creacion_con_pillow_y_relacion_con_su_fuente(cliente, db, fondo, archivista):
    origen = ingresar_archivo(cliente, db, archivista, fondo, "oficio.png", archivos.png_con_texto())
    rec = recorte.recortar(db, origen, {"pagina": 1, "x": 0.1, "y": 0.1, "ancho": 0.5, "alto": 0.4}, "Sello",
                           origen.cargado_por_id)
    db.commit()
    raiz = premis_de(cliente, archivista, rec)
    muestra(raiz, "recorte")
    ev = eventos(raiz)
    assert "ingestion" not in ev  # ya no afirma un ingreso que no ocurrió
    [creacion] = ev["creation"]
    objetos = {t(o, "p:linkingObjectRole"): t(o, "p:linkingObjectIdentifierValue")
               for o in creacion.findall(f"{PREMIS}linkingObjectIdentifier")}
    assert objetos == {"source": str(origen.id), "outcome": str(rec.id)}
    roles = {t(x, "p:linkingAgentRole"): t(x, "p:linkingAgentIdentifierValue")
             for x in creacion.findall(f"{PREMIS}linkingAgentIdentifier")}
    pillow = db.get(EntidadVocabulario, uuid.UUID(roles["executing program"]))
    assert pillow.nombre == f"Pillow {Image.__version__}" and pillow.version == Image.__version__
    assert db.get(EntidadVocabulario, uuid.UUID(roles["implementer"])).subtipo == "persona"
    relacion = raiz.find(f"{PREMIS}object/{PREMIS}relationship")
    assert (t(relacion, "p:relationshipType"), t(relacion, "p:relationshipSubType")) == ("derivation", "has source")
    assert t(relacion, "p:relatedObjectIdentifier/p:relatedObjectIdentifierValue") == str(origen.id)
    # Y el original sabe que es fuente del recorte.
    fuente = premis_de(cliente, archivista, origen).find(f"{PREMIS}object/{PREMIS}relationship")
    assert t(fuente, "p:relationshipSubType") == "is source of"
    assert t(fuente, "p:relatedObjectIdentifier/p:relatedObjectIdentifierValue") == str(rec.id)


# --- PRE-09 · veraPDF y JHOVE; el riesgo bajo depende de la validación -------------------------------


def test_migracion_a_pdfa_se_valida_con_verapdf_y_queda_en_el_premis(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "Oficio 114.pdf", archivos.pdf_con_texto())
    m = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    nueva = db.get(Instanciacion, uuid.UUID(m["nueva_instanciacion"]["id"]))
    v = comprobaciones.ultima(db, nueva.id, "validacion")
    assert (v.herramienta, v.resultado, v.origen) == ("veraPDF", "conforme", "migracion"), v.resumen
    assert "PDF/A-2B" in v.perfil.upper()
    assert m["nueva_instanciacion"]["riesgo"]["nivel"] == "bajo"
    assert "veraPDF" in m["nueva_instanciacion"]["riesgo"]["razon"]
    raiz = premis_de(cliente, archivista, nueva)
    muestra(raiz, "validacion")
    [validacion] = eventos(raiz)["validation"]
    assert t(validacion, "p:eventOutcomeInformation/p:eventOutcome") == "success"
    programa = db.get(EntidadVocabulario, uuid.UUID(t(validacion, "p:linkingAgentIdentifier/p:linkingAgentIdentifierValue")))
    assert programa.nombre.startswith("veraPDF 1.") and programa.version.startswith("1.")


def test_pdf_que_solo_declara_ser_pdfa_no_es_riesgo_bajo(cliente, db, fondo, archivista, tmp_path):
    """Ghostscript sin perfil de color (OutputIntent) produce un archivo que
    Siegfried reconoce como PDF/A-2b por su XMP, pero que incumple ISO 19005."""
    entrada, salida = tmp_path / "a.pdf", tmp_path / "b.pdf"
    entrada.write_bytes(archivos.pdf_con_texto())
    subprocess.run([settings.ghostscript_binario, "-q", "-dPDFA=2", "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE",
                    "-dPDFACompatibilityPolicy=1", "-sColorConversionStrategy=RGB", "-sDEVICE=pdfwrite",
                    f"-sOutputFile={salida}", str(entrada)], check=True, capture_output=True)
    inst = ingresar_archivo(cliente, db, archivista, fondo, "declara-pdfa.pdf", salida.read_bytes())
    assert inst.formato_puid == "fmt/477"
    v = comprobaciones.ultima(db, inst.id, "validacion")
    assert (v.resultado, v.origen) == ("no_conforme", "ingesta")
    assert any(r["clausula"] for r in v.detalle["reglas_incumplidas"])
    riesgo = preservacion.riesgo_de(db, inst)
    assert riesgo["nivel"] == "medio" and "validación formal" in riesgo["razon"]
    alerta = db.scalar(select(Alerta).where(Alerta.tipo == "validacion_formato_fallida", Alerta.entidad_id == str(inst.id)))
    assert alerta is not None and alerta.modulo == "preservacion"
    [validacion] = eventos(premis_de(cliente, archivista, inst))["validation"]
    assert t(validacion, "p:eventOutcomeInformation/p:eventOutcome") == "failure"


def test_tiff_se_valida_con_jhove(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "plano.tif", tiff())
    v = comprobaciones.ultima(db, inst.id, "validacion")
    assert (v.herramienta, v.resultado, v.perfil) == ("JHOVE", "conforme", "TIFF-hul"), v.resumen
    assert preservacion.riesgo_de(db, inst)["nivel"] == "bajo"
    # El mismo archivo dañado (truncado) ya no es válido ni de riesgo bajo.
    ruta = almacen.ruta_absoluta(inst.ruta)
    ruta.write_bytes(ruta.read_bytes()[:400])
    v = comprobaciones.validar(db, inst, "manual")
    db.commit()
    assert v.resultado == "no_conforme" and v.detalle["mensajes"]
    assert preservacion.riesgo_de(db, inst)["nivel"] == "medio"


def test_sin_validadores_no_se_da_por_validado(cliente, db, fondo, archivista, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "directorio_validadores", str(tmp_path / "no-existe"))
    inst = ingresar_archivo(cliente, db, archivista, fondo, "plano.tif", tiff())
    v = comprobaciones.ultima(db, inst.id, "validacion")
    assert v.resultado == "no_disponible" and v.mecanismo_id is None
    assert preservacion.riesgo_de(db, inst)["nivel"] == "medio"


# --- PRE-13 (NDSA, Integridad nivel 1) · Antivirus en la ingesta ------------------------------------


@pytest.fixture()
def antivirus(monkeypatch, tmp_path):
    firmas = tmp_path / "ricora-prueba.hdb"
    firmas.write_text(f"{hashlib.md5(EICAR).hexdigest()}:{len(EICAR)}:RICORA.Prueba.EICAR\n")
    monkeypatch.setattr(settings, "antivirus", True)
    monkeypatch.setattr(settings, "clamav_firmas", str(firmas))


def test_archivo_infectado_va_a_cuarentena_y_no_sigue(cliente, db, fondo, archivista, antivirus):
    r = cliente.post("/api/ingesta/cargar", headers=archivista, data={"fondo_id": str(fondo.id)},
                     files=[("archivos", ("anexo.txt", EICAR, "text/plain"))])
    assert r.status_code == 200, r.text
    procesamiento.procesar_pendientes(db)
    db.expire_all()
    inst = db.get(Instanciacion, uuid.UUID(r.json()["resultados"][0]["id"]))
    assert inst.estado == "error" and "cuarentena" in inst.mensaje_error
    assert inst.ruta.startswith(f"cuarentena/{fondo.id}/")
    assert almacen.ruta_absoluta(inst.ruta).read_bytes() == EICAR  # apartado, no borrado
    c = comprobaciones.ultima(db, inst.id, "antivirus")
    assert c.resultado == "infectado" and c.detalle["firma"].startswith("RICORA.Prueba.EICAR")
    alerta = db.scalar(select(Alerta).where(Alerta.tipo == "archivo_infectado", Alerta.entidad_id == str(inst.id)))
    assert alerta.severidad == "alta"
    assert inst.formato_puid is None  # no siguió al resto del flujo


def test_archivo_limpio_sigue_con_su_evento_virus_check(cliente, db, fondo, archivista, antivirus):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    c = comprobaciones.ultima(db, inst.id, "antivirus")
    assert c.resultado == "limpio" and c.mecanismo_id
    raiz = premis_de(cliente, archivista, inst)
    muestra(raiz, "antivirus")
    [e] = eventos(raiz)["virus check"]
    assert t(e, "p:eventOutcomeInformation/p:eventOutcome") == "success"
    assert "ClamAV" in db.get(EntidadVocabulario, uuid.UUID(t(e, "p:linkingAgentIdentifier/p:linkingAgentIdentifierValue"))).nombre


def test_antivirus_apagado_no_analiza(cliente, db, fondo, archivista):
    assert settings.antivirus is False  # por defecto: las firmas oficiales ocupan cerca de 1 GB de memoria
    inst = ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    assert comprobaciones.ultima(db, inst.id, "antivirus") is None


# --- PRE-13 · Niveles NDSA calculados ------------------------------------------------------------


def test_niveles_ndsa_calculados_y_acumulativos(cliente, db, fondo, archivista, antivirus, monkeypatch):
    ingresar_archivo(cliente, db, archivista, fondo, "oficio.pdf", archivos.pdf_con_texto())
    r = cliente.get("/api/preservacion/ndsa", headers=archivista)
    assert r.status_code == 200, r.text
    areas = {a["area"]: a for a in r.json()["areas"]}
    assert list(areas) == ["Almacenamiento", "Integridad", "Control", "Metadatos", "Contenido"]
    for a in areas.values():
        assert len(a["requisitos"]) == 4
        # Regla acumulativa: el nivel es el último con todo cumplido sin huecos por debajo.
        cumplidos = [all(x["cumple"] for x in nivel) for nivel in a["requisitos"]]
        assert a["nivel"] == (cumplidos.index(False) if False in cumplidos else 4)
    # En las pruebas la segunda copia comparte disco con la primaria: el nivel 1 no se alcanza.
    assert areas["Almacenamiento"]["nivel"] == 0
    assert "Dos copias completas que no estén en el mismo lugar" in areas["Almacenamiento"]["falta_para_el_siguiente"]
    # Con antivirus y validadores, Integridad y Contenido suben; sin antivirus, Integridad baja a 0.
    assert areas["Integridad"]["nivel"] >= 2 and areas["Contenido"]["nivel"] == 4
    monkeypatch.setattr(settings, "antivirus", False)
    integridad = next(a for a in cliente.get("/api/preservacion/ndsa", headers=archivista).json()["areas"]
                      if a["area"] == "Integridad")
    assert integridad["nivel"] == 0 and integridad["falta_para_el_siguiente"] == ["Antivirus sobre el contenido recibido"]


# --- PRE-12 · Paquete de difusión (DIP) ----------------------------------------------------------


def test_dip_lleva_la_copia_de_acceso_publica_y_deja_fuera_lo_reservado(cliente, db, fondo, archivista, admin):
    publico = ingresar_archivo(cliente, db, archivista, fondo, "Oficio 114.pdf", archivos.pdf_con_texto())
    reservado = ingresar_archivo(cliente, db, archivista, fondo, "Anexo.pdf", archivos.pdf_con_texto("Datos reservados."))
    m = cliente.post(f"/api/preservacion/instanciacion/{publico.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    r = publicar(db, fondo, publico, reservado)
    cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "instanciacion", "entidad_id": str(reservado.id), "base": "estatuto", "acceso": "reservado",
        "reproduccion": "no_permitida", "fundamento": "Ley 1712 de 2014, art. 19", "vigente_hasta": "2090-01-01"})
    # Sin sesión y con la publicación apagada (decisión INS-01), no se entrega.
    assert cliente.get(f"/api/publico/dip/{r.id}").status_code == 401
    respuesta = cliente.get(f"/api/publico/dip/{r.id}", headers=archivista)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(respuesta.content)) as z:
        nombres = set(z.namelist())
        raiz = f"ricora-dip-{r.id}/"
        contenido = sorted(n.removeprefix(raiz) for n in nombres if n.startswith(raiz + "contenido/"))
        # La copia de acceso es la migración vigente (PDF/A), y lo reservado no está.
        assert m["nueva_instanciacion"]["nombre"] == "Oficio 114 (PDF/A-2b).pdf"
        assert contenido == ["contenido/Oficio 114 (PDF_A-2b).pdf"]  # la barra se reemplaza, no corta el nombre
        for n in ("descripcion/isadg.json", "descripcion/isadg.txt", "descripcion/ric-o.ttl",
                  "descripcion/iiif-manifest.json", "manifest-sha256.txt", "LEEME.txt"):
            assert raiz + n in nombres, n
        manifiesto = z.read(raiz + "manifest-sha256.txt").decode()
        for linea in manifiesto.splitlines():  # cada huella corresponde a su archivo
            huella, nombre = linea.split("  ", 1)
            assert hashlib.sha256(z.read(raiz + nombre)).hexdigest() == huella, nombre
        leeme = z.read(raiz + "LEEME.txt").decode()
        assert leeme.startswith("PAQUETE DE INFORMACIÓN DE DIFUSIÓN (DIP)") and "Quedaron fuera 1 archivo(s)" in leeme
        assert "Anexo" not in leeme and "Anexo" not in z.read(raiz + "descripcion/iiif-manifest.json").decode()
        ficha = {e["elemento"]: e["valor"] for e in __import__("json").loads(z.read(raiz + "descripcion/isadg.json"))}
        assert ficha["3.1.2"] == "Oficio 114"
        from rdflib import Graph, RDF, URIRef

        from app.servicios import exportacion_rico
        g = Graph().parse(data=z.read(raiz + "descripcion/ric-o.ttl"), format="turtle")
        assert (URIRef(exportacion_rico.base() + str(r.id)), RDF.type, None) in g
        assert "Anexo" not in z.read(raiz + "descripcion/ric-o.ttl").decode()
    assert list((almacen.raiz() / ".temporal").glob("dip-*")) == []
    # Una descripción sin publicar no tiene DIP.
    r.publicado_en = None
    db.commit()
    assert cliente.get(f"/api/publico/dip/{r.id}", headers=archivista).status_code == 404


def test_dip_sin_sesion_cuando_la_publicacion_esta_encendida(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "Oficio 114.pdf", archivos.pdf_con_texto())
    r = publicar(db, fondo, inst)
    parametros.cambiar(db, "rdf_uris_publicas", True, inst.cargado_por_id, "instrumentos")
    db.commit()
    assert cliente.get(f"/api/publico/dip/{r.id}").status_code == 200


# --- PRE-14 · Comprobaciones registradas por API ---------------------------------------------------


def test_comprobaciones_por_api(cliente, db, fondo, archivista):
    inst = ingresar_archivo(cliente, db, archivista, fondo, "plano.tif", tiff())
    r = cliente.get(f"/api/preservacion/instanciacion/{inst.id}/comprobaciones", headers=archivista)
    assert r.status_code == 200
    [v] = r.json()
    assert (v["tipo"], v["herramienta"], v["resultado"]) == ("validacion", "JHOVE", "conforme")
    assert db.scalar(select(ComprobacionTecnica).where(ComprobacionTecnica.instanciacion_id == inst.id)).mecanismo_id


def test_constancia_de_revision_del_registro_completa_control_nivel_4(cliente, db, archivista, cabeceras_admin):
    def control():
        return next(a for a in cliente.get("/api/preservacion/ndsa", headers=cabeceras_admin).json()["areas"]
                    if a["area"] == "Control")
    assert control()["nivel"] == 3
    assert control()["falta_para_el_siguiente"] == ["Revisar periódicamente los registros"]
    # Solo quien ve toda la auditoría deja la constancia; es un evento nuevo, no un cambio del registro.
    assert cliente.post("/api/auditoria/consolidado/revisado", headers=archivista, json={}).status_code == 403
    r = cliente.post("/api/auditoria/consolidado/revisado", headers=cabeceras_admin,
                     json={"nota": "Sin accesos fuera de horario."})
    assert r.status_code == 200, r.text
    [rev] = r.json()["revisiones"]
    assert rev["nota"] == "Sin accesos fuera de horario." and rev["por"]
    assert cliente.get("/api/auditoria/consolidado", headers=cabeceras_admin).json()["revisiones"] == [rev]
    assert control()["nivel"] == 4
