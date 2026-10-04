"""
Evidencia de cada fragmento citado (brecha RF-OCR-001).

El motor cita un fragmento literal del texto. Aquí se ubica ese fragmento
en el documento: la página y la zona (una o varias cajas, en fracciones de
la página, origen arriba a la izquierda), para resaltarlo en el visor y
para que quede fijado en la relación que se publica.

- Texto por OCR: las cajas son las de las líneas que cubre el fragmento,
  guardadas al extraer el texto (paginas_texto).
- PDF con capa de texto: la página sale de paginas_texto y la zona se busca
  en el propio PDF (pdfium), en esa página.
- Texto plano, Word u otros: no hay páginas; la evidencia es el fragmento y
  su posición en el texto, como antes.

Si el texto se volvió a extraer después de la propuesta, la posición
guardada ya no coincide: se vuelve a buscar el fragmento por su contenido.
"""

import logging
import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.evidencia_ia import PaginaTexto
from app.models.instanciacion import Instanciacion

log = logging.getLogger("ricora.evidencia")


def guardar_paginas(db: Session, inst: Instanciacion, paginas) -> None:
    """Reemplaza las páginas del texto de un archivo. Son un derivado del
    texto extraído: si el texto se vuelve a extraer, las anteriores ya no
    describen nada. La evidencia ya publicada no depende de ellas (la página
    y la zona quedan copiadas en cada relación)."""
    db.execute(delete(PaginaTexto).where(PaginaTexto.instanciacion_id == inst.id))
    for p in paginas or []:
        db.add(PaginaTexto(id=uuid.uuid4(), instanciacion_id=inst.id, numero=p.numero, inicio=p.inicio, fin=p.fin,
                           origen=p.origen, ancho_px=p.ancho_px, alto_px=p.alto_px, confianza=p.confianza,
                           lineas=p.lineas))


def _tramo(fragmento: str, texto: str, inicio: int | None) -> tuple[int, int] | None:
    """(inicio, fin) del fragmento en el texto: la posición guardada si sigue
    coincidiendo; si no, se busca de nuevo, exacto o sin distinguir
    mayúsculas ni espacios."""
    if inicio is not None and texto[inicio:inicio + len(fragmento)] == fragmento:
        return inicio, inicio + len(fragmento)
    posicion = texto.find(fragmento)
    if posicion >= 0:
        return posicion, posicion + len(fragmento)
    patron = r"\s+".join(re.escape(p) for p in fragmento.split())
    hallado = re.search(patron, texto, flags=re.IGNORECASE) if patron else None
    return (hallado.start(), hallado.end()) if hallado else None


def _union(cajas: list[dict]) -> dict:
    x0 = min(c["x"] for c in cajas)
    y0 = min(c["y"] for c in cajas)
    x1 = max(c["x"] + c["ancho"] for c in cajas)
    y1 = max(c["y"] + c["alto"] for c in cajas)
    return {"x": round(x0, 4), "y": round(y0, 4), "ancho": round(x1 - x0, 4), "alto": round(y1 - y0, 4)}


def _cajas_pdf(inst: Instanciacion, numero: int, fragmento: str) -> list[dict]:
    """Rectángulos del fragmento en la página de un PDF con capa de texto. Si
    el fragmento completo no aparece tal cual (saltos de línea en el PDF),
    se ubica por sus primeras palabras."""
    import pypdfium2 as pdfium

    from app.servicios import almacen

    try:
        documento = pdfium.PdfDocument(str(almacen.ruta_absoluta(inst.ruta)))
    except Exception:  # noqa: BLE001 — sin archivo legible no hay zona, pero sí página
        return []
    try:
        pagina = documento[numero - 1]
        ancho, alto = pagina.get_size()
        textpage = pagina.get_textpage()
        palabras = fragmento.split()
        for intento in (fragmento, " ".join(palabras[:6]), " ".join(palabras[:3])):
            if not intento:
                continue
            hallado = textpage.search(intento, match_case=False).get_next()
            if hallado:
                indice, cuenta = hallado
                cajas = []
                for i in range(textpage.count_rects(indice, cuenta)):
                    izq, abajo, der, arriba = textpage.get_rect(i)
                    cajas.append({"x": round(izq / ancho, 4), "y": round(1 - arriba / alto, 4),
                                  "ancho": round((der - izq) / ancho, 4), "alto": round((arriba - abajo) / alto, 4)})
                return cajas
        return []
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo ubicar el fragmento en el PDF %s: %s", inst.id, exc)
        return []
    finally:
        documento.close()


def ubicar(db: Session, instanciacion_id, inicio: int | None, fragmento: str | None) -> dict | None:
    """Página y zona de un fragmento: {pagina, paginas, bloque, x, y, ancho,
    alto, cajas, origen, inicio}. None si el documento no tiene páginas o si
    el fragmento no está en su texto."""
    if not fragmento or not instanciacion_id:
        return None
    inst = db.get(Instanciacion, uuid.UUID(str(instanciacion_id)))
    if inst is None or not inst.texto_extraido:
        return None
    tramo = _tramo(fragmento, inst.texto_extraido, inicio)
    if tramo is None:
        return None
    desde, hasta = tramo
    pagina = db.scalar(select(PaginaTexto).where(PaginaTexto.instanciacion_id == inst.id,
                                                 PaginaTexto.inicio <= desde, PaginaTexto.fin >= desde)
                       .order_by(PaginaTexto.numero))
    if pagina is None:
        return None
    cajas, bloque = [], None
    for linea in pagina.lineas or []:
        a, b, x, y, ancho, alto, bloque_linea = linea
        if a < hasta and b > desde:
            cajas.append({"x": x, "y": y, "ancho": ancho, "alto": alto})
            bloque = bloque if bloque is not None else bloque_linea
    if not cajas and pagina.origen == "capa_de_texto":
        cajas = _cajas_pdf(inst, pagina.numero, inst.texto_extraido[desde:hasta])
    zona = {"pagina": pagina.numero, "paginas": inst.paginas, "bloque": bloque, "origen": pagina.origen,
            "inicio": desde, "cajas": cajas}
    if cajas:
        zona |= _union(cajas)
    return zona
