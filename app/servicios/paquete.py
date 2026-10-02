"""
Paquete de información de archivo (AIP, OAIS ISO 14721) con metadatos
PREMIS 3.0, empaquetado según la convención BagIt 1.0 (RFC 8493).

Estructura de un paquete de una instanciación (ver la decisión BagIt
frente a METS en documentacion/modulo-5-preservacion.md):

    ricora-aip-<id>/
      bagit.txt                  declaración BagIt
      bag-info.txt               datos del paquete (quién, cuándo, cuánto)
      manifest-sha256.txt        huella de cada archivo de data/
      tagmanifest-sha256.txt     huella de los archivos de arriba
      data/
        LEEME.txt                explicación en lenguaje llano
        contenido/<archivo>      Información de Contenido: el objeto de datos
        metadatos/premis.xml     PREMIS: Objeto, Eventos, Agentes, Derechos
        metadatos/pdi.json       Información de Descripción de Preservación:
                                 Referencia, Contexto, Procedencia, Fijeza,
                                 Derechos de acceso (+ información de
                                 representación del contenido)

El de un expediente lleva una carpeta así (contenido/ y metadatos/) por
cada instanciación, dentro de data/, más data/expediente.json.

Todo sale de lo que el sistema ya registró: la ingesta, las verificaciones
de integridad, las migraciones, las segundas copias, las restauraciones, la
descripción (grafo RiC) y las declaraciones de derechos. Nada se inventa.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from lxml import etree
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.auditoria import RegistroAuditoria
from app.models.descripcion import Relacion
from app.models.instanciacion import Instanciacion
from app.models.preservacion import Migracion, Restauracion, SegundaCopia, VerificacionIntegridad
from app.models.recurso_documental import RecursoDocumental
from app.models.usuario import Usuario
from app.servicios import almacen, derechos
from app.servicios.auditoria import registrar

PREMIS_NS = "http://www.loc.gov/premis/v3"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
PREMIS_ESQUEMA = "https://www.loc.gov/standards/premis/premis.xsd"
P = f"{{{PREMIS_NS}}}"
NS_AGENTES = uuid.UUID("6f1c2a52-3c1e-4b8e-9a51-7d0f2b9c4e11")  # espacio fijo para identificar software

ID_UUID = "UUID"
ID_AUDITORIA = "RICORA registro de auditoría"
ID_USUARIO = "RICORA usuario"
ID_SOFTWARE = "RICORA software"

CATEGORIAS_PDI = ("referencia", "contexto", "procedencia", "fijeza", "derechos_de_acceso")


class ErrorPaquete(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


# --- Eventos y agentes (PREMIS), reunidos desde lo ya registrado ---------------------------------------


def _agente_software(nombre: str) -> dict:
    return {"tipo_id": ID_SOFTWARE, "id": str(uuid.uuid5(NS_AGENTES, nombre)), "nombre": nombre, "tipo": "software"}


def _agente_persona(db: Session, usuario_id: uuid.UUID | None) -> dict | None:
    if usuario_id is None:
        return None
    u = db.get(Usuario, usuario_id)
    return {"tipo_id": ID_USUARIO, "id": str(usuario_id), "nombre": u.nombre if u else "Usuario", "tipo": "person"}


SISTEMA = f"{settings.nombre_sistema} (sistema de gestión documental RiC)"


def _evento(id_tipo: str, id_valor, tipo: str, fecha: datetime, detalle: str, resultado: str,
            nota: str | None, agentes: list[tuple[dict | None, str]], objetos: list[tuple[str, str]]) -> dict:
    return {"tipo_id": id_tipo, "id": str(id_valor), "tipo": tipo, "fecha": fecha, "detalle": detalle,
            "resultado": resultado, "nota": nota, "agentes": [(a, rol) for a, rol in agentes if a is not None],
            "objetos": objetos}


def eventos_de(db: Session, inst: Instanciacion) -> list[dict]:
    """Cadena de eventos PREMIS de la instanciación, en orden de tiempo."""
    yo = str(inst.id)
    sistema = _agente_software(SISTEMA)
    eventos = []
    if inst.derivada_de_id is None:
        eventos.append(_evento(ID_UUID, uuid.uuid5(inst.id, "ingestion"), "ingestion", inst.cargado_en,
                               f"Ingreso del archivo «{inst.nombre_original}» al fondo por el módulo de ingesta.",
                               "éxito", None,
                               [(_agente_persona(db, inst.cargado_por_id), "implementer"), (sistema, "executing program")],
                               [(yo, "outcome")]))
    fecha_proceso = inst.procesado_en or inst.cargado_en
    eventos.append(_evento(ID_UUID, uuid.uuid5(inst.id, "message digest calculation"), "message digest calculation",
                           fecha_proceso, f"Cálculo de la huella digital con {inst.algoritmo_huella}.", "éxito",
                           inst.huella, [(sistema, "executing program")], [(yo, "source")]))
    if inst.herramienta_identificacion:
        eventos.append(_evento(ID_UUID, uuid.uuid5(inst.id, "format identification"), "format identification",
                               fecha_proceso, "Identificación del formato contra el registro PRONOM.",
                               "fallo" if inst.formato_no_identificado else "éxito",
                               f"{inst.formato_puid or 'sin PUID'} · {inst.formato_nombre or 'formato desconocido'}"
                               + (f" · {inst.formato_base}" if inst.formato_base else ""),
                               [(_agente_software(inst.herramienta_identificacion), "executing program")],
                               [(yo, "source")]))
    for c in db.scalars(select(SegundaCopia).where(SegundaCopia.instanciacion_id == inst.id)).all():
        eventos.append(_evento(ID_UUID, c.id, "replication", c.creada_en,
                               f"Segunda copia en «{c.ubicacion}» (motivo: {c.motivo.replace('_', ' ')}).", "éxito",
                               f"{c.algoritmo} {c.huella}",
                               [(_agente_persona(db, c.creada_por_id), "implementer"), (sistema, "executing program")],
                               [(yo, "source")]))
    for v in db.scalars(select(VerificacionIntegridad).where(VerificacionIntegridad.instanciacion_id == inst.id)).all():
        bien = v.resultado == "integra" and v.segunda_copia_resultado in (None, "integra")
        eventos.append(_evento(ID_UUID, v.id, "fixity check", v.fecha,
                               f"Verificación de integridad {'periódica' if v.origen == 'periodica' else 'manual'} "
                               f"({v.algoritmo}) de la copia primaria y de la segunda copia.",
                               "éxito" if bien else "fallo",
                               f"Copia primaria: {v.resultado}. Segunda copia: {v.segunda_copia_resultado or 'no verificada'}.",
                               [(_agente_persona(db, v.usuario_id), "implementer"), (sistema, "executing program")],
                               [(yo, "source")]))
    migraciones = db.scalars(select(Migracion).where((Migracion.instanciacion_origen_id == inst.id)
                                                     | (Migracion.instanciacion_resultado_id == inst.id))).all()
    for m in migraciones:
        objetos = [(str(m.instanciacion_origen_id), "source")]
        if m.instanciacion_resultado_id:
            objetos.append((str(m.instanciacion_resultado_id), "outcome"))
        resultado = {"completada": "éxito", "fallida": "fallo"}.get(m.estado, "en espera")
        agentes = [(_agente_persona(db, m.aprobada_por_id), "authorizer")]
        if m.herramienta:
            agentes.append((_agente_software(m.herramienta) if m.modo == "automatica" else
                            _agente_persona(db, m.aprobada_por_id), "executing program"))
        eventos.append(_evento(ID_UUID, m.id, "migration", m.terminada_en or m.aprobada_en,
                               f"Migración {'automática' if m.modo == 'automatica' else 'con archivo convertido por fuera'} "
                               f"a {m.destino_nombre}, aprobada de forma explícita.", resultado, m.mensaje or m.herramienta,
                               agentes, objetos))
    for r in db.scalars(select(Restauracion).where(Restauracion.instanciacion_id == inst.id)).all():
        eventos.append(_evento(ID_UUID, r.id, "recovery", r.fecha,
                               f"Copia primaria ({r.estado_previo}) restaurada desde la segunda copia; el archivo "
                               "dañado se conserva en cuarentena.", "éxito", r.ruta_cuarentena,
                               [(_agente_persona(db, r.usuario_id), "authorizer"), (sistema, "executing program")],
                               [(yo, "outcome")]))
    for a in db.scalars(select(RegistroAuditoria).where(RegistroAuditoria.accion == "paquete_exportado",
                                                        RegistroAuditoria.entidad_id == yo)).all():
        eventos.append(_evento(ID_AUDITORIA, a.id, "information package creation", a.fecha,
                               "Exportación del paquete de información de archivo (AIP, BagIt).", "éxito", None,
                               [(_agente_persona(db, a.usuario_id), "implementer"), (sistema, "executing program")],
                               [(yo, "source")]))
    return sorted(eventos, key=lambda e: e["fecha"])


# --- PREMIS XML -----------------------------------------------------------------------------------


def _sub(padre, nombre: str, texto=None, **atributos):
    el = etree.SubElement(padre, P + nombre, **atributos)
    if texto is not None:
        el.text = str(texto)
    return el


def _identificador(padre, nombre: str, tipo: str, valor: str, roles: list[str] = ()):
    el = _sub(padre, nombre)
    _sub(el, f"{nombre}Type", tipo)
    _sub(el, f"{nombre}Value", valor)
    for rol in roles:
        _sub(el, f"{nombre[0:-len('Identifier')]}Role", rol)
    return el


def _fecha(f: datetime | None) -> str:
    return f.isoformat(timespec="seconds") if f else ""


def _objeto_premis(raiz, db: Session, inst: Instanciacion, eventos: list[dict], declaracion: dict | None,
                   aplicacion: str | None):
    obj = _sub(raiz, "object", attrib={f"{{{XSI_NS}}}type": "premis:file"})
    _identificador(obj, "objectIdentifier", ID_UUID, str(inst.id))
    car = _sub(obj, "objectCharacteristics")
    _sub(car, "compositionLevel", 0)
    fix = _sub(car, "fixity")
    _sub(fix, "messageDigestAlgorithm", inst.algoritmo_huella)
    _sub(fix, "messageDigest", inst.huella)
    _sub(fix, "messageDigestOriginator", settings.nombre_sistema)
    _sub(car, "size", inst.tamano_bytes)
    fmt = _sub(car, "format")
    des = _sub(fmt, "formatDesignation")
    _sub(des, "formatName", inst.formato_nombre or "Formato no identificado")
    if inst.formato_version:
        _sub(des, "formatVersion", inst.formato_version)
    if inst.formato_puid:
        reg = _sub(fmt, "formatRegistry")
        _sub(reg, "formatRegistryName", "PRONOM")
        _sub(reg, "formatRegistryKey", inst.formato_puid)
        _sub(reg, "formatRegistryRole", "specification")
    if inst.herramienta_identificacion:
        _sub(fmt, "formatNote", f"Identificado con {inst.herramienta_identificacion}")
    if aplicacion:
        app = _sub(car, "creatingApplication")
        _sub(app, "creatingApplicationName", aplicacion)
        m = db.scalar(select(Migracion).where(Migracion.instanciacion_resultado_id == inst.id))
        if m and m.terminada_en:
            _sub(app, "dateCreatedByApplication", _fecha(m.terminada_en))
    _sub(obj, "originalName", inst.nombre_original)
    alm = _sub(obj, "storage")
    loc = _sub(alm, "contentLocation")
    _sub(loc, "contentLocationType", "ruta en el servidor")
    _sub(loc, "contentLocationValue", str(almacen.raiz() / inst.ruta))
    _sub(alm, "storageMedium", "Copia primaria · almacenamiento de archivo de RICORA")
    from app.servicios import segunda_copia

    copia = segunda_copia.vigente(db, inst.id)
    if copia is not None:
        alm = _sub(obj, "storage")
        loc = _sub(alm, "contentLocation")
        _sub(loc, "contentLocationType", "ruta en el servidor")
        _sub(loc, "contentLocationValue", str(segunda_copia.ruta_absoluta(copia)))
        _sub(alm, "storageMedium", f"Segunda copia · {copia.ubicacion} · estado: {copia.estado}")
    if inst.derivada_de_id:
        rel = _sub(obj, "relationship")
        _sub(rel, "relationshipType", "derivation")
        _sub(rel, "relationshipSubType", "has source")
        _identificador(rel, "relatedObjectIdentifier", ID_UUID, str(inst.derivada_de_id))
    for hija in db.scalars(select(Instanciacion.id).where(Instanciacion.derivada_de_id == inst.id)).all():
        rel = _sub(obj, "relationship")
        _sub(rel, "relationshipType", "derivation")
        _sub(rel, "relationshipSubType", "is source of")
        _identificador(rel, "relatedObjectIdentifier", ID_UUID, str(hija))
    for e in eventos:
        _identificador(obj, "linkingEventIdentifier", e["tipo_id"], e["id"])
    if declaracion:
        _identificador(obj, "linkingRightsStatementIdentifier", ID_UUID, declaracion["id"])


def _evento_premis(raiz, e: dict):
    ev = _sub(raiz, "event")
    _identificador(ev, "eventIdentifier", e["tipo_id"], e["id"])
    _sub(ev, "eventType", e["tipo"])
    _sub(ev, "eventDateTime", _fecha(e["fecha"]))
    _sub(_sub(ev, "eventDetailInformation"), "eventDetail", e["detalle"])
    res = _sub(ev, "eventOutcomeInformation")
    _sub(res, "eventOutcome", e["resultado"])
    if e["nota"]:
        _sub(_sub(res, "eventOutcomeDetail"), "eventOutcomeDetailNote", e["nota"])
    for a, rol in e["agentes"]:
        _identificador(ev, "linkingAgentIdentifier", a["tipo_id"], a["id"], [rol])
    for obj_id, rol in e["objetos"]:
        _identificador(ev, "linkingObjectIdentifier", ID_UUID, obj_id, [rol])


def _agente_premis(raiz, a: dict):
    ag = _sub(raiz, "agent")
    _identificador(ag, "agentIdentifier", a["tipo_id"], a["id"])
    _sub(ag, "agentName", a["nombre"])
    _sub(ag, "agentType", a["tipo"])


def _derechos_premis(raiz, d: dict, inst_id: str):
    st = _sub(_sub(raiz, "rights"), "rightsStatement")
    _identificador(st, "rightsStatementIdentifier", ID_UUID, d["id"])
    _sub(st, "rightsBasis", derechos.BASE_PREMIS[d["base"]])
    if d["base"] == "estatuto":
        info = _sub(st, "statuteInformation")
        _sub(info, "statuteJurisdiction", "co")
        _sub(info, "statuteCitation", d["fundamento"])
        if d["nota"]:
            _sub(info, "statuteNote", d["nota"])
    elif d["base"] == "licencia":
        info = _sub(st, "licenseInformation")
        _sub(info, "licenseTerms", d["fundamento"])
        if d["nota"]:
            _sub(info, "licenseNote", d["nota"])
    elif d["base"] == "derecho_de_autor":
        info = _sub(st, "copyrightInformation")
        _sub(info, "copyrightStatus", "copyrighted")
        _sub(info, "copyrightJurisdiction", "co")
        _sub(info, "copyrightNote", d["fundamento"] + (f" · {d['nota']}" if d["nota"] else ""))
    else:
        info = _sub(st, "otherRightsInformation")
        _sub(info, "otherRightsBasis", derechos.BASE_NOMBRE[d["base"]])
        _sub(info, "otherRightsNote", d["fundamento"] + (f" · {d['nota']}" if d["nota"] else ""))
    inicio = d["creada_en"].date().isoformat()
    fin = d["vigente_hasta"].isoformat() if d["vigente_hasta"] else None
    for acto, restriccion, nota in (
        ("disseminate", "Allow" if d["acceso"] == "publico" else "Disallow", d["acceso_nombre"]),
        ("replicate", {"permitida": "Allow", "condicionada": "Conditional", "no_permitida": "Disallow"}[d["reproduccion"]],
         d["reproduccion_nombre"]),
    ):
        g = _sub(st, "rightsGranted")
        _sub(g, "act", acto)
        _sub(g, "restriction", restriccion)
        plazo = _sub(g, "termOfGrant")
        _sub(plazo, "startDate", inicio)
        if fin:
            _sub(plazo, "endDate", fin)
        _sub(g, "rightsGrantedNote", nota)
    _identificador(st, "linkingObjectIdentifier", ID_UUID, inst_id)


def premis_xml(db: Session, inst: Instanciacion, eventos: list[dict], declaracion: dict | None,
               aplicacion: str | None) -> bytes:
    raiz = etree.Element(P + "premis", nsmap={"premis": PREMIS_NS, "xsi": XSI_NS},
                         attrib={"version": "3.0", f"{{{XSI_NS}}}schemaLocation": f"{PREMIS_NS} {PREMIS_ESQUEMA}"})
    _objeto_premis(raiz, db, inst, eventos, declaracion, aplicacion)
    for e in eventos:
        _evento_premis(raiz, e)
    agentes = {}
    for e in eventos:
        for a, _ in e["agentes"]:
            agentes.setdefault((a["tipo_id"], a["id"]), a)
    for a in agentes.values():
        _agente_premis(raiz, a)
    if declaracion:
        _derechos_premis(raiz, declaracion, str(inst.id))
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# --- Información de Descripción de Preservación (las cinco categorías OAIS) ----------------------------


def _jerarquia(db: Session, recurso: RecursoDocumental) -> list[dict]:
    salida, actual = [], recurso
    while actual is not None:
        salida.append({"id": str(actual.id), "nivel": actual.nivel, "titulo": actual.titulo,
                       "codigo_referencia": actual.codigo_referencia})
        actual = db.get(RecursoDocumental, actual.incluido_en_id) if actual.incluido_en_id and actual.nivel != "fondo" else None
    return list(reversed(salida))


def _iso(f) -> str | None:
    return f.isoformat() if f else None


def pdi(db: Session, inst: Instanciacion, eventos: list[dict], declaracion: dict | None, contenido: str) -> dict:
    from app.servicios import segunda_copia

    recursos = derechos.recursos_de(db, inst)
    fondo = db.get(RecursoDocumental, inst.fondo_id)
    copia = segunda_copia.vigente(db, inst.id)
    verificaciones = db.scalars(select(VerificacionIntegridad).where(VerificacionIntegridad.instanciacion_id == inst.id)
                                .order_by(VerificacionIntegridad.fecha)).all()
    migradas = db.scalars(select(Instanciacion).where(Instanciacion.derivada_de_id == inst.id)).all()
    return {
        "informacion_de_contenido": {
            "objeto_de_datos": contenido,
            "informacion_de_representacion": {
                "formato": inst.formato_nombre, "version": inst.formato_version, "mime": inst.formato_mime,
                "registro": "PRONOM", "puid": inst.formato_puid,
                "enlace": f"https://www.nationalarchives.gov.uk/PRONOM/{inst.formato_puid}" if inst.formato_puid else None,
                "identificado_con": inst.herramienta_identificacion,
            },
        },
        "informacion_de_descripcion_de_preservacion": {
            "referencia": {
                "identificador": str(inst.id), "tipo_identificador": "UUID", "urn": f"urn:uuid:{inst.id}",
                "entidad_ric": "Instantiation (RiC-E06) · rico:Instantiation",
                "nombre_original": inst.nombre_original,
                "codigos_de_referencia": [r.codigo_referencia for r in recursos if r.codigo_referencia],
            },
            "contexto": {
                "fondo": {"id": str(fondo.id), "titulo": fondo.titulo} if fondo else None,
                "record_resources": [{
                    "id": str(r.id), "nivel": r.nivel, "titulo": r.titulo, "codigo_referencia": r.codigo_referencia,
                    "relacion": "RiC-R025 has or had instantiation · rico:hasOrHadInstantiation",
                    "jerarquia": _jerarquia(db, r)} for r in recursos],
                "sin_describir": not recursos,
                "derivada_de": {"id": str(inst.derivada_de_id),
                                "relacion": "RiC-R015 migrated into (desde la original) · rico:migratedInto"}
                if inst.derivada_de_id else None,
                "migrada_a": [{"id": str(m.id), "nombre": m.nombre_original, "puid": m.formato_puid,
                               "relacion": "RiC-R015 migrated into · rico:migratedInto"} for m in migradas],
            },
            "procedencia": {
                "nota": "Historia de custodia y de eventos técnicos desde el ingreso, tomada de los eventos PREMIS "
                        "(metadatos/premis.xml).",
                "cargado_en": _iso(inst.cargado_en),
                "eventos": [{"id": e["id"], "tipo": e["tipo"], "fecha": _iso(e["fecha"]), "detalle": e["detalle"],
                             "resultado": e["resultado"],
                             "agentes": [{"nombre": a["nombre"], "tipo": a["tipo"], "rol": rol} for a, rol in e["agentes"]]}
                            for e in eventos],
            },
            "fijeza": {
                "algoritmo": inst.algoritmo_huella, "valor": inst.huella, "registrada_en": _iso(inst.procesado_en),
                "estado_copia_primaria": inst.estado_integridad,
                "segunda_copia": {"estado": copia.estado, "ubicacion": copia.ubicacion, "huella": copia.huella,
                                  "creada_en": _iso(copia.creada_en)} if copia else {"estado": "sin_copia"},
                "verificaciones": [{"fecha": _iso(v.fecha), "copia_primaria": v.resultado,
                                    "segunda_copia": v.segunda_copia_resultado, "origen": v.origen} for v in verificaciones],
            },
            "derechos_de_acceso": {
                "declaracion": {k: (_iso(v) if hasattr(v, "isoformat") else v) for k, v in declaracion.items()}
                if declaracion else None,
                "nota": None if declaracion else "No hay una declaración de derechos documentada para este archivo ni "
                                                  "para los niveles que lo contienen.",
            },
        },
    }


# --- BagIt ----------------------------------------------------------------------------------------


def nombre_seguro(nombre: str) -> str:
    base = re.sub(r"[^\w .()\-]", "_", nombre.replace("\\", "/").rsplit("/", 1)[-1]).strip(" .")
    return (base or "archivo")[:150]


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while bloque := f.read(almacen.TAMANO_BLOQUE):
            h.update(bloque)
    return h.hexdigest()


def _cerrar_bolsa(bolsa: Path, info: dict) -> None:
    datos = sorted(p for p in (bolsa / "data").rglob("*") if p.is_file())
    (bolsa / "manifest-sha256.txt").write_text(
        "".join(f"{_sha256(p)}  {p.relative_to(bolsa).as_posix()}\n" for p in datos), encoding="utf-8")
    (bolsa / "bagit.txt").write_text("BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n", encoding="utf-8")
    info = {"Bag-Software-Agent": f"{settings.nombre_sistema} (preservación digital)",
            "Bagging-Date": ahora().date().isoformat(),
            "Payload-Oxum": f"{sum(p.stat().st_size for p in datos)}.{len(datos)}"} | info
    (bolsa / "bag-info.txt").write_text("".join(f"{k}: {v}\n" for k, v in info.items()), encoding="utf-8")
    etiquetas = [bolsa / n for n in ("bagit.txt", "bag-info.txt", "manifest-sha256.txt")]
    (bolsa / "tagmanifest-sha256.txt").write_text(
        "".join(f"{_sha256(p)}  {p.name}\n" for p in etiquetas), encoding="utf-8")


def _comprimir(bolsa: Path, destino: Path) -> None:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(bolsa.rglob("*")):
            if p.is_file():
                z.write(p, f"{bolsa.name}/{p.relative_to(bolsa).as_posix()}")


LEEME = """PAQUETE DE INFORMACIÓN DE ARCHIVO (AIP) · {sistema}

