"""
Completitud del documento (RiC-A24, rico:integrityNote), revisada por el sistema.

Con el texto de cada página (capa de texto del PDF u OCR, ya guardado al
cargar el archivo), el sistema busca señales de que al documento le falta algo
o tiene algo de más, y propone la nota de completitud. Son reglas, no IA: cada
hallazgo dice en qué página está y por qué, y el archivista lo confirma o
corrige. Lo que el sistema no puede saber (un anexo que nunca se escaneó y que
el texto no menciona) no lo afirma.

Señales:
- Página sin texto: hoja en blanco o ilegible.
- Página con OCR de confianza baja: se lee con dificultad.
- Numeración que salta («Página 11 de 20» y después «Página 13 de 20», o
  folios 11 y 13): falta una hoja.
- Total declarado distinto de las páginas del archivo («Página 1 de 20» o
  «consta de 20 folios» y el archivo trae 18).
- Páginas repetidas (el mismo texto dos veces).
"""

import hashlib
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

PAGINA_DE = re.compile(r"\bp[aá]g(?:ina)?\.?\s*(?:n[o°º.]*\s*)?(\d{1,4})\s*(?:de|/)\s*(\d{1,4})\b", re.IGNORECASE)
HOJA_DE = re.compile(r"\bhoja\s*(?:n[o°º.]*\s*)?(\d{1,4})\s*(?:de|/)\s*(\d{1,4})\b", re.IGNORECASE)
FOLIO = re.compile(r"\bfolio\s*(?:n[o°º.]*\s*)?(\d{1,4})\b(?!\s*(?:de|al|y|a)\b)", re.IGNORECASE)
CONSTA = re.compile(r"\bconsta(?:n)?\s+de\s+(\d{1,4})\s+(folios|p[aá]ginas|hojas)\b", re.IGNORECASE)
MIN_TEXTO = 15  # caracteres útiles: menos que esto es una hoja en blanco o ilegible
UMBRAL_OCR = 60.0  # confianza del OCR por página (0 a 100) por debajo de la cual se avisa


def _limpio(texto: str) -> str:
    return re.sub(r"\W+", "", texto or "").lower()


def _paginas(db: Session, instanciacion_id: uuid.UUID, texto: str) -> list[dict]:
    from app.models.evidencia_ia import PaginaTexto

    filas = db.scalars(select(PaginaTexto).where(PaginaTexto.instanciacion_id == instanciacion_id)
                       .order_by(PaginaTexto.numero)).all()
    return [{"numero": p.numero, "texto": texto[p.inicio:p.fin], "confianza": p.confianza, "origen": p.origen}
            for p in filas]


def _rangos(numeros: list[int]) -> str:
    return ", ".join(str(n) for n in numeros[:12]) + ("…" if len(numeros) > 12 else "")


