"""
Auditoría de especialización RiC (3 de octubre de 2026), brechas 1, 2 y 8.

1. Cada relación exportada es un nodo rico:Relation con su fuente
   (rico:relationSource), su certeza (rico:relationCertainty, solo si la
   propuso el motor y nadie la corrigió) y su estado (rico:relationState).
   La clase es la más específica de RiC-O 1.1 y va orientada como la define
   el OWL (en algunas, al revés de la tripleta binaria).
2. Lo que el sistema ya sabía y no decía en RiC-O: extensión con cantidad y
   unidad (rico:Extent), calidad de la representación (OCR, RiC-A34),
   autenticidad (huella, verificación y validación, RiC-A03) y fechas de
   migración y derivación.
3. (Brecha 8) Group, rico:hasAuthor y rico:hasAccumulator, mapeados pero sin
   ninguna prueba que los exportara.

Toda exportación de estas pruebas pasa, además, la verificación contra el
OWL y el perfil SHACL.
"""

import uuid

import pytest
from rdflib import RDF, XSD, Literal, Namespace, URIRef

from app.db.base import ahora
from app.models.descripcion import Relacion
from app.models.recurso_documental import RecursoDocumental
from app.servicios import conformidad_rico, exportacion_rico, vocabulario
from tests import archivos
from tests.test_preservacion import archivista, fondo, herramientas, ingresar_archivo  # noqa: F401  (fixtures)

RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")


def u(ident) -> URIRef:
    return URIRef(exportacion_rico.base() + str(ident))


def documento(db, fondo, titulo="Oficio 114", folios=None) -> RecursoDocumental:
    r = RecursoDocumental(id=uuid.uuid4(), nivel="unidad_documental", titulo=titulo, fondo_id=fondo.id,
                          incluido_en_id=fondo.id, publicado_en=ahora(), folios=folios)
    db.add(r)
    db.flush()
    return r


def agente(db, fondo, nombre, subtipo="persona"):
    return vocabulario.crear(db, fondo_id=fondo.id, clase="agente", nombre=nombre, subtipo=subtipo, origen="persona",
                             confianza=None, motor=None, usuario_id=None)


def relacion(db, de, a, codigo, *, origen_tipo="recurso_documental", destino_tipo="entidad_vocabulario",
             **extra) -> Relacion:
    r = Relacion(origen_tipo=origen_tipo, origen_id=de.id, destino_tipo=destino_tipo, destino_id=a.id,
                 tipo_relacion="asociacion", codigo_ric=codigo, **({"origen": "persona"} | extra))
    db.add(r)
    db.flush()
    return r


def exportar_conforme(db, fondo):
    db.commit()
    ex = exportacion_rico.exportar(db, fondo)
    reporte = conformidad_rico.reporte(ex)
    assert reporte["owl"]["problemas"] == [], reporte["owl"]["problemas"]
    assert reporte["shacl"]["conforme"], reporte["shacl"]["resultados"]
    return ex


def uno(g, s, p):
    valores = list(g.objects(s, p))
    assert len(valores) == 1, (s, p, valores)
    return valores[0]


# --- Brecha 1 · Fuente, certeza y estado de cada relación -------------------------------------------


def test_relacion_propuesta_por_el_motor_lleva_su_certeza_y_su_fuente(cliente, db, fondo, archivista):
    archivo = ingresar_archivo(cliente, db, archivista, fondo, "Oficio 114.pdf", archivos.pdf_con_texto())
    doc = documento(db, fondo)
    relacion(db, doc, archivo, "has_or_had_instantiation", destino_tipo="instanciacion")
    alcalde = agente(db, fondo, "Jorge Eliécer Gaitán")
    rel = relacion(db, doc, alcalde, "has_creator", origen="motor", confianza=0.93, motor="motor-de-prueba",
                   fragmento="Firmado: Jorge Eliécer Gaitán, alcalde", fragmento_instanciacion_id=archivo.id)
    g = exportar_conforme(db, fondo).grafo
    nodo = u(rel.id)
    # La tripleta directa sigue; el nodo es la clase más específica, orientada del documento al agente.
    assert (u(doc.id), RICO.hasCreator, u(alcalde.id)) in g
    assert (nodo, RDF.type, RICO.CreationRelation) in g
    assert uno(g, nodo, RICO.relationHasSource) == u(doc.id) and uno(g, nodo, RICO.relationHasTarget) == u(alcalde.id)
    assert uno(g, nodo, RICO.relationCertainty) == Literal("alta (confianza del motor: 0.93)", lang="es")
    fuente = str(uno(g, nodo, RICO.relationSource))
    assert fuente.startswith("Propuesta por el motor de análisis y confirmada por una persona.")
    assert "«Firmado: Jorge Eliécer Gaitán, alcalde»" in fuente
    assert "motor-de-prueba" not in fuente  # el motor no se nombra (decisión anterior que se mantiene)


