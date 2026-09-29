"""Vistas compartidas por varios módulos: el archivo original protegido
por sesión, el grafo de solo lectura (M8 «Ver en grafo»), la exportación
RDF por entidad y el acceso técnico de M9/M10 (SPARQL, laboratorio de
métricas). Cada módulo del documento de especificación vive en su propio
archivo: vistas_ingesta (M1, M2), vistas_analisis (M3, M4, M6, M7),
vistas_vocabularios (M5), vistas_catalogo (M8, M9), vistas_panel (M10) y
vistas_admin (M11)."""

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from . import acceso_documentos, grafo, metricas, rdf, sparql, tipos
from .models import Instantiation


def _entidad_o_404(tipo, pk):
    modelo = tipos.modelo_por_slug(tipo)
    if modelo is None:
        raise Http404(f"Tipo de entidad desconocido: {tipo!r}")
    return get_object_or_404(modelo, pk=pk)


def _visible_o_404(request, tipo, pk):
    """RF-M8-04: lo que el rol consulta no puede ver responde como si no
    existiera (404), sin confirmar siquiera que existe."""
    entidad = _entidad_o_404(tipo, pk)
    vis = acceso_documentos.Visibilidad(request.user)
    if not vis.puede(entidad):
        raise Http404("No encontrado")
    return entidad, vis


_FORMATOS_RDF = {
    "turtle": "text/turtle; charset=utf-8",
    "xml": "application/rdf+xml; charset=utf-8",
    "n3": "text/n3; charset=utf-8",
    "json-ld": "application/ld+json; charset=utf-8",
}


@login_required
def exportar_rdf(request, tipo, pk):
    """El vecindario RiC validado de una entidad, serializado con las URIs
    de RiC-O 1.1 verificadas. ?formato=turtle|xml|n3|json-ld."""
    entidad, vis = _visible_o_404(request, tipo, pk)
    formato = request.GET.get("formato", "turtle")
    if formato not in _FORMATOS_RDF:
        formato = "turtle"
    base = request.build_absolute_uri("/ric/entidad/")
    g = rdf.grafo_de_entidad(entidad, base, None if vis.todo else vis)
    return HttpResponse(g.serialize(format=formato), content_type=_FORMATOS_RDF[formato])


# --- URI de las entidades (datos enlazados) ---------------------------------
# Cada entidad exportada en RiC-O tiene una dirección …/ric/entidad/<tipo>/<id>.
# Abrirla lleva a su ficha (persona en un navegador) o entrega su RDF
# (programa que pide text/turtle, application/rdf+xml o application/ld+json).

_ACEPTA = (("text/turtle", "turtle"), ("application/rdf+xml", "xml"), ("application/ld+json", "json-ld"),
           ("text/n3", "n3"), ("application/n-triples", "nt"))


def _formato_pedido(request):
    formato = request.GET.get("formato")
    if formato in _FORMATOS_RDF:
        return formato
    acepta = request.headers.get("Accept", "")
    for tipo_mime, formato in _ACEPTA:
        if tipo_mime in acepta:
            return "turtle" if formato == "nt" else formato
    return None  # un navegador: se muestra la ficha


def _rdf(g, formato):
    return HttpResponse(g.serialize(format=formato), content_type=_FORMATOS_RDF[formato])


@login_required
def entidad_uri(request, tipo, pk):
    from django.shortcuts import redirect

    from .models import FormaDocumental

    formato = _formato_pedido(request)
    base = request.build_absolute_uri("/ric/entidad/")
    vis = acceso_documentos.Visibilidad(request.user)
    if tipo == "formadocumental":
        forma = get_object_or_404(FormaDocumental, pk=pk)
        if formato is None:
            return redirect("vocabulario_ficha", "formadocumental", pk)
        return _rdf(rdf.grafo_de_forma_documental(forma, base, None if vis.todo else vis), formato)
    entidad, vis = _visible_o_404(request, tipo, pk)
    entidad = rdf.mas_especifica(entidad)
    if formato is None:
        return redirect("catalogo_ficha", type(entidad).__name__.lower(), entidad.pk)
    return _rdf(rdf.grafo_de_entidad(entidad, base, None if vis.todo else vis), formato)


@login_required
def entidad_nombre_uri(request, tipo, pk, numero):
    """Un nombre alternativo (rico:Name) se resuelve en la entidad que lo tiene."""
    from django.shortcuts import redirect

    return redirect("entidad_uri", tipo, pk)


@login_required
def tipo_uri(request, clase, valor):
    """Un individuo de tipo de RiC-O (rico:ActivityType, rico:Language…)."""
    from django.shortcuts import redirect
    from django.urls import reverse

    vis = acceso_documentos.Visibilidad(request.user)
    g = rdf.grafo_de_tipo(clase, valor, request.build_absolute_uri("/ric/entidad/"), None if vis.todo else vis)
    if g is None:
        raise Http404("No encontrado")
    formato = _formato_pedido(request)
    if formato is None:
        nombre = next((str(o) for s, o in g.subject_objects(rdf.RICO.name) if str(s).endswith(f"/tipo/{clase}/{valor}")), valor)
        return redirect(f"{reverse('catalogo')}?q={nombre}")
    return _rdf(g, formato)


@login_required
def exportar_rdf_completo(request):
    formato = request.GET.get("formato", "turtle")
    if formato not in _FORMATOS_RDF:
        formato = "turtle"
    base = request.build_absolute_uri("/ric/entidad/")
    vis = acceso_documentos.Visibilidad(request.user)
    g = rdf.grafo_completo(base, None if vis.todo else vis)
    return HttpResponse(g.serialize(format=formato), content_type=_FORMATOS_RDF[formato])


@login_required
def grafo_datos(request, tipo, pk):
    entidad, vis = _visible_o_404(request, tipo, pk)
    return JsonResponse(grafo.subgrafo_json(entidad, None if vis.todo else vis))


@login_required
def grafo_html(request, tipo, pk):
    """M8, «Ver en grafo»: la entidad y sus conexiones validadas, solo lectura."""
    entidad, _vis = _visible_o_404(request, tipo, pk)
    return render(request, "ric/grafo.html", {"entidad": entidad, "tipo": tipo})


@login_required
def sparql_html(request):
    return render(request, "ric/sparql.html")


@login_required
@require_POST
def sparql_endpoint(request):
    """Consulta SPARQL de solo lectura (campo `query`, form-encoded) contra el
    grafo RiC ya validado; resultado en formato SPARQL 1.1 JSON."""
    query = request.POST.get("query", "").strip()
    if not query:
        return JsonResponse({"error": "Falta el parámetro 'query'."}, status=400)
    base = request.build_absolute_uri("/ric/entidad/")
    try:
        vis = acceso_documentos.Visibilidad(request.user)
        resultado = sparql.ejecutar(query, base, None if vis.todo else vis)
    except sparql.ErrorSparql as e:
        return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse(resultado)


@login_required
def evaluacion_html(request):
    """Laboratorio de evaluación: M01-M14 calculadas de datos reales, con
    una nota explícita donde falta el dato (nunca un número inventado)."""
    return render(request, "ric/evaluacion.html", {"metricas": metricas.calcular_metricas()})


@login_required
def evaluacion_datos(request):
    return JsonResponse({"metricas": metricas.calcular_metricas()})


