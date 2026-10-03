"""
Formatos de intercambio archivístico (hallazgo INS-05).

- EAD3 (SAA, 2015) del fondo, desde el mismo árbol de los instrumentos y
  solo con lo público (el filtro de INS-02).
- EAC-CPF 2.0 (SAA, 2022) de cada agente, desde su ficha ISAAR.
- Manifiesto IIIF Presentation 3.0 de una descripción pública, con las
  páginas que ya produce el visor (PNG). No es un servidor IIIF Image: no
  hay mosaicos ni zoom profundo (decisión documentada).

EAD3 y EAC-CPF se validan contra sus esquemas oficiales (XSD de la SAA,
copiados en app/recursos/esquemas) antes de entregarse: un archivo que no
valida no sale.
"""

import uuid
from functools import lru_cache
from pathlib import Path

from lxml import etree
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import ahora
from app.models.descripcion import EntidadVocabulario, IdentificadorEntidad, NombreEntidad, Relacion
from app.models.instanciacion import Instanciacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import fechas, isadg

ESQUEMAS = Path(__file__).resolve().parent.parent / "recursos" / "esquemas"
EAD = "http://ead3.archivists.org/schema/"
EAC = "https://archivists.org/ns/eac/v2"

NIVEL_EAD = {"fondo": "fonds", "seccion": "subfonds", "subseccion": "subfonds", "serie": "series",
             "subserie": "subseries", "expediente": "file", "unidad_documental": "item"}


class ErrorIntercambio(ValueError):
    pass


@lru_cache(maxsize=None)
def _esquema(nombre: str) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(ESQUEMAS / nombre)))


def validar(xml: bytes, esquema: str) -> list[str]:
    s = _esquema(esquema)
    documento = etree.fromstring(xml)
    if s.validate(documento):
        return []
    return [f"línea {e.line}: {e.message}" for e in s.error_log]


def _sub(padre, ns: str, nombre: str, texto: str | None = None, **atributos):
    nodo = etree.SubElement(padre, f"{{{ns}}}{nombre}", {k.rstrip("_"): str(v) for k, v in atributos.items() if v})
    if texto is not None:
        nodo.text = texto
    return nodo


def _parrafos(padre, ns: str, contenedor: str, texto: str | None):
    if not texto or not texto.strip():
        return None
    c = _sub(padre, ns, contenedor)
    for p in [x.strip() for x in texto.replace("\r\n", "\n").split("\n\n") if x.strip()]:
        _sub(c, ns, "p", p)
    return c


# --- EAD3 ---------------------------------------------------------------------------------------


def _did(db: Session, padre, r: RecursoDocumental, ficha: dict):
    did = _sub(padre, EAD, "did")
    if r.codigo_referencia:
        _sub(did, EAD, "unitid", r.codigo_referencia)
    _sub(did, EAD, "unittitle", r.titulo)
    if ficha.get("3.1.3"):
        _sub(did, EAD, "unitdate", ficha["3.1.3"])
    if ficha.get("3.2.1"):
        origen = _sub(did, EAD, "origination")
        for nombre in ficha["3.2.1"].split(", "):
            _sub(_sub(origen, EAD, "corpname"), EAD, "part", nombre)
    if r.idiomas or r.escrituras:
        lm = _sub(did, EAD, "langmaterial")
        for codigo in r.idiomas or []:
            _sub(lm, EAD, "language", codigo, langcode=codigo)
        if r.escrituras:
            _sub(lm, EAD, "script", isadg.ESCRITURAS.get(r.escrituras[0], r.escrituras[0]), scriptcode=r.escrituras[0])
    if ficha.get("3.1.5"):
        _sub(did, EAD, "physdesc", ficha["3.1.5"])
    return did


# Elementos de ISAD(G) → elemento EAD3 (fuera de <did>), en el orden de la tabla de isadg.
ISADG_EAD = [("3.2.2", "bioghist"), ("3.2.3", "custodhist"), ("3.2.4", "acqinfo"), ("3.3.1", "scopecontent"),
             ("3.3.2", "appraisal"), ("3.3.3", "accruals"), ("3.3.4", "arrangement"), ("3.4.1", "accessrestrict"),
             ("3.4.2", "userestrict"), ("3.4.4", "phystech"), ("3.4.5", "otherfindaid"), ("3.5.1", "originalsloc"),
             ("3.5.2", "altformavail"), ("3.5.3", "relatedmaterial"), ("3.5.4", "bibliography"), ("3.6.1", "odd"),
             ("3.7.1", "processinfo")]


def _elementos_isadg(padre, ficha: dict):
    for elemento, etiqueta in ISADG_EAD:
        _parrafos(padre, EAD, etiqueta, ficha.get(elemento))


