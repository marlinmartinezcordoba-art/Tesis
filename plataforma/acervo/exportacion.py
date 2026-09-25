"""Exportación de metadatos a esquemas estándar interoperables (MET-04).

La entidad no debe quedar atada al formato propio de MAZUCA: los metadatos
descriptivos se pueden exportar a Dublin Core (oai_dc), y la bitácora de
preservación a un resumen de eventos al estilo PREMIS.
"""

from xml.sax.saxutils import escape


def _el(tag, texto):
    return f"<{tag}>{escape(str(texto))}</{tag}>" if texto else ""


def dublin_core_xml(documento):
    """15 elementos Dublin Core simple (oai_dc), a partir de la descripción ISAD(G)."""
    campos = [
        _el("dc:identifier", documento.codigo_referencia),
        _el("dc:title", documento.titulo),
        _el("dc:creator", documento.productor),
        _el("dc:date", documento.fechas),
        _el("dc:description", documento.alcance_contenido),
        _el("dc:format", documento.formato or documento.volumen_soporte),
        _el(
            "dc:type",
            {"fondo": "Fondo", "seccion": "Sección", "serie": "Serie", "unidad": "Unidad documental"}
            .get(documento.nivel_descripcion, documento.nivel_descripcion),
        ),
        _el("dc:relation", documento.unidad_clasificacion.ruta() if documento.unidad_clasificacion else ""),
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
