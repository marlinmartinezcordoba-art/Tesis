"""
Página web de una entidad en su URI (/id/…), para quien la abre en el navegador.

La misma URI entrega RiC-O a una máquina (Turtle o JSON-LD) y, a una persona
que pide text/html, esta ficha legible: su clase de RiC-O con la etiqueta
oficial en español, sus atributos, sus relaciones con enlaces a las otras
URI, quién la afirmó (la autoría del criterio nativo 7) y los enlaces a sus
datos. Se arma con las mismas tripletas que la versión para máquinas
(exportacion_rico.descripcion_de): nunca dice algo distinto.
"""

from html import escape

from rdflib import OWL, RDF, RDFS, SKOS, Graph, Literal, Namespace, URIRef

from app.servicios import ric_o

RICO = Namespace(str(ric_o.RICO))
NOMBRES_EXTRA = {str(RDFS.label): "etiqueta", str(OWL.sameAs): "la misma entidad en", str(SKOS.prefLabel): "término preferido",
                 str(SKOS.altLabel): "otra forma", str(SKOS.inScheme): "en el esquema", str(SKOS.exactMatch): "equivale a",
                 str(SKOS.broader): "término más amplio", str(SKOS.narrower): "término más específico"}


def _corto(uri: str) -> str:
    return uri.split("#")[-1] if "#" in uri else uri.rstrip("/").split("/")[-1]


def _nombre_propiedad(p: URIRef) -> str:
    texto = str(p)
    if texto in NOMBRES_EXTRA:
        return NOMBRES_EXTRA[texto]
    if texto.startswith(str(RICO)):
        return ric_o.etiqueta_es(_corto(texto)) or f"rico:{_corto(texto)}"
    return _corto(texto)


def _etiqueta(g: Graph, nodo) -> str:
    for p in (RDFS.label, RICO.name, RICO.title, SKOS.prefLabel):
        v = g.value(nodo, p)
        if v is not None:
            return str(v)
    return _corto(str(nodo))


def _clases(g: Graph, nodo) -> list[str]:
    return [f"{ric_o.etiqueta_es(_corto(str(c))) or _corto(str(c))} (rico:{_corto(str(c))})"
            for c in g.objects(nodo, RDF.type) if str(c).startswith(str(RICO))]


def _valor(g: Graph, o, base: str) -> str:
    if isinstance(o, Literal):
        return escape(str(o))
    texto = str(o)
    if texto.startswith(base):
        return f'<a href="{escape(texto)}">{escape(_etiqueta(g, o))}</a>'
    if texto.startswith(("http://", "https://")) and not texto.startswith(str(RICO)):
        return f'<a href="{escape(texto)}" rel="noreferrer">{escape(texto)}</a>'
    return escape(_etiqueta(g, o))


def _relacion_legible(g: Graph, rel, base: str) -> str:
    """«Oficio 301 · tiene como creador a · Alcaldía de Tunja», con la URI del nodo de relación."""
    etiqueta = _etiqueta(g, rel)
    nombre = etiqueta.split("rico:")[-1] if "rico:" in etiqueta else ""
    verbo = (ric_o.etiqueta_es(nombre) if nombre else None) or etiqueta
    desde, hacia = g.value(rel, RICO.relationHasSource), g.value(rel, RICO.relationHasTarget)
    partes = [escape(_etiqueta(g, desde)) if desde is not None else "—", f'<a href="{escape(str(rel))}">{escape(verbo)}</a>',
              escape(_etiqueta(g, hacia)) if hacia is not None else "—"]
    return " · ".join(partes)


