"""
Búsqueda asistida en Wikidata para enlazar una autoridad con la web de datos.

RICORA propone candidatos; la archivista decide. Nada se enlaza solo: el
enlace se registra con el mismo camino que un identificador escrito a mano
(autoridad.agregar_identificador), queda en la auditoría y sale en el grafo
como owl:sameAs. Si el candidato tiene identificador VIAF (propiedad P214 de
Wikidata), se ofrece también, para que la archivista lo confirme.

Solo se envía a Wikidata el nombre de la autoridad: nunca documentos ni datos
de personas distintos del nombre que ya es la forma autorizada.
"""

import logging

import httpx

log = logging.getLogger("ricora.wikidata")

API = "https://www.wikidata.org/w/api.php"
AGENTE = "RICORA/1.0 (sistema de archivo historico; enlace de autoridades)"
SEGUNDOS = 10
MAXIMO = 7


class ErrorWikidata(Exception):
    pass


def _pedir(params: dict) -> dict:
    try:
        r = httpx.get(API, params={**params, "format": "json"}, headers={"User-Agent": AGENTE}, timeout=SEGUNDOS)
    except httpx.HTTPError as exc:
        raise ErrorWikidata("No hubo conexión con Wikidata. Intente de nuevo en un momento.") from exc
    if r.status_code != 200:
        log.warning("Wikidata respondió %s", r.status_code)
        raise ErrorWikidata(f"Wikidata respondió con un error ({r.status_code}).")
    try:
        return r.json()
    except ValueError as exc:
        raise ErrorWikidata("La respuesta de Wikidata no se pudo leer.") from exc


def _texto(entidad: dict, campo: str) -> str | None:
    valores = entidad.get(campo) or {}
    for idioma in ("es", "en"):
        if idioma in valores:
            return valores[idioma].get("value")
    return next((v.get("value") for v in valores.values()), None)


def _viaf(entidad: dict) -> str | None:
    for afirmacion in (entidad.get("claims") or {}).get("P214", []):
        valor = ((afirmacion.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(valor, str) and valor.isdigit():
            return valor
    return None


def candidatos(nombre: str, ya_enlazados: set[str] | None = None) -> list[dict]:
    """Hasta siete entidades de Wikidata cuyo nombre se parece, con su descripción y su VIAF si lo tienen."""
    nombre = " ".join((nombre or "").split())[:200]
    if len(nombre) < 2:
        raise ErrorWikidata("Escriba al menos dos letras para buscar.")
    hallados = _pedir({"action": "wbsearchentities", "search": nombre, "language": "es", "uselang": "es",
                       "type": "item", "limit": MAXIMO}).get("search", [])
    ids = [h["id"] for h in hallados if str(h.get("id", "")).startswith("Q")]
    if not ids:
        return []
    entidades = _pedir({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|descriptions|claims",
                        "languages": "es|en"}).get("entities", {})
    salida = []
    for qid in ids:
        e = entidades.get(qid, {})
        busqueda = next((h for h in hallados if h["id"] == qid), {})
        salida.append({
            "qid": qid,
            "etiqueta": _texto(e, "labels") or busqueda.get("label") or qid,
            "descripcion": _texto(e, "descriptions") or busqueda.get("description"),
            "viaf": _viaf(e),
            "url": f"https://www.wikidata.org/wiki/{qid}",
            "ya_enlazado": qid in (ya_enlazados or set()),
        })
    return salida
