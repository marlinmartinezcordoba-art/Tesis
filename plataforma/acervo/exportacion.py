"""Exportación de metadatos a esquemas estándar interoperables (MET-04).

La entidad no debe quedar atada al formato propio de MAZUCA: los metadatos
descriptivos se pueden exportar a Dublin Core (oai_dc), y la bitácora de
preservación a un resumen de eventos al estilo PREMIS.
"""

from xml.sax.saxutils import escape


def _el(tag, texto):
    return f"<{tag}>{escape(str(texto))}</{tag}>" if texto else ""


def dublin_core_xml(documento):
    """15 elementos Dublin Core simple (oai_dc), a partir de la descripción ISAD(G)
    y del grafo de entidades RiC-CM (personas, instituciones, lugares y
    actividades vinculadas al documento con una relación tipada — DES-04).
    """
    relaciones = documento.relacionentidaddocumento_set.select_related("entidad")

    # dc:creator: el productor declarado en la ficha ISAD(G), más cualquier
    # persona o institución vinculada como productor en el grafo RiC.
    creadores = {documento.productor} if documento.productor else set()
    creadores |= {
        r.entidad.nombre for r in relaciones if r.tipo_relacion == "productor"
    }
    # dc:subject: entidades de las que el documento "trata" (relación
    # asociativa trata_sobre), sin importar su tipo — así se ve el tema del
    # documento aunque RiC-CM no tenga una entidad "concepto" separada.
    temas = {r.entidad.nombre for r in relaciones if r.tipo_relacion == "trata_sobre"}
    # dc:coverage: lugares mencionados o de producción.
    lugares = {
        r.entidad.nombre for r in relaciones
        if r.entidad.tipo == "lugar" and r.tipo_relacion in ("mencionado", "lugar_produccion")
    }
    # Actividades que el documento documenta (sin equivalente directo en
    # Dublin Core simple; se agregan como dc:relation adicionales).
    actividades = {r.entidad.nombre for r in relaciones if r.tipo_relacion == "documenta"}

    campos = [
        _el("dc:identifier", documento.codigo_referencia),
        _el("dc:title", documento.titulo),
        *[_el("dc:creator", c) for c in sorted(creadores)],
        _el("dc:date", documento.fechas),
        _el("dc:description", documento.alcance_contenido),
        *[_el("dc:subject", t) for t in sorted(temas)],
        *[_el("dc:coverage", l) for l in sorted(lugares)],
        _el("dc:format", documento.formato or documento.volumen_soporte),
        _el(
            "dc:type",
            {"fondo": "Fondo", "seccion": "Sección", "serie": "Serie", "unidad": "Unidad documental"}
            .get(documento.nivel_descripcion, documento.nivel_descripcion),
        ),
        _el("dc:relation", documento.unidad_clasificacion.ruta() if documento.unidad_clasificacion else ""),
        *[_el("dc:relation", f"Documenta: {a}") for a in sorted(actividades)],
        _el("dc:identifier", f"urn:sha256:{documento.sha256}"),
    ]
    cuerpo = "\n  ".join(c for c in campos if c)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f"  {cuerpo}\n"
        "</oai_dc:dc>\n"
    )


def premis_xml(documento):
    """Objeto (fijeza) y eventos de preservación, en un esquema simplificado PREMIS 3."""
    eventos_xml = []
    for e in documento.eventos.order_by("id"):
        eventos_xml.append(
            "  <premis:event>\n"
            f"    <premis:eventType>{escape(e.tipo)}</premis:eventType>\n"
            f"    <premis:eventDateTime>{e.fecha.isoformat()}</premis:eventDateTime>\n"
            f"    <premis:eventOutcome>{'success' if e.exitoso else 'failure'}</premis:eventOutcome>\n"
            f"    <premis:linkingAgentIdentifier>{escape(e.agente)}</premis:linkingAgentIdentifier>\n"
            "  </premis:event>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<premis:premis xmlns:premis="http://www.loc.gov/premis/v3" version="3.0">\n'
        "  <premis:object>\n"
        f"    <premis:objectIdentifier>{documento.pk}</premis:objectIdentifier>\n"
        '    <premis:objectCharacteristics>\n'
        '      <premis:fixity>\n'
        '        <premis:messageDigestAlgorithm>SHA-256</premis:messageDigestAlgorithm>\n'
        f"        <premis:messageDigest>{documento.sha256}</premis:messageDigest>\n"
        '      </premis:fixity>\n'
        f"      <premis:size>{documento.tamano_bytes}</premis:size>\n"
        f"      <premis:format>{escape(documento.formato)}</premis:format>\n"
        '    </premis:objectCharacteristics>\n'
        "  </premis:object>\n"
        + "\n".join(eventos_xml) + ("\n" if eventos_xml else "")
        + "</premis:premis>\n"
    )
