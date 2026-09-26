"""Extracción de texto de una Instantiation, página por página.

Reutiliza los mismos primitivos de OCR que `acervo.extraccion` (mismo
Tesseract, mismo umbral para decidir si una página de PDF está escaneada),
pero en vez de guardar un solo bloque de texto, crea un `PaginaTexto` por
página — así la Evidencia de una propuesta puede señalar la página exacta
(RiC-CM: evidencia por documento/página/fragmento).
"""

from acervo.extraccion import FormatoNoSoportado, extraer_paginas

__all__ = ["FormatoNoSoportado", "extraer_texto_de_instanciacion"]


def extraer_texto_de_instanciacion(instanciacion, agente="sistema"):
    """Extrae el texto de `instanciacion.archivo`, reemplaza sus PaginaTexto
    existentes (si la reextracción es porque el archivo cambió), registra el
    evento en la bitácora y devuelve (texto_completo, detalle), con el mismo
    `detalle` que arma `acervo.extraccion.resumir_paginas`."""
    from acervo.extraccion import resumir_paginas

    from .models import EventoRiC, PaginaTexto, registrar_evento

    paginas = extraer_paginas(instanciacion.archivo.path)
    texto, detalle = resumir_paginas(paginas)

    instanciacion.paginas.all().delete()
    PaginaTexto.objects.bulk_create([
        PaginaTexto(
            instanciacion=instanciacion, numero=i,
            texto=p["texto"], uso_ocr=p["ocr"],
            confianza_ocr=(round(sum(p["confianzas"]) / len(p["confianzas"]), 1) if p["confianzas"] else None),
        )
        for i, p in enumerate(paginas, start=1)
    ])
    registrar_evento(instanciacion, EventoRiC.Tipo.EXTRACCION, agente=agente, detalle=detalle)
    return texto, detalle