def revisar(db: Session, documento) -> dict:
    """La revisión de un archivo (una instanciación con su texto extraído)."""
    paginas = _paginas(db, documento.id, documento.texto_extraido or "")
    total = len(paginas) or (documento.paginas or 0)
    hallazgos: list[dict] = []
    if not paginas:
        return {"documento_id": str(documento.id), "nombre": documento.nombre_original, "paginas": total,
                "revisable": False, "hallazgos": [],
                "nota": None, "explicacion": "El archivo no tiene texto por página: la completitud se revisa a mano."}

    blancas = [p["numero"] for p in paginas if len(_limpio(p["texto"])) < MIN_TEXTO]
    if blancas:
        hallazgos.append({"tipo": "pagina_sin_texto", "paginas": blancas, "confianza": "media",
                          "detalle": f"{'La página' if len(blancas) == 1 else 'Las páginas'} {_rangos(blancas)} "
                                     f"no {'tiene' if len(blancas) == 1 else 'tienen'} texto: hoja en blanco o ilegible."})
    dificiles = [p["numero"] for p in paginas if p["origen"] == "ocr" and p["confianza"] is not None
                 and p["confianza"] < UMBRAL_OCR and p["numero"] not in blancas]
    if dificiles:
        hallazgos.append({"tipo": "ocr_dificil", "paginas": dificiles, "confianza": "media",
                          "detalle": f"{'La página' if len(dificiles) == 1 else 'Las páginas'} {_rangos(dificiles)} "
                                     "se leen con dificultad (OCR de confianza baja): revise que estén completas."})

    # Numeración propia del documento: «Página N de M», «Hoja N de M» o «Folio N».
    declarados: dict[int, int] = {}  # página del archivo -> número que dice el documento
    total_declarado: int | None = None
    for p in paginas:
        m = PAGINA_DE.search(p["texto"]) or HOJA_DE.search(p["texto"])
        if m:
            n, de = int(m.group(1)), int(m.group(2))
            if 0 < n <= de <= 5000:
                declarados[p["numero"]] = n
                total_declarado = max(total_declarado or 0, de)
            continue
        f = FOLIO.search(p["texto"])
        if f and 0 < int(f.group(1)) <= 5000:
            declarados[p["numero"]] = int(f.group(1))
    huecos = []
    secuencia = sorted(declarados.items())
    for (pa, na), (pb, nb) in zip(secuencia, secuencia[1:]):
        if pb == pa + 1 and nb > na + 1:
            faltan = list(range(na + 1, nb))
            huecos.append((pa, pb, faltan))
    for pa, pb, faltan in huecos:
        hallazgos.append({"tipo": "numeracion_salta", "paginas": [pa, pb], "faltantes": faltan, "confianza": "alta",
                          "detalle": f"La numeración salta de {faltan[0] - 1} a {faltan[-1] + 1} entre las páginas "
                                     f"{pa} y {pb} del archivo: {'falta la hoja' if len(faltan) == 1 else 'faltan las hojas'} "
                                     f"{_rangos(faltan)}."})
    texto_total = documento.texto_extraido or ""
    consta = CONSTA.search(texto_total)
    if consta:
        total_declarado = max(total_declarado or 0, int(consta.group(1)))
    # El total se compara solo si el documento lo declara con claridad: en «Página N de M»
    # de al menos dos hojas, o en «consta de N folios».
    if total_declarado and total_declarado != total and (len(declarados) >= 2 or consta):
        menos = total_declarado - total
        hallazgos.append({"tipo": "total_distinto", "paginas": [], "confianza": "alta" if consta else "media",
                          "detalle": f"El documento dice tener {total_declarado} "
                                     f"{consta.group(2).lower() if consta else 'páginas'} y el archivo trae {total}"
                                     + (f": {'falta' if menos == 1 else 'faltan'} {menos}." if menos > 0
                                        else ": trae más de las que declara (¿anexos o páginas repetidas?).")})

    vistas: dict[str, int] = {}
    repetidas = []
    for p in paginas:
        clave = _limpio(p["texto"])
        if len(clave) < 200:
            continue  # páginas cortas se parecen sin estar repetidas (sellos, membretes)
        huella = hashlib.sha256(clave.encode()).hexdigest()
        if huella in vistas:
            repetidas.append((vistas[huella], p["numero"]))
        else:
            vistas[huella] = p["numero"]
    if repetidas:
        hallazgos.append({"tipo": "pagina_repetida", "paginas": [b for _, b in repetidas], "confianza": "alta",
                          "detalle": "Páginas repetidas: " + "; ".join(f"la {b} es igual a la {a}" for a, b in repetidas[:6])
                                     + "."})

    if hallazgos:
        nota = "Revisión automática, por confirmar: " + " ".join(h["detalle"] for h in hallazgos)
    else:
        base = f"{total} página{'s' if total != 1 else ''}"
        if declarados:
            base += ", numeración continua" + (f" ({total_declarado} declaradas)" if total_declarado else "")
        nota = f"Completo según la revisión automática: {base}, sin hojas en blanco ni repetidas."
    return {"documento_id": str(documento.id), "nombre": documento.nombre_original, "paginas": total,
            "revisable": True, "hallazgos": hallazgos, "nota": nota,
            "explicacion": "Reglas sobre el texto de cada página (no IA). Confirme o corrija antes de publicar."}


def revisar_todos(db: Session, documentos) -> dict:
    """La revisión de los archivos de un trabajo, y la nota propuesta para la descripción."""
    revisiones = [revisar(db, d) for d in documentos]
    notas = [r["nota"] for r in revisiones if r["nota"]]
    if len(revisiones) > 1:
        nota = " ".join(f"«{r['nombre']}»: {r['nota']}" for r in revisiones if r["nota"]) or None
    else:
        nota = notas[0] if notas else None
    return {"documentos": revisiones, "nota_propuesta": nota,
            "con_hallazgos": sum(len(r["hallazgos"]) for r in revisiones)}
