"""M9 · Exportación e interoperabilidad: la descripción de uno o varios
documentos en datos enlazados conformes a RiC-O 1.1 (Turtle), en JSON-LD
y en tabular (CSV) — RF-M9-01 — y el registro de cada exportación con su
formato, su alcance y quién la pidió (RF-M9-03).

La exportación se pide (`solicitar`) y se genera en la cola (`generar`,
tarea `ric.tasks.generar_exportacion`) con avance visible; al terminar, el
archivo se vuelve a leer con el mismo parser que usaría quien lo recibe,
para no entregar nunca un archivo que no es válido.
"""

import csv
import hashlib
import io
import json

from django.core.files.base import ContentFile
from django.utils import timezone
from rdflib import Graph
from rdflib.namespace import RDF, RDFS, XSD

from . import flujo, grafo, rdf, reglas
from .models import EventoRiC, Exportacion, Record, registrar_evento

_CONTENT_TYPES = {
    Exportacion.Formato.RDF: ("ttl", "text/turtle; charset=utf-8"),
    Exportacion.Formato.JSON_LD: ("jsonld", "application/ld+json; charset=utf-8"),
    Exportacion.Formato.CSV: ("csv", "text/csv; charset=utf-8"),
}
# Contexto JSON-LD: las propiedades se leen como «rico:hasCreator» en vez de
# URIs completas, sin perder su significado (el contexto las expande).
_CONTEXTO_JSONLD = {"rico": str(rdf.RICO), "rdf": str(RDF), "rdfs": str(RDFS), "xsd": str(XSD)}

COLUMNAS_CSV = [
    "documento_id", "documento", "identificador", "forma_documental", "idioma", "expediente", "serie_trd",
    "publicado", "fecha_publicacion", "relacion_id", "relacion", "categoria", "entidad", "tipo_entidad",
    "estado_analisis", "revision", "origen_decision", "validado_por", "fecha_validacion", "revisado_por",
    "fecha_revision", "evidencia_pagina", "evidencia_fragmento",
]


class ExportacionInvalida(Exception):
    """El archivo generado no se pudo volver a leer: no se entrega."""


def alcance_de(records):
    """RF-M9-03: el alcance en lenguaje claro, p. ej. «3 documentos: Acta
    del Cabildo…, Oficio 12, Resolución 4»."""
    nombres = [r.nombre for r in records]
    muestra = ", ".join(nombres[:5]) + (f" y {len(nombres) - 5} más" if len(nombres) > 5 else "")
    return f"{len(nombres)} documento(s): {muestra}"


def solicitar(records, formato, usuario):
    """Crea el registro de la exportación, en cola. No genera todavía."""
    records = list(records)
    return Exportacion.objects.create(
        usuario=usuario, formato=formato, documentos=[r.pk for r in records], total_registros=len(records),
        estado=Exportacion.Estado.EN_COLA, progreso=0, alcance=alcance_de(records),
    )


def _grafo_lote(records, base, visibilidad=None, al_avanzar=None):
    g = Graph()
    g.bind("rico", rdf.RICO)
    for i, record in enumerate(records, 1):
        g += rdf.grafo_de_entidad(record, base, visibilidad)
        for instanciacion in record.instanciaciones.all():
            g += rdf.grafo_de_entidad(instanciacion, base, visibilidad)
        if al_avanzar:
            al_avanzar(i, len(records))
    return g


def _csv_lote(records, visibilidad=None, al_avanzar=None):
    matriz = reglas.cargar_matriz()["relaciones"]
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(COLUMNAS_CSV)
    for i, record in enumerate(records, 1):
        base = [record.pk, record.nombre, record.identificador, record.forma_documental or record.tipo_forma_documental,
                record.idioma, record.record_set or "", record.serie_trd, "sí" if record.publicado else "no",
                record.fecha_publicacion.isoformat() if record.fecha_publicacion else ""]
        relaciones = [r for r in flujo.relaciones_de(record) if visibilidad is None or visibilidad.relacion(r)]
        if not relaciones:
            escritor.writerow(base + ["", "", "", "", "", "sin relaciones validadas", "", "", "", "", "", "", "", ""])
        for rel in relaciones:
            destino = flujo.otro_lado(rel, record)
            escritor.writerow(base + [
                rel.relacion_id, matriz.get(rel.relacion_id, {}).get("nombre", ""),
                grafo.CATEGORIAS[grafo.categoria_relacion(rel.relacion_id)][0],
                str(destino) if destino else "", type(destino).__name__ if destino else "",
                rel.get_estado_display(), rel.get_revision_display(), rel.origen_decision,
                rel.validado_por.get_username() if rel.validado_por else "",
                rel.fecha_validacion.isoformat() if rel.fecha_validacion else "",
                rel.revisado_por.get_username() if rel.revisado_por else "",
                rel.fecha_revision.isoformat() if rel.fecha_revision else "",
                rel.evidencia.pagina if rel.evidencia else "", rel.evidencia.fragmento if rel.evidencia else "",
            ])
        if al_avanzar:
            al_avanzar(i, len(records))
    # BOM: que Excel abra el UTF-8 con sus tildes y eñes sin configurar nada.
    return "﻿" + salida.getvalue()


