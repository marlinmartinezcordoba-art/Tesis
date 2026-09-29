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

from . import grafo, metricas, rdf, sparql, tipos
from .models import Instantiation


def _entidad_o_404(tipo, pk):
    modelo = tipos.modelo_por_slug(tipo)
    if modelo is None:
        raise Http404(f"Tipo de entidad desconocido: {tipo!r}")
    return get_object_or_404(modelo, pk=pk)


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
    entidad = _entidad_o_404(tipo, pk)
    formato = request.GET.get("formato", "turtle")
    if formato not in _FORMATOS_RDF:
        formato = "turtle"
    base = request.build_absolute_uri("/ric/entidad/")
    g = rdf.grafo_de_entidad(entidad, base)
    return HttpResponse(g.serialize(format=formato), content_type=_FORMATOS_RDF[formato])


@login_required
def exportar_rdf_completo(request):
    formato = request.GET.get("formato", "turtle")
    if formato not in _FORMATOS_RDF:
        formato = "turtle"
    base = request.build_absolute_uri("/ric/entidad/")
    g = rdf.grafo_completo(base)
    return HttpResponse(g.serialize(format=formato), content_type=_FORMATOS_RDF[formato])


@login_required
def grafo_datos(request, tipo, pk):
    entidad = _entidad_o_404(tipo, pk)
    return JsonResponse(grafo.subgrafo_json(entidad))


@login_required
def grafo_html(request, tipo, pk):
    """M8, «Ver en grafo»: la entidad y sus conexiones validadas, solo lectura."""
    entidad = _entidad_o_404(tipo, pk)
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
        resultado = sparql.ejecutar(query, base)
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


@login_required
def servir_archivo(request, pk):
    """El original solo se entrega con sesión iniciada — nunca directo por
    /media/ (que en producción, DEBUG=0, ni siquiera existe)."""
    instanciacion = get_object_or_404(Instantiation, pk=pk)
    nombre = instanciacion.archivo.name.rsplit("/", 1)[-1]
    return FileResponse(instanciacion.archivo.open("rb"), filename=nombre)
