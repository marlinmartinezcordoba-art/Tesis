"""La forma documental de un documento sale de las tipologías de la TRD.

Las tipologías documentales de cada serie y subserie de la TRD son las formas documentales del fondo
(rico:DocumentaryFormType, unidas a su serie por hasOrHadSomeMembersWithDocumentaryFormType). Al
describir, la forma se elige entre ellas: la que el documento declara en su encabezado («RESOLUCIÓN
No. …», «ACTA DE …»). Si el motor propuso una que no es tipología de la TRD y el encabezado dice una
que sí lo es, se propone la de la TRD con su fragmento como evidencia. La persona confirma.
"""

import unicodedata
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.descripcion import EntidadVocabulario
from app.models.recurso_documental import RecursoDocumental

# El encabezado: el documento declara su forma en sus primeras líneas.
ENCABEZADO = 800
CONFIANZA_ENCABEZADO = 0.9


def tipologias(db: Session, fondo_id: uuid.UUID) -> list[EntidadVocabulario]:
    """Las formas documentales activas que la TRD asigna a alguna serie o subserie del fondo."""
    ids = set(db.scalars(select(func.unnest(RecursoDocumental.formas_miembros)).where(
        RecursoDocumental.fondo_id == fondo_id)))
    if not ids:
        return []
    return list(db.scalars(select(EntidadVocabulario).where(
        EntidadVocabulario.id.in_(ids), EntidadVocabulario.estado == "activa",
        EntidadVocabulario.clase == "forma_documental")))


def _normalizado_con_posiciones(texto: str) -> tuple[str, list[int]]:
    """El texto sin tildes, en minúsculas y con los espacios colapsados, y para cada carácter su
    posición en el original (para citar el fragmento exacto)."""
    salida, posiciones, espacio = [], [], False
    for i, c in enumerate(texto):
        if c.isspace():
            if not espacio and salida:
                salida.append(" ")
                posiciones.append(i)
            espacio = True
            continue
        espacio = False
        for d in unicodedata.normalize("NFKD", c):
            if not unicodedata.combining(d):
                salida.append(d.lower())
                posiciones.append(i)
    return "".join(salida), posiciones


def _es_palabra(texto: str, i: int, j: int) -> bool:
    return (i == 0 or not texto[i - 1].isalnum()) and (j >= len(texto) or not texto[j].isalnum())


def en_encabezado(formas: list[EntidadVocabulario], documentos) -> tuple[EntidadVocabulario, object, int, str] | None:
    """La tipología que aparece primero en el encabezado de alguno de los documentos (a igual posición,
    la de nombre más largo: «Acta de comité» antes que «Acta»). Devuelve (forma, documento, inicio, fragmento)."""
    from app.servicios.vocabulario import normalizar

    mejor = None
    for doc in documentos:
        original = (doc.texto or "")[: ENCABEZADO * 2]
        texto, pos = _normalizado_con_posiciones(original)
        texto, pos = texto[:ENCABEZADO], pos[:ENCABEZADO]
        for f in formas:
            nombre = normalizar(f.nombre)
            if not nombre:
                continue
            i = texto.find(nombre)
            while i >= 0 and not _es_palabra(texto, i, i + len(nombre)):
                i = texto.find(nombre, i + 1)
            if i < 0:
                continue
            clave = (i, -len(nombre))
            if mejor is None or clave < mejor[0]:
                a, b = pos[i], pos[i + len(nombre) - 1] + 1
                mejor = (clave, f, doc, a, original[a:b])
        if mejor is not None:
            break  # el primer documento que la declara
    return None if mejor is None else mejor[1:]


def ajustar(db: Session, fondo_id: uuid.UUID, propuesta, documentos) -> None:
    """Deja en la propuesta del motor una forma documental que sea tipología de la TRD, cuando el
    encabezado de un documento declara una. Sin TRD o sin tipología en el encabezado, no cambia nada."""
    from app.servicios.motor import EntidadPropuesta

    formas = tipologias(db, fondo_id)
    if not formas:
        return
    ids = {str(f.id) for f in formas}
    propuestas = [e for e in propuesta.entidades if e.tipo == "forma_documental"]
    if any(e.existente_id in ids for e in propuestas):
        return  # el motor ya eligió una tipología de la TRD
    hallada = en_encabezado(formas, documentos)
    if hallada is None:
        return
    forma, doc, inicio, fragmento = hallada
    e = propuestas[0] if propuestas else EntidadPropuesta(clave="forma_trd", tipo="forma_documental", valor=forma.nombre)
    e.valor, e.existente_id, e.existente_nombre = forma.nombre, str(forma.id), forma.nombre
    e.fragmento, e.documento_id, e.inicio, e.fragmento_localizado = fragmento, str(doc.id), inicio, True
    e.confianza = max(e.confianza or 0.0, CONFIANZA_ENCABEZADO)
    propuesta.entidades = [x for x in propuesta.entidades if x.tipo != "forma_documental" or x is e]
    if not propuestas:
        propuesta.entidades.append(e)
