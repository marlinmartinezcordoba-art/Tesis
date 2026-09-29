"""M9 · Exportación e interoperabilidad: la descripción de uno o varios
documentos en datos enlazados conformes a RiC-O 1.1 (Turtle), en JSON-LD
y en tabular (CSV) — RF-M9-01 — y el registro de cada exportación con su
archivo (RF-M9-03)."""

import csv
import io

from django.core.files.base import ContentFile
from django.utils import timezone
from rdflib import Graph

from . import flujo, grafo, rdf, reglas
from .models import Exportacion

_CONTENT_TYPES = {
    Exportacion.Formato.RDF: ("ttl", "text/turtle; charset=utf-8"),
    Exportacion.Formato.JSON_LD: ("jsonld", "application/ld+json; charset=utf-8"),
    Exportacion.Formato.CSV: ("csv", "text/csv; charset=utf-8"),
}


def _grafo_lote(records, base):
    g = Graph()
    g.bind("rico", rdf.RICO)
    for record in records:
        g += rdf.grafo_de_entidad(record, base)
        for instanciacion in record.instanciaciones.all():
            g += rdf.grafo_de_entidad(instanciacion, base)
    return g


def _csv_lote(records):
    matriz = reglas.cargar_matriz()["relaciones"]
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow([
        "documento_id", "documento", "forma_documental", "expediente", "serie_trd", "relacion_id", "relacion", "categoria",
        "entidad", "tipo_entidad", "estado", "origen_decision", "validado_por", "fecha_validacion",
        "evidencia_pagina", "evidencia_fragmento",
    ])
    for record in records:
        relaciones = list(flujo.relaciones_de(record))
        if not relaciones:
            escritor.writerow([record.pk, record.nombre, record.forma_documental or record.tipo_forma_documental,
                               record.record_set or "", record.serie_trd,
                               "", "", "", "", "", "sin relaciones validadas", "", "", "", "", ""])
        for rel in relaciones:
            destino = flujo.otro_lado(rel, record)
            escritor.writerow([
                record.pk, record.nombre, record.forma_documental or record.tipo_forma_documental,
                record.record_set or "", record.serie_trd,
                rel.relacion_id, matriz.get(rel.relacion_id, {}).get("nombre", ""),
                grafo.CATEGORIAS[grafo.categoria_relacion(rel.relacion_id)][0],
                str(destino) if destino else "", type(destino).__name__ if destino else "",
                rel.get_estado_display(), rel.origen_decision,
                rel.validado_por.get_username() if rel.validado_por else "",
                rel.fecha_validacion.isoformat() if rel.fecha_validacion else "",
                rel.evidencia.pagina if rel.evidencia else "", rel.evidencia.fragmento if rel.evidencia else "",
            ])
    return salida.getvalue()


def generar_exportacion(records, formato, usuario, base):
    """Genera el archivo, lo guarda y devuelve la fila de registro."""
    records = list(records)
    if formato == Exportacion.Formato.CSV:
        contenido = _csv_lote(records)
    else:
        g = _grafo_lote(records, base)
        contenido = g.serialize(format="turtle" if formato == Exportacion.Formato.RDF else "json-ld")
    extension, _ = _CONTENT_TYPES[formato]
    nombre = f"ricora-{timezone.now():%Y%m%d-%H%M%S}-{len(records)}docs.{extension}"
    exportacion = Exportacion(usuario=usuario, formato=formato, documentos=[r.pk for r in records], total_registros=len(records))
    exportacion.archivo.save(nombre, ContentFile(contenido.encode("utf-8") if isinstance(contenido, str) else contenido), save=True)
    return exportacion


def content_type_de(exportacion):
    return _CONTENT_TYPES[exportacion.formato][1]
