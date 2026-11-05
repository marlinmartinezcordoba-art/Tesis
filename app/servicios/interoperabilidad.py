"""
Prueba de interoperabilidad de un fondo: ¿lo que RICORA publica lo puede leer otro sistema?

Se hace sobre lo público del fondo (sin lo restringido) y sin guardar nada:

1. Términos de RiC-O 1.1: toda clase y propiedad existe en la ontología oficial.
2. Perfil SHACL: el grafo cumple las reglas de RICORA.
3. Formatos de la web de datos: el grafo se escribe en Turtle, JSON-LD, RDF/XML y
   N-Triples y otro analizador lo vuelve a leer idéntico (isomorfismo de grafos).
4. Reimportación: el importador de RiC-O, el mismo que recibe fondos de otros
   sistemas, reconoce el fondo, sus unidades y sus entidades.
5. EAD3 y EAC-CPF: los archivos XML validan contra los esquemas oficiales de la SAA.
6. Enlaces externos: cuántas autoridades están enlazadas con Wikidata, VIAF u otras.
"""

from collections import Counter

from rdflib import OWL, RDF, Graph
from rdflib.compare import isomorphic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario
from app.models.recurso_documental import RecursoDocumental
from app.servicios import conformidad_rico, exportacion_rico, grafo_rdf, intercambio, ric_o

FORMATOS = (("Turtle", "turtle"), ("JSON-LD", "json-ld"), ("RDF/XML", "xml"), ("N-Triples", "nt"))
RECURSOS = {"RecordSet", "Record", "RecordPart"}


def _prueba(nombre: str, norma: str, ok: bool, detalle: str) -> dict:
    return {"prueba": nombre, "norma": norma, "resultado": "superada" if ok else "no superada", "superada": ok,
            "detalle": detalle}


def _formatos(g: Graph) -> dict:
    fallas, pesos = [], []
    for nombre, formato in FORMATOS:
        try:
            datos = exportacion_rico.serializar(g, "jsonld") if formato == "json-ld" else g.serialize(format=formato, encoding="utf-8")
            otro = Graph().parse(data=datos, format=formato)
            if not isomorphic(g, otro):
                fallas.append(f"{nombre}: al releerlo cambia el grafo")
            pesos.append(f"{nombre} {len(datos) / 1024:.1f} KB")
        except Exception as exc:  # noqa: BLE001
            fallas.append(f"{nombre}: {str(exc)[:120]}")
    return _prueba("Formatos de la web de datos", "W3C RDF 1.1 (Turtle, JSON-LD, RDF/XML, N-Triples)", not fallas,
                   "; ".join(fallas) if fallas else "Se escribe y se relee idéntico en los cuatro formatos (" + ", ".join(pesos) + ").")


def _reimportar(g: Graph, ex) -> dict:
    from app.servicios import importacion_rico

    try:
        datos = g.serialize(format="turtle", encoding="utf-8")
        a = importacion_rico.analizar(importacion_rico.leer(datos, "prueba.ttl"))
    except Exception as exc:  # noqa: BLE001
        return _prueba("Reimportación en RiC-O", "RiC-O 1.1", False, f"El importador no pudo leerlo: {str(exc)[:160]}")
    exportados = sum(n for c, n in ex.resumen()["por_clase"].items() if c in RECURSOS)
    ok = a.fondo is not None and len(a.recursos) >= 1
    return _prueba("Reimportación en RiC-O", "RiC-O 1.1", ok,
                   f"El importador reconoce el fondo{'' if a.fondo else ' (no lo encontró)'}, {len(a.recursos)} unidad(es) de "
                   f"descripción de {exportados} publicada(s) y {len(a.entidades)} entidad(es)."
                   + (" Advierte: " + "; ".join(x.rstrip(".") for x in a.problemas[:3]) + "." if a.problemas else ""))


def _xml(db: Session, fondo: RecursoDocumental) -> list[dict]:
    salida = []
    try:
        ead = intercambio.ead3(db, fondo)
        salida.append(_prueba("EAD3 del fondo", "EAD3 (SAA, 2015)", True,
                              f"Valida contra el esquema oficial ({len(ead) / 1024:.1f} KB)."))
    except intercambio.ErrorIntercambio as exc:
        salida.append(_prueba("EAD3 del fondo", "EAD3 (SAA, 2015)", False, str(exc)[:300]))
    agentes = db.scalars(select(EntidadVocabulario).where(EntidadVocabulario.fondo_id == fondo.id,
                                                          EntidadVocabulario.clase == "agente",
                                                          EntidadVocabulario.estado == "activa",
                                                          EntidadVocabulario.subtipo != "mecanismo")
                         .order_by(EntidadVocabulario.nombre).limit(20)).all()
    if agentes:
        errores = []
        for e in agentes:
            try:
                intercambio.eac_cpf(db, e)
            except intercambio.ErrorIntercambio as exc:
                errores.append(f"{e.nombre}: {str(exc)[:120]}")
        salida.append(_prueba("EAC-CPF de los agentes", "EAC-CPF 2.0 (SAA, 2022)", not errores,
                              "; ".join(errores[:3]) if errores else f"Las {len(agentes)} fichas de agente validan contra el esquema oficial."))
    return salida


def _enlaces(g: Graph) -> dict:
    externos = Counter()
    for _, o in g.subject_objects(OWL.sameAs):
        texto = str(o)
        clave = next((k for k in ("wikidata", "viaf", "geonames", "isni", "loc.gov", "orcid", "ror") if k in texto), "otra")
        externos[clave] += 1
    total = sum(externos.values())
    return _prueba("Enlaces con la web de datos", "owl:sameAs (OWL 2)", total > 0,
                   (f"{total} enlace(s): " + ", ".join(f"{k} {n}" for k, n in externos.most_common())) if total
                   else "Ninguna autoridad publicada está enlazada todavía. Use «Buscar en Wikidata» en la ficha de cada autoridad.")


def informe(db: Session, fondo: RecursoDocumental) -> dict:
    ex = grafo_rdf.leer(db, fondo, incluir_restringidos=False)
    g = ex.grafo
    owl = conformidad_rico.verificar_owl(g)
    shacl = conformidad_rico.validar_shacl(g)
    violaciones = [r for r in shacl["resultados"] if r.get("severidad") == "Violation"]
    clases = {str(o)[len(ric_o.RICO):] for o in g.objects(None, RDF.type) if str(o).startswith(ric_o.RICO)}
    pruebas = [
        _prueba("Términos de RiC-O 1.1", "RiC-O 1.1 (ICA-EGAD)", not owl,
                "; ".join(owl[:3]) if owl else f"Las {len(clases)} clases y todas las propiedades usadas existen en la ontología oficial."),
        _prueba("Perfil SHACL de RICORA", "W3C SHACL", shacl["conforme"],
                "Sin violaciones." if shacl["conforme"] else f"{len(violaciones)} violación(es); la primera: {violaciones[0]['mensaje'] if violaciones else '—'}"),
        _formatos(g),
        _reimportar(g, ex),
        *_xml(db, fondo),
        _enlaces(g),
    ]
    return {"fondo": {"id": str(fondo.id), "titulo": fondo.titulo}, "tripletas": len(g), "clases": sorted(clases),
            "superadas": sum(p["superada"] for p in pruebas), "total": len(pruebas), "pruebas": pruebas}