def validar(contenido, formato, total_documentos):
    """Vuelve a leer el archivo como lo haría quien lo recibe. Devuelve un
    mensaje con lo verificado o lanza ExportacionInvalida."""
    try:
        if formato == Exportacion.Formato.CSV:
            filas = list(csv.reader(io.StringIO(contenido.lstrip("﻿"))))
            if not filas or filas[0] != COLUMNAS_CSV:
                raise ExportacionInvalida("el encabezado del CSV no es el esperado")
            documentos = {f[0] for f in filas[1:]}
            if len(documentos) != total_documentos:
                raise ExportacionInvalida(f"el CSV tiene {len(documentos)} documento(s) y se pidieron {total_documentos}")
            return f"Archivo verificado: CSV con {len(filas) - 1} fila(s) de {total_documentos} documento(s), UTF-8."
        g = Graph()
        g.parse(data=contenido, format="turtle" if formato == Exportacion.Formato.RDF else "json-ld")
        documentos = len(set(g.subjects(RDF.type, rdf.RICO.Record)))
        # Puede haber más rico:Record que los pedidos (un documento relacionado con otro), nunca menos.
        if documentos < total_documentos:
            raise ExportacionInvalida(f"el grafo describe {documentos} documento(s) y se pidieron {total_documentos}")
        nombre = "RDF/Turtle" if formato == Exportacion.Formato.RDF else "JSON-LD"
        return f"Archivo verificado: {nombre} válido con {len(g)} tripleta(s) RiC-O 1.1 que describen {total_documentos} documento(s)."
    except ExportacionInvalida:
        raise
    except Exception as e:
        raise ExportacionInvalida(f"el archivo no se pudo volver a leer ({e.__class__.__name__}: {e})") from e


def generar(exportacion, base, al_avanzar=None):
    """Genera el archivo de `exportacion`, lo valida, lo guarda con su huella
    y deja la exportación en el historial de cada documento (M7)."""
    from . import acceso_documentos

    ids = exportacion.documentos
    visibles = acceso_documentos.documentos_visibles(exportacion.usuario) if exportacion.usuario else Record.objects.none()
    records = list(visibles.filter(pk__in=ids).order_by("nombre"))  # RF-M8-04 también al generar
    vis = acceso_documentos.Visibilidad(exportacion.usuario) if exportacion.usuario else None
    vis = None if vis is None or vis.todo else vis
    if exportacion.formato == Exportacion.Formato.CSV:
        contenido = _csv_lote(records, vis, al_avanzar)
    else:
        g = _grafo_lote(records, base, vis, al_avanzar)
        if exportacion.formato == Exportacion.Formato.RDF:
            contenido = g.serialize(format="turtle")
        else:
            contenido = g.serialize(format="json-ld", context=_CONTEXTO_JSONLD, indent=2)
    exportacion.mensaje = validar(contenido, exportacion.formato, len(records))
    datos = contenido.encode("utf-8")
    extension, _ = _CONTENT_TYPES[exportacion.formato]
    nombre = f"ricora-{timezone.now():%Y%m%d-%H%M%S}-{len(records)}docs.{extension}"
    exportacion.archivo.save(nombre, ContentFile(datos), save=False)
    exportacion.tamano_bytes = len(datos)
    exportacion.sha256 = hashlib.sha256(datos).hexdigest()
    exportacion.total_registros = len(records)
    exportacion.documentos = [r.pk for r in records]
    exportacion.estado = Exportacion.Estado.LISTA
    exportacion.progreso = 100
    exportacion.save()
    for record in records:
        registrar_evento(
            flujo.instanciacion_principal(record), EventoRiC.Tipo.EXPORTACION, agente=exportacion.usuario or "sistema",
            detalle={"exportacion": exportacion.pk, "formato": exportacion.formato, "sha256": exportacion.sha256},
        )
    return exportacion


def generar_exportacion(records, formato, usuario, base):
    """Compatibilidad: solicitar y generar de inmediato (sin cola)."""
    return generar(solicitar(records, formato, usuario), base)


def content_type_de(exportacion):
    return _CONTENT_TYPES[exportacion.formato][1]