Modelo: OAIS (ISO 14721:2012). Convención de empaquetado: BagIt 1.0 (RFC 8493).
Metadatos de preservación: PREMIS 3.0 (Library of Congress).
Generado el {fecha} por {persona}.

{cuerpo}

Cómo comprobar que nada cambió: cada archivo de data/ tiene su huella SHA-256
en manifest-sha256.txt. Cualquier validador BagIt (por ejemplo bagit-python
de la Library of Congress: «bagit.py --validate <carpeta>») recalcula las
huellas y avisa si alguna no coincide.
"""

CUERPO_INSTANCIACION = """Contenido:
  contenido/{archivo}
      Información de Contenido: el objeto de datos tal como se custodia.
  metadatos/premis.xml
      PREMIS: Objeto (identificador, formato PRONOM, tamaño, huella,
      ubicaciones primaria y segunda copia), Eventos (ingreso, huella,
      identificación de formato, segunda copia, verificaciones, migraciones,
      restauraciones, exportaciones), Agentes (personas y software) y
      Derechos (cuando hay una declaración).
  metadatos/pdi.json
      Información de Descripción de Preservación en sus cinco categorías:
      referencia, contexto, procedencia, fijeza y derechos de acceso, más la
      información de representación del contenido (formato PRONOM)."""


def _carpeta_instanciacion(db: Session, inst: Instanciacion, carpeta: Path, prefijo: str) -> dict:
    """Escribe contenido/ y metadatos/ de una instanciación. Devuelve su
    resumen para el índice del expediente."""
    archivo = nombre_seguro(inst.nombre_original)
    (carpeta / "contenido").mkdir(parents=True)
    (carpeta / "metadatos").mkdir()
    almacen.copiar_a(inst.ruta, carpeta / "contenido" / archivo)
    if _sha256(carpeta / "contenido" / archivo) != inst.huella:
        raise ErrorPaquete(f"«{inst.nombre_original}» no tiene la huella de la ingesta: verifique su integridad "
                           "(y restáurelo desde la segunda copia) antes de empaquetarlo.", 409)
    from app.servicios.preservacion import aplicacion_creadora

    declaracion = derechos.aplicable(db, inst)
    eventos = eventos_de(db, inst)
    (carpeta / "metadatos" / "premis.xml").write_bytes(
        premis_xml(db, inst, eventos, declaracion, aplicacion_creadora(db, inst)))
    datos_pdi = pdi(db, inst, eventos, declaracion, f"{prefijo}contenido/{archivo}")
    (carpeta / "metadatos" / "pdi.json").write_text(json.dumps(datos_pdi, ensure_ascii=False, indent=2, default=str),
                                                    encoding="utf-8")
    return {"id": str(inst.id), "nombre": inst.nombre_original, "carpeta": prefijo.rstrip("/") or ".",
            "puid": inst.formato_puid, "huella": inst.huella}


def _temporal() -> Path:
    carpeta = almacen.raiz() / ".temporal"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _empaquetar(nombre: str, construir) -> Path:
    """Arma la bolsa en una carpeta temporal y devuelve la ruta del .zip
    (el que llama la borra después de enviarla)."""
    trabajo = Path(tempfile.mkdtemp(prefix="aip-", dir=_temporal()))
    try:
        bolsa = trabajo / nombre
        (bolsa / "data").mkdir(parents=True)
        info = construir(bolsa / "data")
        _cerrar_bolsa(bolsa, info)
        descriptor, ruta = tempfile.mkstemp(prefix="aip-", suffix=".zip", dir=_temporal())
        os.close(descriptor)
        destino = Path(ruta)
        _comprimir(bolsa, destino)
        return destino
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)


def _persona(db: Session, usuario_id: uuid.UUID) -> str:
    u = db.get(Usuario, usuario_id)
    return u.nombre if u else "RICORA"


def exportar_instanciacion(db: Session, inst: Instanciacion, usuario_id: uuid.UUID,
                           ip: str | None = None) -> tuple[Path, str]:
    registrar(db, modulo="preservacion", accion="paquete_exportado", usuario_id=usuario_id,
              entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip, detalle=inst.nombre_original,
              nuevo={"alcance": "instanciacion", "convencion": "BagIt 1.0", "premis": "3.0"})
    db.flush()  # el propio evento de exportación queda dentro del paquete
    nombre = f"ricora-aip-{inst.id}"

    def construir(data: Path) -> dict:
        _carpeta_instanciacion(db, inst, data, "")
        (data / "LEEME.txt").write_text(LEEME.format(
            sistema=settings.nombre_sistema, fecha=ahora().isoformat(timespec="seconds"),
            persona=_persona(db, usuario_id),
            cuerpo=CUERPO_INSTANCIACION.format(archivo=nombre_seguro(inst.nombre_original))),
            encoding="utf-8")
        return {"External-Identifier": f"urn:uuid:{inst.id}",
                "External-Description": f"AIP de la instanciación «{inst.nombre_original}» (RiC-E06)",
                "Internal-Sender-Identifier": inst.ruta}

    return _empaquetar(nombre, construir), f"{nombre}.zip"


def instanciaciones_de_expediente(db: Session, expediente: RecursoDocumental) -> list[Instanciacion]:
    """Todas las instanciaciones del expediente: las de sus documentos (a
    cualquier profundidad), las del propio expediente y sus migraciones."""
    recursos, pendientes = [expediente.id], [expediente.id]
    while pendientes:
        hijos = list(db.scalars(select(RecursoDocumental.id).where(RecursoDocumental.incluido_en_id.in_(pendientes))).all())
        recursos.extend(hijos)
        pendientes = hijos
    ids = set(db.scalars(select(Relacion.destino_id).where(
        Relacion.origen_id.in_(recursos), Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente", Relacion.destino_tipo == "instanciacion")).all())
    pendientes = list(ids)
    while pendientes:  # las migraciones aún no publicadas con su documento
        hijas = set(db.scalars(select(Instanciacion.id).where(Instanciacion.derivada_de_id.in_(pendientes))).all()) - ids
        ids |= hijas
        pendientes = list(hijas)
    return sorted((i for i in (db.get(Instanciacion, x) for x in ids)
                   if i is not None and i.estado == "listo_para_descripcion"), key=lambda i: i.cargado_en)


def exportar_expediente(db: Session, expediente: RecursoDocumental, usuario_id: uuid.UUID,
                        ip: str | None = None) -> tuple[Path, str]:
    if expediente.nivel != "expediente":
        raise ErrorPaquete("El paquete consolidado se exporta al nivel de un expediente.")
    instancias = instanciaciones_de_expediente(db, expediente)
    if not instancias:
        raise ErrorPaquete("El expediente no tiene archivos (instanciaciones) descritos todavía.", 404)
    for inst in instancias:
        registrar(db, modulo="preservacion", accion="paquete_exportado", usuario_id=usuario_id,
                  entidad_tipo="instanciacion", entidad_id=inst.id, ip=ip, detalle=inst.nombre_original,
                  nuevo={"alcance": "expediente", "expediente_id": str(expediente.id), "convencion": "BagIt 1.0",
                         "premis": "3.0"})
    db.flush()
    nombre = f"ricora-aip-expediente-{expediente.id}"

    def construir(data: Path) -> dict:
        indice = []
        for n, inst in enumerate(instancias, 1):
            prefijo = f"{n:03d}-{inst.id}/"
            indice.append(_carpeta_instanciacion(db, inst, data / prefijo.rstrip("/"), prefijo))
        (data / "expediente.json").write_text(json.dumps({
            "expediente": {"id": str(expediente.id), "titulo": expediente.titulo,
                           "codigo_referencia": expediente.codigo_referencia, "fechas_extremas": expediente.fechas_extremas,
                           "entidad_ric": "Record Set (RiC-E03) · rico:RecordSet", "jerarquia": _jerarquia(db, expediente)},
            "instanciaciones": indice, "total": len(indice)}, ensure_ascii=False, indent=2), encoding="utf-8")
        (data / "LEEME.txt").write_text(LEEME.format(
            sistema=settings.nombre_sistema, fecha=ahora().isoformat(timespec="seconds"), persona=_persona(db, usuario_id),
            cuerpo=f"Expediente «{expediente.titulo}»: {len(indice)} instanciación(es).\n\n"
                   "expediente.json\n    Índice del expediente y de sus instanciaciones.\n"
                   "NNN-<identificador>/\n    Una carpeta por instanciación, con la misma estructura del paquete "
                   "individual:\n" + CUERPO_INSTANCIACION.format(archivo="<archivo>").replace("\n  ", "\n      ")),
            encoding="utf-8")
        return {"External-Identifier": f"urn:uuid:{expediente.id}",
                "External-Description": f"AIP del expediente «{expediente.titulo}» (Record Set, RiC-E03), "
                                        f"{len(indice)} instanciación(es)"}

    return _empaquetar(nombre, construir), f"{nombre}.zip"