def _componentes(db: Session, padre, a, nodo_id: uuid.UUID):
    for h in a.hijos.get(nodo_id, []):
        r = a.nodos[h]
        if r.nivel == "parte_documental":
            continue
        c = _sub(padre, EAD, "c", level=NIVEL_EAD.get(r.nivel, "otherlevel"),
                 otherlevel=None if r.nivel in NIVEL_EAD else r.nivel, id=f"r-{r.id}")
        ficha = {e["elemento"]: e["valor"] for e in isadg.ficha(db, r)}
        _did(db, c, r, ficha)
        _elementos_isadg(c, ficha)
        _componentes(db, c, a, h)


def ead3(db: Session, fondo: RecursoDocumental) -> bytes:
    """El fondo en EAD3, solo con lo público (clasificado y reservado fuera)."""
    from app.servicios import instrumentos

    a = instrumentos.arbol(db, fondo, ver_restringidos=False)
    raiz = etree.Element(f"{{{EAD}}}ead", nsmap={None: EAD})
    control = _sub(raiz, EAD, "control")
    _sub(control, EAD, "recordid", f"urn:uuid:{fondo.id}")
    _sub(_sub(_sub(control, EAD, "filedesc"), EAD, "titlestmt"), EAD, "titleproper", fondo.titulo)
    _sub(control, EAD, "maintenancestatus", value="derived")
    _sub(_sub(control, EAD, "maintenanceagency"), EAD, "agencyname", settings.nombre_sistema)
    decl = _sub(control, EAD, "languagedeclaration")
    _sub(decl, EAD, "language", "español", langcode="spa")
    _sub(decl, EAD, "script", "latina", scriptcode="Latn")
    _sub(_sub(control, EAD, "conventiondeclaration"), EAD, "citation", "ISAD(G), 2.ª ed.; RiC-CM 1.0")
    evento = _sub(_sub(control, EAD, "maintenancehistory"), EAD, "maintenanceevent")
    _sub(evento, EAD, "eventtype", value="derived")
    momento = ahora()
    _sub(evento, EAD, "eventdatetime", momento.strftime("%d/%m/%Y %H:%M"), standarddatetime=momento.isoformat())
    _sub(evento, EAD, "agenttype", value="machine")
    _sub(evento, EAD, "agent", f"{settings.nombre_sistema} (exportación EAD3 desde la descripción publicada)")
    archdesc = _sub(raiz, EAD, "archdesc", level="fonds")
    ficha = {e["elemento"]: e["valor"] for e in isadg.ficha(db, fondo)}
    _did(db, archdesc, fondo, ficha)
    _elementos_isadg(archdesc, ficha)
    if a.hijos.get(fondo.id):
        _componentes(db, _sub(archdesc, EAD, "dsc"), a, fondo.id)
    xml = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    errores = validar(xml, "ead3.xsd")
    if errores:
        raise ErrorIntercambio("El EAD3 no valida contra el esquema oficial: " + "; ".join(errores[:5]))
    return xml


# --- EAC-CPF 2.0 ----------------------------------------------------------------------------------

TIPO_EAC = {"persona": "person", "familia": "family"}  # lo demás (entidades, grupos, cargos): corporateBody


