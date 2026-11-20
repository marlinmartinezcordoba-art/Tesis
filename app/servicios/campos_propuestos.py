"""Los campos de la descripción que RICORA propone, además de las entidades.

La descripción exhaustiva la propone el sistema y la aprueba una persona. Aquí se arman las
propuestas de los campos que no son entidades, cada una con su evidencia y su certeza:

- Idioma (RiC-A25): lo identifica el motor de IA en el texto.
- Tipo de contenido (RiC-A10): «texto» cuando el documento tiene texto legible.
- Extensión (RiC-A35): los folios, a partir de las páginas del archivo digital.
- Estado del documento (RiC-A39): solo si el texto declara ser copia o borrador.
- Nota de integridad (RiC-A24): la revisión de páginas por reglas (servicios/completitud).
- Documento asociado (RiC-R022): un documento que el texto cita y que ya está descrito en RICORA.

Nada se aplica solo: la pantalla los muestra como propuestas y la persona acepta o descarta
cada uno, o todos de una vez. Ninguno decide el acceso: lo decide la institución (TCA).
"""

import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.recurso_documental import RecursoDocumental

MINIMO_PALABRAS = 20
ENCABEZADO = 1500

_COPIA_AUTENTICA = re.compile(r"\b(fiel\s+copia|copia\s+(fiel|aut[eé]ntica|autenticada))\b", re.I)
_COPIA = re.compile(r"\b(es\s+copia|copia\s+de(l)?\s+original|copia)\b", re.I)
_BORRADOR = re.compile(r"\b(borrador|proyecto\s+de\s+(resoluci[oó]n|decreto|acuerdo|oficio))\b", re.I)


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)).lower()


def _fragmento(texto: str, m: re.Match) -> str:
    inicio, fin = max(0, m.start() - 40), min(len(texto), m.end() + 40)
    return " ".join(texto[inicio:fin].split())


def _estado(texto: str) -> dict | None:
    cabeza = texto[:ENCABEZADO]
    for regex, clave, nombre in ((_COPIA_AUTENTICA, "copia_autentica", "Copia auténtica"),
                                 (_BORRADOR, "borrador", "Borrador"), (_COPIA, "copia", "Copia")):
        m = regex.search(cabeza)
        if m:
            return {"campo": "estado_documento", "valor": clave, "mostrar": nombre, "confianza": 0.6, "origen": "regla",
                    "evidencia": f"El encabezado dice «{_fragmento(cabeza, m)}»."}
    return None


def _citado_en_ricora(db: Session, fondo_id: uuid.UUID, citados: list[dict], excluir: set) -> dict | None:
    """El primer documento citado cuyo número y tipo aparecen en el título de una descripción publicada."""
    publicadas = db.execute(select(RecursoDocumental.id, RecursoDocumental.titulo).where(
        RecursoDocumental.fondo_id == fondo_id, RecursoDocumental.publicado_en.is_not(None),
        RecursoDocumental.nivel.in_(("unidad_documental", "expediente")))).all()
    if not publicadas:
        return None
    for c in citados or []:
        valor = _sin_tildes(c.get("valor") or "")
        numeros = re.findall(r"\d{3,}", valor)
        palabra = (re.findall(r"[a-z]{4,}", valor) or [""])[0]
        if not numeros:
            continue
        buscado = int(numeros[0])  # «0818» y «818» son el mismo número
        for rid, titulo in publicadas:
            t = _sin_tildes(titulo)
            if rid in excluir:
                continue
            # El número propio del documento es el primero de su título («Resolución No. 1919 … contra la 0818»).
            propio = re.findall(r"\d+", t)[:1]
            if propio and int(propio[0]) == buscado and (not palabra or palabra in t):
                return {"campo": "asociado_a", "valor": {"id": str(rid), "titulo": titulo}, "mostrar": titulo,
                        "confianza": 0.8, "origen": "regla",
                        "evidencia": f"El texto cita «{c.get('valor')}»" + (f": «{c['fragmento']}»." if c.get("fragmento") else ".")}
    return None


def proponer(db: Session, *, fondo_id: uuid.UUID, nivel: str, documentos: list, propuesta: dict | None,
             completitud: dict | None, recurso_id: uuid.UUID | None = None) -> list[dict]:
    """Las propuestas de campos para la pantalla de descripción, en el orden en que se muestran."""
    salida: list[dict] = []
    p = propuesta or {}
    textos = [d.texto_extraido or "" for d in documentos]
    if p.get("idiomas"):
        salida.append({"campo": "idiomas", "valor": p["idiomas"], "mostrar": ", ".join(p["idiomas"]),
                       "confianza": p.get("confianza_idiomas"), "origen": "motor",
                       "evidencia": "El motor de IA identificó la lengua del texto."})
    palabras = sum(len(t.split()) for t in textos)
    if palabras >= MINIMO_PALABRAS:
        salida.append({"campo": "tipos_contenido", "valor": ["texto"], "mostrar": "Texto", "confianza": 0.9,
                       "origen": "regla", "evidencia": f"El documento tiene {palabras} palabras de texto legible."})
    paginas = [d.paginas for d in documentos]
    if paginas and all(isinstance(n, int) and n > 0 for n in paginas):
        total = sum(paginas)
        salida.append({"campo": "folios", "valor": total, "mostrar": f"{total} folio(s)", "confianza": 0.7, "origen": "regla",
                       "evidencia": f"El archivo digital tiene {total} página(s). En un impreso cada página suele ser un "
                                    "folio; si hay hojas escritas por ambas caras, corríjalo con el original."})
    if nivel in ("unidad_documental", "parte_documental") and textos:
        estado = _estado(textos[0])
        if estado:
            salida.append(estado)
    nota = (completitud or {}).get("nota_propuesta")
    if nota:
        salida.append({"campo": "nota_integridad", "valor": nota, "mostrar": nota, "confianza": None, "origen": "regla",
                       "evidencia": "Revisión de la numeración y del texto de cada página."})
    asociado = _citado_en_ricora(db, fondo_id, p.get("documentos_citados") or [], {recurso_id} if recurso_id else set())
    if asociado:
        salida.append(asociado)
    return salida