def test_certeza_media_y_baja_y_ninguna_si_una_persona_la_corrigio(db, fondo):
    doc = documento(db, fondo)
    media = relacion(db, doc, agente(db, fondo, "Concejo Municipal", "entidad_corporativa"), "has_addressee",
                     origen="motor", confianza=0.6)
    baja = relacion(db, doc, agente(db, fondo, "Personero"), "has_sender", origen="motor", confianza=0.3)
    corregida = relacion(db, doc, agente(db, fondo, "Tesorero"), "has_or_had_subject", origen="motor_editado",
                         confianza=0.9)
    propia = relacion(db, doc, agente(db, fondo, "Secretario"), "has_or_had_subject")
    g = exportar_conforme(db, fondo).grafo
    assert str(uno(g, u(media.id), RICO.relationCertainty)).startswith("media")
    assert str(uno(g, u(baja.id), RICO.relationCertainty)).startswith("baja")
    # Sin clase específica en RiC-O 1.1: la general rico:Relation.
    assert (u(media.id), RDF.type, RICO.Relation) in g
    # Corregida por una persona: la confianza del motor ya no describe lo que quedó.
    assert list(g.objects(u(corregida.id), RICO.relationCertainty)) == []
    assert "corregida" in str(uno(g, u(corregida.id), RICO.relationSource))
    assert list(g.objects(u(propia.id), RICO.relationCertainty)) == []
    assert str(uno(g, u(propia.id), RICO.relationSource)) == "Registrada por una persona."


def test_las_clases_que_van_al_reves_se_orientan_como_dice_ric_o(db, fondo):
    """PerformanceRelation: la actividad es la fuente. RecordResourceHoldingRelation:
    el agente custodio es la fuente. Así las define el OWL de RiC-O 1.1."""
    doc = documento(db, fondo)
    archivo_central = agente(db, fondo, "Archivo Central", "entidad_corporativa")
    custodia = relacion(db, doc, archivo_central, "has_or_had_holder")
    g = exportar_conforme(db, fondo).grafo
    nodo = u(custodia.id)
    assert (u(doc.id), RICO.hasOrHadHolder, u(archivo_central.id)) in g
    assert (nodo, RDF.type, RICO.RecordResourceHoldingRelation) in g
    assert uno(g, nodo, RICO.relationHasSource) == u(archivo_central.id)
    assert uno(g, nodo, RICO.relationHasTarget) == u(doc.id)


def test_estado_de_la_relacion_desde_su_vigencia(db, fondo):
    doc = documento(db, fondo)
    alcaldia = agente(db, fondo, "Alcaldía Municipal", "entidad_corporativa")
    terminada = relacion(db, alcaldia, agente(db, fondo, "Gaitán"), "has_or_had_member",
                         origen_tipo="entidad_vocabulario", fecha_edtf="1936/1937")
    vigente = relacion(db, alcaldia, agente(db, fondo, "Concejal actual"), "has_or_had_member",
                       origen_tipo="entidad_vocabulario", fecha_edtf="2020/")  # fin abierto, en el subconjunto EDTF del sistema
    sin_fecha = relacion(db, alcaldia, agente(db, fondo, "Personero"), "has_or_had_member",
                         origen_tipo="entidad_vocabulario")
    relacion(db, doc, alcaldia, "has_creator")
    g = exportar_conforme(db, fondo).grafo
    assert uno(g, u(terminada.id), RICO.relationState) == Literal("terminada", lang="es")
    assert uno(g, u(vigente.id), RICO.relationState) == Literal("vigente", lang="es")
    assert list(g.objects(u(sin_fecha.id), RICO.relationState)) == []  # no se inventa
    assert (u(terminada.id), RDF.type, RICO.MembershipRelation) in g


def test_el_fragmento_de_un_archivo_reservado_no_se_cita(cliente, db, fondo, archivista):
    archivo = ingresar_archivo(cliente, db, archivista, fondo, "Anexo.pdf", archivos.pdf_con_texto("Datos reservados."))
    cliente.put("/api/preservacion/derechos", headers=archivista, json={
        "entidad_tipo": "instanciacion", "entidad_id": str(archivo.id), "base": "estatuto", "acceso": "reservado",
        "reproduccion": "no_permitida", "fundamento": "Ley 1712 de 2014, art. 19", "vigente_hasta": "2090-01-01"})
    doc = documento(db, fondo)
    rel = relacion(db, doc, agente(db, fondo, "Informante"), "has_or_had_subject", origen="motor", confianza=0.9,
                   fragmento="El informante reservado dijo", fragmento_instanciacion_id=archivo.id)
    ex = exportar_conforme(db, fondo)
    fuente = str(uno(ex.grafo, u(rel.id), RICO.relationSource))
    assert "reservado" not in fuente and "«" not in fuente
    assert ex.omitidas["fragmento citado de un archivo restringido (la fuente de la relación sale sin él)"] == 1


# --- Brecha 2 · Lo que el sistema ya sabía ----------------------------------------------------------