def eac_cpf(db: Session, e: EntidadVocabulario) -> bytes:
    """La ficha de autoridad ISAAR del agente en EAC-CPF 2.0."""
    if e.clase != "agente" or e.subtipo == "mecanismo":
        raise ErrorIntercambio("EAC-CPF describe personas, familias y entidades (no mecanismos ni otras clases).")
    raiz = etree.Element(f"{{{EAC}}}eac", nsmap={None: EAC})
    estado = {"definitivo": "revised", "revisado": "revised"}.get(e.estado_elaboracion or "", "derived")
    control = _sub(raiz, EAC, "control", maintenanceStatus=estado)
    _sub(control, EAC, "recordId", f"urn:uuid:{e.id}")
    agencia = _sub(control, EAC, "maintenanceAgency")
    _sub(agencia, EAC, "agencyName", e.institucion_responsable or settings.nombre_sistema)
    historia = _sub(control, EAC, "maintenanceHistory")
    evento = _sub(historia, EAC, "maintenanceEvent", maintenanceEventType="derived")
    _sub(evento, EAC, "agent", f"{settings.nombre_sistema} (desde la ficha ISAAR)", agentType="machine")
    momento = ahora()
    _sub(evento, EAC, "eventDateTime", momento.strftime("%d/%m/%Y %H:%M"), standardDateTime=momento.isoformat())
    if e.fuentes:
        fuente = _sub(_sub(control, EAC, "sources"), EAC, "source")
        _sub(fuente, EAC, "reference", e.fuentes)
    _sub(_sub(control, EAC, "conventionDeclaration"), EAC, "reference",
         e.reglas or "ISAAR (CPF), 2.ª edición (Consejo Internacional de Archivos, 2004)")
    for codigo in e.lenguas or ["spa"]:
        _sub(control, EAC, "languageDeclaration", languageCode=codigo, scriptCode=(e.escrituras or ["Latn"])[0])
    descripcion_cpf = _sub(raiz, EAC, "cpfDescription")
    identidad = _sub(descripcion_cpf, EAC, "identity")
    _sub(identidad, EAC, "entityType", value=TIPO_EAC.get(e.subtipo or "", "corporateBody"))
    autorizada = _sub(identidad, EAC, "nameEntry", status="authorized")
    _sub(autorizada, EAC, "part", e.nombre)
    for n in db.scalars(select(NombreEntidad).where(NombreEntidad.entidad_id == e.id,
                                                    NombreEntidad.estado == "vigente")).all():
        _sub(_sub(identidad, EAC, "nameEntry", status="alternative", languageOfElement=n.idioma), EAC, "part", n.nombre)
    for i in db.scalars(select(IdentificadorEntidad).where(IdentificadorEntidad.entidad_id == e.id,
                                                           IdentificadorEntidad.estado == "vigente")).all():
        _sub(identidad, EAC, "identityId", i.valor, localType=i.esquema)
    desc = _sub(descripcion_cpf, EAC, "description")
    if e.existencia_edtf:
        existencia = _sub(desc, EAC, "existDates")
        _sub(existencia, EAC, "date", fechas.legible(e.existencia_edtf))
    _parrafos(desc, EAC, "biogHist", e.historia)
    xml = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    errores = validar(xml, "eac.xsd")
    if errores:
        raise ErrorIntercambio("El EAC-CPF no valida contra el esquema oficial: " + "; ".join(errores[:5]))
    return xml


# --- IIIF Presentation 3.0 -----------------------------------------------------------------------


def manifiesto_iiif(db: Session, recurso: RecursoDocumental, base: str) -> dict:
    """Manifiesto IIIF Presentation 3.0 de una descripción pública: un
    lienzo por página de cada archivo que el visor sabe mostrar."""
    from PIL import Image

    from app.servicios import derechos, recorte
    import io

    instancias = db.scalars(select(Instanciacion).join(Relacion, Relacion.destino_id == Instanciacion.id).where(
        Relacion.origen_id == recurso.id, Relacion.codigo_ric == "has_or_had_instantiation",
        Relacion.estado == "vigente", Instanciacion.estado == "listo_para_descripcion")).all()
    raiz = f"{base}/api/publico/iiif/{recurso.id}"
    lienzos = []
    for inst in instancias:
        if derechos.instanciacion_restringida(db, inst) or not recorte.admite_paginas(inst):
            continue
        for pagina in range(1, min(recorte.total_paginas(inst), 500) + 1):
            png = recorte.pagina_png(inst, pagina)
            ancho, alto = Image.open(io.BytesIO(png)).size
            lienzo = f"{raiz}/lienzo/{inst.id}/{pagina}"
            imagen = f"{base}/api/publico/iiif/imagen/{inst.id}/{pagina}.png"
            lienzos.append({
                "id": lienzo, "type": "Canvas", "label": {"es": [f"{inst.nombre_original}, p. {pagina}"]},
                "height": alto, "width": ancho,
                "items": [{"id": f"{lienzo}/pagina", "type": "AnnotationPage", "items": [{
                    "id": f"{lienzo}/anotacion", "type": "Annotation", "motivation": "painting", "target": lienzo,
                    "body": {"id": imagen, "type": "Image", "format": "image/png", "height": alto, "width": ancho}}]}],
            })
    ficha = {e["elemento"]: (e["nombre"], e["valor"]) for e in isadg.ficha(db, recurso)}
    metadatos = [{"label": {"es": [nombre]}, "value": {"es": [valor]}}
                 for elemento, (nombre, valor) in ficha.items()
                 if valor and elemento in ("3.1.1", "3.1.3", "3.1.4", "3.2.1", "3.3.1", "3.4.1", "3.4.2")]
    salida = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": f"{raiz}/manifest", "type": "Manifest", "label": {"es": [recurso.titulo]},
        "metadata": metadatos, "items": lienzos,
        "homepage": [{"id": f"{base}/id/{recurso.id}", "type": "Text", "label": {"es": ["Descripción RiC-O"]},
                      "format": "text/turtle"}],
    }
    if recurso.condiciones_uso:
        salida["requiredStatement"] = {"label": {"es": ["Condiciones de uso"]}, "value": {"es": [recurso.condiciones_uso]}}
    return salida