def html(g: Graph, nodo: URIRef, base: str, institucion: str) -> str:
    titulo = _etiqueta(g, nodo)
    clases = _clases(g, nodo)
    filas, entrantes, autoria = [], [], []
    for p, o in sorted(g.predicate_objects(nodo), key=lambda x: (_nombre_propiedad(x[0]), str(x[1]))):
        if p == RDF.type:
            continue
        filas.append((_nombre_propiedad(p), _valor(g, o, base)))
    for s, p in sorted(g.subject_predicates(nodo), key=lambda x: (_nombre_propiedad(x[1]), str(x[0]))):
        if str(s).startswith(str(nodo) + "/"):
            continue  # nodos de apoyo propios (nombres, fechas)
        if p in (RICO.relationHasSource, RICO.relationHasTarget, RICO.affectsOrAffected):
            continue  # nodos de relación y actividades de autoría: van en «Quién afirmó cada relación»
        entrantes.append((_valor(g, s, base), _nombre_propiedad(p)))
    # Autoría (criterio nativo 7): las relaciones de esta entidad y las actividades que las produjeron.
    for rel in set(g.subjects(RICO.relationHasSource, nodo)) | set(g.subjects(RICO.relationHasTarget, nodo)):
        for act in g.objects(rel, RICO.isAssociatedWithEvent):
            quienes = [_etiqueta(g, a) for a in g.subjects(RICO.performsOrPerformed, act)]
            autoria.append((_relacion_legible(g, rel, base), escape(_etiqueta(g, act)),
                            escape(", ".join(sorted(quienes)) or "—")))
    autoria.sort(key=lambda f: (f[0], "Propuesta" not in f[1]))  # primero lo que propuso el motor, luego quién lo revisó

    def tabla(cab, cuerpo):
        if not cuerpo:
            return ""
        ths = "".join(f"<th>{c}</th>" for c in cab)
        trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in fila) + "</tr>" for fila in cuerpo)
        return f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"

    datos = escape(str(nodo))
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)} · {escape(institucion)}</title>
<link rel="alternate" type="text/turtle" href="{datos}.ttl"><link rel="alternate" type="application/ld+json" href="{datos}.jsonld">
<style>
:root {{ --fondo:#f4f6fb; --tinta:#1b2433; --suave:#5b6780; --linea:#d9dfeb; --marca:#1f2b47; --acento:#2f5fd0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fondo:#121826; --tinta:#e8edf6; --suave:#9aa8c4; --linea:#2a3550; --marca:#0d1322; --acento:#7ea2f0; }} }}
body {{ margin:0; background:var(--fondo); color:var(--tinta); font:16px/1.55 Inter, system-ui, sans-serif; }}
header {{ background:var(--marca); color:#e8edf6; padding:14px 16px; }} header b {{ font-family:Georgia, serif; }}
main {{ max-width:880px; margin:0 auto; padding:20px 16px 48px; }}
h1 {{ font-family:Georgia, serif; font-size:1.6rem; margin:.2em 0; }} h2 {{ font-size:1.05rem; margin:28px 0 8px; }}
.clase {{ color:var(--suave); }} code {{ font-size:.85em; }}
table {{ width:100%; border-collapse:collapse; font-size:.92rem; }} th, td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--linea); vertical-align:top; overflow-wrap:anywhere; }}
th {{ color:var(--suave); font-weight:600; }} a {{ color:var(--acento); }}
.datos {{ margin-top:28px; color:var(--suave); font-size:.88rem; }}
</style></head><body>
<header><b>RICORA</b> · {escape(institucion)}</header>
<main>
<p class="clase">{escape(" · ".join(clases) or "Entidad")}</p>
<h1>{escape(titulo)}</h1>
<p class="datos"><code>{datos}</code></p>
<h2>Datos</h2>{tabla(("Propiedad", "Valor"), filas) or "<p>Sin datos.</p>"}
{"<h2>Otras entidades que se relacionan con esta</h2>" + tabla(("Entidad", "Relación"), entrantes) if entrantes else ""}
{"<h2>Quién afirmó cada relación</h2>" + tabla(("Relación", "Actividad", "Quién"), autoria) if autoria else ""}
<p class="datos">Datos en RiC-O 1.1: <a href="{datos}.ttl">Turtle</a> · <a href="{datos}.jsonld">JSON-LD</a>.
Solo se muestra lo público.</p>
</main></body></html>"""