def test_extension_con_cantidad_y_unidad(cliente, db, fondo, archivista):
    archivo = ingresar_archivo(cliente, db, archivista, fondo, "Oficio 114.pdf", archivos.pdf_con_texto())
    doc = documento(db, fondo, folios=12)
    relacion(db, doc, archivo, "has_or_had_instantiation", destino_tipo="instanciacion")
    g = exportar_conforme(db, fondo).grafo
    [ext] = g.objects(u(doc.id), RICO.hasExtent)
    assert (ext, RDF.type, RICO.RecordResourceExtent) in g
    assert uno(g, ext, RICO.quantity) == Literal("12.0", datatype=XSD.decimal)
    assert uno(g, ext, RICO.unitOfMeasurement) == Literal("folios", lang="es")
    assert (u(doc.id), RICO.recordResourceExtent, Literal("12 folios", lang="es")) in g
    medidas = {str(uno(g, e, RICO.unitOfMeasurement)): uno(g, e, RICO.quantity)
               for e in g.objects(u(archivo.id), RICO.hasExtent)}
    assert medidas["bytes"] == Literal(f"{archivo.tamano_bytes}.0", datatype=XSD.decimal)
    assert all((e, RDF.type, RICO.InstantiationExtent) in g for e in g.objects(u(archivo.id), RICO.hasExtent))


def test_calidad_del_ocr_y_autenticidad_del_archivo(cliente, db, fondo, archivista):
    archivo = ingresar_archivo(cliente, db, archivista, fondo, "oficio.png", archivos.png_con_texto())
    assert cliente.post(f"/api/preservacion/instanciacion/{archivo.id}/verificar", headers=archivista).status_code == 200
    doc = documento(db, fondo)
    relacion(db, doc, archivo, "has_or_had_instantiation", destino_tipo="instanciacion")
    db.refresh(archivo)
    g = exportar_conforme(db, fondo).grafo
    calidad = str(uno(g, u(archivo.id), RICO.qualityOfRepresentationNote))
    assert "OCR" in calidad and f"{archivo.confianza_ocr:.0f} sobre 100" in calidad
    autenticidad = str(uno(g, u(archivo.id), RICO.authenticityNote))
    assert archivo.huella in autenticidad and "copia primaria integra" in autenticidad


def test_fechas_de_migracion_y_derivacion_y_validacion_en_la_autenticidad(cliente, db, fondo, archivista):
    original = ingresar_archivo(cliente, db, archivista, fondo, "Oficio 114.pdf", archivos.pdf_con_texto())
    m = cliente.post(f"/api/preservacion/instanciacion/{original.id}/migrar", headers=archivista,
                     json={"destino": "pdfa_2b", "aprobada": True}).json()
    doc = documento(db, fondo)
    relacion(db, doc, original, "has_or_had_instantiation", destino_tipo="instanciacion")
    nueva = u(m["nueva_instanciacion"]["id"])
    g = exportar_conforme(db, fondo).grafo
    hoy = Literal(ahora().date().isoformat(), datatype=XSD.date)
    assert uno(g, u(original.id), RICO.migrationDate) == hoy
    assert uno(g, nueva, RICO.derivationDate) == hoy
    assert list(g.objects(u(original.id), RICO.derivationDate)) == []
    assert "veraPDF" in str(uno(g, nueva, RICO.authenticityNote))


# --- Brecha 8 · Group, autoría y acumulación ---------------------------------------------------------


def test_grupo_autor_y_acumulador_se_exportan_conformes(db, fondo):
    doc = documento(db, fondo)
    comision = agente(db, fondo, "Comisión de Notables", "grupo")
    autora = agente(db, fondo, "María Cano")
    coleccionista = agente(db, fondo, "Coleccionista particular")
    autoria = relacion(db, doc, autora, "has_author")
    acumulacion = relacion(db, doc, coleccionista, "has_accumulator")
    miembro = relacion(db, comision, autora, "has_or_had_member", origen_tipo="entidad_vocabulario")
    g = exportar_conforme(db, fondo).grafo
    assert (u(comision.id), RDF.type, RICO.Group) in g
    assert (u(doc.id), RICO.hasAuthor, u(autora.id)) in g
    assert (u(doc.id), RICO.hasAccumulator, u(coleccionista.id)) in g
    assert (u(autoria.id), RDF.type, RICO.AuthorshipRelation) in g
    assert (u(acumulacion.id), RDF.type, RICO.AccumulationRelation) in g
    assert (u(comision.id), RICO.hasOrHadMember, u(autora.id)) in g
    assert (u(miembro.id), RDF.type, RICO.MembershipRelation) in g


@pytest.mark.parametrize("codigo", ["performs_or_performed", "has_or_had_holder", "has_activity_type"])
def test_las_relaciones_invertidas_tienen_clase_especifica(codigo):
    from app.servicios import ric_o

    assert ric_o.clase_relacion(codigo, None) in ("PerformanceRelation", "RecordResourceHoldingRelation",
                                                  "TypeRelation")
    assert codigo in ric_o.RELACION_INVERTIDA
