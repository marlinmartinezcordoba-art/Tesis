"""
La descripción de la evaluación ciega en términos de RiC.

Antes, la archivista anotaba una ficha: título, alcance y entidades sueltas
con un «rol». Ahora describe como lo pide RiC-CM: **entidades** (nodos con
su clase de RiC-O) y **relaciones** (tripletas con una propiedad de RiC-O)
entre el documento que describe y esas entidades, o entre las entidades.
El rol deja de ser un dato del agente: es la relación (productor =
rico:hasCreator, destinatario = rico:hasAddressee…).

Aquí están:
- la conversión de la propuesta del motor (y de las anotaciones con el
  formato anterior) a entidades y relaciones, con la misma regla con que la
  publicación crea las relaciones del grafo (servicios/descripcion.py);
- la comparación de relaciones (precisión, exhaustividad y F1 por propiedad,
  y la confusión de propiedades: los mismos extremos con otra relación);
- la conformidad de cada descripción con RiC-O 1.1: contra el mapeo único
  (servicios/ric_o.py) y, por separado, contra el archivo OWL oficial
  (servicios/conformidad_rico.verificar_owl).

Decisiones en documentacion/modulo-evaluacion.md (versión 2).
"""

from difflib import SequenceMatcher

from app.servicios import ric_o
from app.servicios.evaluacion import TIPOS, normalizar, texto_de

DOCUMENTO = "documento"  # el Record que se describe (cada documento de la evaluación es una unidad documental)
CLASE_DOCUMENTO = "Record"
SUBTIPOS_AGENTE = tuple(ric_o.CLASE_AGENTE)  # persona, familia, entidad_corporativa, grupo, cargo, mecanismo
# rico:hasDocumentaryFormType: en el mapeo es un nodo de apoyo (APOYO), no una fila de «relaciones».
FORMA = "forma_documental"

# Lo que una archivista puede afirmar al describir un documento desde su
# texto: las propiedades del mapeo que unen el documento con su contexto o
# las entidades de contexto entre sí. Quedan fuera las estructurales
# (jerarquía, instanciaciones, secuencia, migración, hito, TRD): no se
# describen leyendo un documento.
PROPIEDADES = (
    "has_creator", "has_author", "has_sender", "has_addressee", "has_accumulator", "has_or_had_holder",
    "has_or_had_subject", "is_creation_date_of", "is_date_associated_with", "is_or_was_location_of",
    "contains_or_contained", "documents", "has_activity_type", "performs_or_performed", "has_direct_subevent",
    "regulates_or_regulated", "issued_by", "authorizes", "has_or_had_subordinate", "has_successor",
    "is_agent_associated_with_agent", "occupies_or_occupied", "has_family_association_with", "has_or_had_member",
    "has_or_had_subdivision", "exists_or_existed_in", "is_or_was_leader_of", FORMA,
)
MAX_RELACIONES = 400
# Nombre archivístico de uso común, junto a la etiqueta oficial en español de
# RiC-O (que a veces no se entiende sola: hasAddressee es «se dirige a»).
PAPEL = {
    "has_creator": "Productor", "has_author": "Autor", "has_sender": "Remitente", "has_addressee": "Destinatario",
    "has_accumulator": "Acumulador", "has_or_had_holder": "Custodio", "has_or_had_subject": "Tema o mencionado",
    "is_creation_date_of": "Fecha de creación", "is_date_associated_with": "Fecha asociada",
    "is_or_was_location_of": "Lugar de expedición o localización", "contains_or_contained": "Lugar que contiene a otro",
    "documents": "Actividad que documenta", "has_activity_type": "Función (tipo de actividad)",
    "performs_or_performed": "Agente que ejerce la actividad", "has_direct_subevent": "Subactividad",
    "regulates_or_regulated": "Norma que regula", "issued_by": "Quién expide la norma",
    "authorizes": "Norma que faculta al agente", "has_or_had_subordinate": "Subordinación",
    "has_successor": "Sucesión", "is_agent_associated_with_agent": "Agentes asociados",
    "occupies_or_occupied": "Persona que ocupa un cargo", "has_family_association_with": "Parentesco",
    "has_or_had_member": "Miembro de un grupo", "has_or_had_subdivision": "Dependencia de una entidad",
    "exists_or_existed_in": "Cargo dentro de una entidad", "is_or_was_leader_of": "Quien dirige un grupo",
    FORMA: "Tipo documental",
}


class ErrorRic(ValueError):
    pass


# --- Clases y propiedades ---------------------------------------------------------------------------


def clase(entidad: dict | None) -> str:
    """Clase RiC-O de un extremo: el documento o una entidad anotada."""
    if entidad is None:
        return CLASE_DOCUMENTO
    tipo = entidad.get("tipo")
    if tipo == "agente":
        return ric_o.CLASE_AGENTE.get(entidad.get("subtipo") or "", "Agent")
    if tipo == "fecha":
        return "Date"
    return ric_o.CLASE_VOCABULARIO[tipo]


def admitidas(codigo: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if codigo == FORMA:
        _, origen, destino = ric_o.APOYO[FORMA]
        return tuple(origen), (destino,)
    p = ric_o.PROPIEDADES[codigo]
    return p.origen, p.destino


def nombre_rico(codigo: str) -> str:
    return ric_o.uri(codigo)


def _admite(clase_nodo: str, admitidas_: tuple[str, ...]) -> bool:
    if "Thing" in admitidas_:
        return True
    if clase_nodo == "Agent":  # agente sin subtipo: vale solo si cualquier agente vale
        return all(ric_o._es(a, admitidas_) for a in ric_o.AGENTES)
    return ric_o._es(clase_nodo, admitidas_)


def _clase_es(c: str) -> str:
    return ric_o.etiqueta_es(c) or c


def problema_de_uso(codigo: str, origen: dict | None, destino: dict | None) -> str | None:
    """Por qué esa tripleta no es válida en RiC-O 1.1 (o None si lo es)."""
    o, d = admitidas(codigo)
    co, cd = clase(origen), clase(destino)
    for extremo, c, lista in (("origen", co, o), ("destino", cd, d)):
        if not _admite(c, lista):
            if c == "Agent":
                return (f"{nombre_rico(codigo)}: indique el subtipo del agente; la propiedad solo admite "
                        f"{', '.join(lista)} como {extremo}.")
            return f"{nombre_rico(codigo)} no admite {c} como {extremo} (admite {', '.join(lista)})."
    return None


TIPOS_DE_EXTREMO = (("documento", None), *[("agente", s) for s in SUBTIPOS_AGENTE], ("agente", None),
                    *[(t, None) for t in TIPOS if t != "agente"])


def catalogo() -> list[dict]:
    """Las propiedades disponibles, con los tipos de extremo que admite cada
    una, para que la pantalla solo ofrezca relaciones válidas."""
    salida = []
    for codigo in PROPIEDADES:
        o, d = admitidas(codigo)
        p = ric_o.PROPIEDADES.get(codigo)
        rico = nombre_rico(codigo)

        def extremos(lista):
            return [f"{t}:{s}" if s else t for t, s in TIPOS_DE_EXTREMO
                    if _admite(CLASE_DOCUMENTO if t == "documento" else clase({"tipo": t, "subtipo": s}), lista)]
        salida.append({"codigo": codigo, "rico": rico, "papel": PAPEL[codigo],
                       "etiqueta": ric_o.etiqueta_es(rico.split(":")[1]) or rico,
                       "codigo_cm": p.codigo_cm if p else None, "origen": extremos(o), "destino": extremos(d)})
    return salida


# --- De la propuesta del motor (o del formato anterior) a RiC ---------------------------------------


def _clave_identidad(e: dict) -> tuple:
    return e.get("tipo"), (e.get("edtf") or "").strip() if e.get("tipo") == "fecha" and e.get("edtf") \
        else normalizar(e.get("valor"))


def desde_roles(datos: dict | None, *, sin_rol_es_tema: bool = True) -> dict:
    """Entidades con «rol» y cadena de actividad (propuesta del motor o
    anotación con el formato anterior) → entidades y relaciones RiC. Una
    misma entidad con dos roles es un solo nodo con dos relaciones. Las
    relaciones son las que crearía la publicación. Un agente sin rol válido
    es tema del documento, como lo deja el motor (servicios/motor.py); en una
    anotación de una persona (sin_rol_es_tema=False) queda sin relación: no
    se le inventa una."""
    from app.servicios.descripcion import RELACION_POR_ROL

    datos = datos or {}
    originales = [e for e in datos.get("entidades", []) if e.get("tipo") in TIPOS and (e.get("valor") or "").strip()]
    nodos: dict[tuple, dict] = {}
    clave_de: dict[str, str] = {}  # clave del motor → clave del nodo
    for i, e in enumerate(originales):
        ident = _clave_identidad(e)
        if ident not in nodos:
            nodos[ident] = {"clave": f"e{len(nodos) + 1}", "tipo": e["tipo"], "valor": " ".join(e["valor"].split()),
                            "subtipo": e.get("subtipo") if e["tipo"] == "agente" else None,
                            "edtf": (e.get("edtf") or e.get("fecha_normalizada")) if e["tipo"] == "fecha" else None}
        elif e["tipo"] == "agente" and not nodos[ident]["subtipo"]:
            nodos[ident]["subtipo"] = e.get("subtipo")
        clave_de[e.get("clave") or f"_{i}"] = nodos[ident]["clave"]
    relaciones: list[dict] = []

    def rel(origen, propiedad, destino):
        r = {"origen": origen, "propiedad": propiedad, "destino": destino}
        if origen and destino and r not in relaciones:
            relaciones.append(r)

    citados = {e.get("mandato_clave") for e in originales if e["tipo"] == "actividad"}
    for i, e in enumerate(originales):
        yo = clave_de[e.get("clave") or f"_{i}"]
        tipo = e["tipo"]
        if tipo == "agente":
            par = RELACION_POR_ROL.get(("agente", e.get("rol")))
            if par or sin_rol_es_tema:
                rel(DOCUMENTO, par[0] if par else "has_or_had_subject", yo)
        elif tipo == "lugar":
            if e.get("rol") == "expedicion":
                rel(yo, "is_or_was_location_of", DOCUMENTO)
            else:
                rel(DOCUMENTO, "has_or_had_subject", yo)
        elif tipo == "fecha":
            rel(yo, "is_creation_date_of", DOCUMENTO)
        elif tipo == "forma_documental":
            rel(DOCUMENTO, FORMA, yo)
        elif tipo == "mandato" and e.get("clave") not in citados:
            rel(DOCUMENTO, "has_or_had_subject", yo)
        elif tipo == "actividad":
            rel(DOCUMENTO, "documents", yo)
            tipo_a, agente, mandato = (clave_de.get(e.get(c) or "") for c in ("tipo_clave", "agente_clave",
                                                                              "mandato_clave"))
            rel(yo, "has_activity_type", tipo_a)
            rel(agente, "performs_or_performed", yo)
            rel(mandato, "regulates_or_regulated", yo)
            rel(mandato, "authorizes", agente)
    return {"titulo": (datos.get("titulo") or "").strip() or None,
            "alcance": (datos.get("alcance") or datos.get("alcance_contenido") or "").strip() or None,
            "entidades": list(nodos.values()), "relaciones": relaciones}


def a_ric(datos: dict | None) -> dict:
    """Cualquier descripción de la evaluación en formato RiC."""
    datos = datos or {}
    if "relaciones" in datos:
        return {"titulo": datos.get("titulo"), "alcance": datos.get("alcance"),
                "entidades": list(datos.get("entidades") or []), "relaciones": list(datos.get("relaciones") or [])}
    return desde_roles(datos)


def limpiar(datos: dict) -> dict:
    """Valida lo que envía la archivista: entidades con clave única, tipo y
    valor; relaciones entre el documento y entidades existentes, con una
    propiedad de RiC-O de la lista. Un borrador puede tener relaciones que
    RiC-O no admite (se informan); enviarlo, no."""
    from app.servicios import fechas

    if "relaciones" not in datos:  # cliente con el formato anterior
        datos = desde_roles(datos, sin_rol_es_tema=False)
    entidades, claves = [], set()
    for e in (datos.get("entidades") or [])[:200]:
        tipo = e.get("tipo")
        valor = " ".join(str(e.get("valor") or "").split())[:300]
        if tipo not in TIPOS or not valor:
            continue
        clave = str(e.get("clave") or "").strip()[:20] or f"e{len(entidades) + 1}"
        if clave in claves or clave == DOCUMENTO:
            raise ErrorRic(f"La clave «{clave}» se repite.")
        claves.add(clave)
        subtipo = e.get("subtipo") if tipo == "agente" and e.get("subtipo") in SUBTIPOS_AGENTE else None
        edtf = (e.get("edtf") or "").strip() or None if tipo == "fecha" else None
        if edtf:
            try:
                edtf = fechas.interpretar(edtf).edtf
            except fechas.FechaInvalida as exc:
                raise ErrorRic(f"La fecha «{valor}»: {exc}") from exc
        entidades.append({"clave": clave, "tipo": tipo, "valor": valor, "subtipo": subtipo, "edtf": edtf})
    relaciones = []
    for r in (datos.get("relaciones") or [])[:MAX_RELACIONES]:
        origen, propiedad, destino = (str(r.get(c) or "").strip() for c in ("origen", "propiedad", "destino"))
        if propiedad not in PROPIEDADES:
            raise ErrorRic(f"«{propiedad or 'sin propiedad'}» no es una relación de RiC-O disponible para describir.")
        for extremo in (origen, destino):
            if extremo != DOCUMENTO and extremo not in claves:
                raise ErrorRic("Una relación apunta a una entidad que no está en la descripción (quizá se quitó).")
        if origen == destino:
            raise ErrorRic("Una relación une dos entidades distintas.")
        nueva = {"origen": origen, "propiedad": propiedad, "destino": destino}
        if nueva not in relaciones:
            relaciones.append(nueva)
    return {"titulo": (datos.get("titulo") or "").strip()[:300] or None,
            "alcance": (datos.get("alcance") or "").strip()[:5000] or None,
            "entidades": entidades, "relaciones": relaciones}


# --- Conformidad con RiC-O 1.1 ----------------------------------------------------------------------


def _grafo(datos: dict):
    """La descripción como grafo RDF mínimo (solo clases y relaciones), para
    contrastarla con el OWL oficial sin pasar por el mapeo del sistema."""
    from rdflib import RDF, Graph, Namespace, URIRef

    rico = Namespace(ric_o.RICO)
    g = Graph()
    nodo = {DOCUMENTO: URIRef("urn:ricora:evaluacion:documento")}
    g.add((nodo[DOCUMENTO], RDF.type, rico[CLASE_DOCUMENTO]))
    for e in datos["entidades"]:
        nodo[e["clave"]] = URIRef(f"urn:ricora:evaluacion:{e['clave']}")
        g.add((nodo[e["clave"]], RDF.type, rico[clase(e)]))
    for r in datos["relaciones"]:
        if r["origen"] in nodo and r["destino"] in nodo and r["propiedad"] in PROPIEDADES:
            g.add((nodo[r["origen"]], rico[nombre_rico(r["propiedad"]).split(":")[1]], nodo[r["destino"]]))
    return g


def conformidad(datos: dict | None) -> dict:
    """¿La descripción es RiC válida? Cada problema dice por qué.

    - Mapeo único (perfil del sistema): cada relación tiene una propiedad de
      RiC-O y su origen y destino son de las clases que esa propiedad admite.
    - Reglas del perfil: un título; a lo sumo una forma documental; una
      actividad con a lo sumo un tipo; ninguna entidad suelta (en RiC una
      entidad sin relación no describe nada).
    - OWL oficial de RiC-O 1.1: dominio y rango de cada propiedad usada."""
    from app.servicios.conformidad_rico import verificar_owl

    d = a_ric(datos)
    por_clave = {e["clave"]: e for e in d["entidades"] if e.get("clave")}
    problemas, validas = [], 0
    for r in d["relaciones"]:
        propiedad = r.get("propiedad")
        if propiedad not in PROPIEDADES:
            problemas.append(f"«{propiedad}» no es una propiedad de RiC-O disponible.")
            continue
        extremos = []
        for k in (r.get("origen"), r.get("destino")):
            extremos.append(None if k == DOCUMENTO else por_clave.get(k, False))
        if False in extremos:
            problemas.append(f"{nombre_rico(propiedad)} apunta a una entidad que no está en la descripción.")
            continue
        p = problema_de_uso(propiedad, *extremos)
        if p:
            problemas.append(p)
        else:
            validas += 1
    if not (d.get("titulo") or "").strip():
        problemas.append("Falta el título (rico:title, exactamente uno).")
    if sum(1 for r in d["relaciones"] if r.get("propiedad") == FORMA and r.get("origen") == DOCUMENTO) > 1:
        problemas.append("El documento tiene más de una forma documental (rico:hasDocumentaryFormType, a lo sumo una).")
    for e in d["entidades"]:
        if e.get("tipo") == "actividad" and sum(1 for r in d["relaciones"] if r.get("propiedad") == "has_activity_type"
                                                and r.get("origen") == e.get("clave")) > 1:
            problemas.append(f"La actividad «{e['valor']}» tiene más de un tipo de actividad (a lo sumo uno).")
        if not any(e.get("clave") in (r.get("origen"), r.get("destino")) for r in d["relaciones"]):
            problemas.append(f"«{e['valor']}» no está relacionada con nada: en RiC una entidad suelta no describe "
                             "el documento.")
    owl = [] if any(r.get("propiedad") not in PROPIEDADES for r in d["relaciones"]) else verificar_owl(_grafo(d))
    problemas += [f"OWL oficial: {p}" for p in owl]
    return {"conforme": not problemas, "relaciones": len(d["relaciones"]), "relaciones_validas": validas,
            "problemas": problemas}


# --- Comparación de relaciones ----------------------------------------------------------------------


def tripletas(datos: dict | None) -> list[tuple[str, dict | None, dict | None]]:
    """(propiedad, origen, destino) con las entidades de los extremos; None
    es el documento. Se omiten las relaciones con extremos que no existen."""
    d = a_ric(datos)
    por_clave = {e["clave"]: e for e in d["entidades"] if e.get("clave")}
    salida = []
    for r in d["relaciones"]:
        extremos = [None if k == DOCUMENTO else por_clave.get(k) for k in (r.get("origen"), r.get("destino"))]
        if r.get("propiedad") in PROPIEDADES and all(x is not None or k == DOCUMENTO
                                                     for x, k in zip(extremos, (r.get("origen"), r.get("destino")))):
            salida.append((r["propiedad"], extremos[0], extremos[1]))
    return salida


def _parecido_extremo(a: dict | None, b: dict | None) -> float:
    if a is None or b is None:
        return 1.0 if a is None and b is None else 0.0
    if a.get("tipo") != b.get("tipo"):
        return 0.0
    x, y = texto_de(a), texto_de(b)
    return 1.0 if x == y else SequenceMatcher(None, x, y).ratio()


def _parecido(s, r) -> float:
    return min(_parecido_extremo(s[1], r[1]), _parecido_extremo(s[2], r[2]))


def emparejar(sistema: list, referencia: list, umbral: float) -> tuple[int, list[tuple[str, str]]]:
    """Pares uno a uno de tripletas con la misma propiedad y extremos
    parecidos desde el umbral (1.0 = iguales tras normalizar). Después, entre
    las que quedaron sin pareja, las confusiones: mismos extremos, otra
    propiedad (p. ej. el motor dijo destinatario y la archivista, productor)."""
    candidatos = sorted(((_parecido(s, r), i, j) for i, s in enumerate(sistema) for j, r in enumerate(referencia)
                         if s[0] == r[0]), reverse=True)
    usados_s, usados_r = set(), set()
    for parecido, i, j in candidatos:
        if parecido < umbral:
            break
        if i not in usados_s and j not in usados_r:
            usados_s.add(i)
            usados_r.add(j)
    vp = len(usados_s)
    confusiones = []
    otros = sorted(((_parecido(s, r), i, j) for i, s in enumerate(sistema) for j, r in enumerate(referencia)
                    if s[0] != r[0] and i not in usados_s and j not in usados_r), reverse=True)
    for parecido, i, j in otros:
        if parecido < umbral:
            break
        if i not in usados_s and j not in usados_r:
            usados_s.add(i)
            usados_r.add(j)
            confusiones.append((sistema[i][0], referencia[j][0]))
    return vp, confusiones


def conteo_por_propiedad(sistema: list, referencia: list, umbral: float) -> tuple[dict, list]:
    """VP, FP y FN por propiedad, y las confusiones."""
    salida: dict[str, dict] = {}
    for p in sorted({t[0] for t in sistema} | {t[0] for t in referencia}):
        s = [t for t in sistema if t[0] == p]
        r = [t for t in referencia if t[0] == p]
        vp, _ = emparejar(s, r, umbral)
        salida[p] = {"vp": vp, "fp": len(s) - vp, "fn": len(r) - vp}
    _, confusiones = emparejar(sistema, referencia, umbral)
    return salida, confusiones
