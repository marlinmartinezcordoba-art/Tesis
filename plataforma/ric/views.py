"""Bandeja de validación (T040): la vista que muestra a la vez documento +
evidencia + propuesta de IA + entidad/relación RiC + decisión del
archivista, tal como lo exige el Entregable 3 (sección 8: "la interfaz debe
mostrar simultáneamente..."). Antes de esto, la única forma de validar una
PropuestaRiC era el admin de Django, que no reúne las cinco cosas a la vez.
"""

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import busqueda, grafo, metricas, reglas, rdf, sparql, tipos
from .models import PropuestaRiC, Record

# Slug de URL (nombre de modelo en minúsculas) -> nombre real del modelo,
# para las vistas que reciben el tipo de entidad como texto en la URL.
_MODELOS_POR_SLUG = {nombre.lower(): nombre for nombre in tipos.RIC_ID_A_MODELO_NOMBRE.values()}


def _entidad_o_404(tipo, pk):
    nombre_modelo = _MODELOS_POR_SLUG.get(tipo)
    if nombre_modelo is None:
        raise Http404(f"Tipo de entidad desconocido: {tipo!r}")
    modelo = apps.get_model("ric", nombre_modelo)
    return get_object_or_404(modelo, pk=pk)


def _fila(propuesta):
    """Arma todo lo que la plantilla necesita para una propuesta: la info
    de la relación verificada en RiC-CM/RiC-O, y las entidades ya existentes
    del mismo tipo, para poder "vincular" en vez de crear un duplicado."""
    try:
        info = reglas.info_relacion(propuesta.relacion_id)
    except reglas.RelacionInvalida:
        info = None
    modelo = tipos.ric_id_a_modelo(propuesta.entidad_tipo)
    return {
        "propuesta": propuesta,
        "info_relacion": info,
        "modelo_nombre": modelo.__name__ if modelo else propuesta.entidad_tipo,
        "candidatas": modelo.objects.order_by("nombre") if modelo else [],
    }


@login_required
def bandeja_validacion(request):
    pendientes = (
        PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE)
        .select_related("evidencia", "evidencia__instanciacion", "origen_content_type")
        .order_by("-confianza", "-fecha_creacion")
    )
    return render(request, "ric/bandeja.html", {
        "filas": [_fila(p) for p in pendientes],
        "total": len(pendientes),
    })


@login_required
def decidir_propuesta(request, pk):
    if request.method != "POST":
        return redirect("ric_bandeja")

    propuesta = get_object_or_404(PropuestaRiC, pk=pk)
    accion = request.POST.get("accion")
    motivo = request.POST.get("motivo", "").strip()

    try:
        if accion == "aceptar":
            propuesta.validar(request.user, aceptar=True, motivo=motivo)
            messages.success(request, f"'{propuesta.relacion_id}' aceptada y agregada al grafo RiC.")
        elif accion == "vincular":
            modelo = tipos.ric_id_a_modelo(propuesta.entidad_tipo)
            entidad_existente = get_object_or_404(modelo, pk=request.POST.get("entidad_existente"))
            propuesta.validar(request.user, aceptar=True, entidad_existente=entidad_existente, motivo=motivo)
            messages.success(request, f"Vinculada a '{entidad_existente}' en vez de crear una entidad nueva.")
        elif accion == "rechazar":
            if not motivo:
                messages.error(request, "Indique el motivo del rechazo antes de rechazar la propuesta.")
                return redirect("ric_bandeja")
            propuesta.validar(request.user, aceptar=False, motivo=motivo)
            messages.info(request, f"'{propuesta.relacion_id}' rechazada.")
        else:
            messages.error(request, "Acción no reconocida.")
    except (ValueError, PermissionError) as e:
        messages.error(request, str(e))

    return redirect("ric_bandeja")


_FORMATOS_RDF = {
    "turtle": "text/turtle; charset=utf-8",
    "xml": "application/rdf+xml; charset=utf-8",
    "n3": "text/n3; charset=utf-8",
    "json-ld": "application/ld+json; charset=utf-8",
}


@login_required
def exportar_rdf(request, tipo, pk):
    """T050: el vecindario RiC validado de una entidad, serializado con las
    URIs de RiC-O 1.1 verificadas. ?formato=turtle|xml|n3|json-ld."""
    entidad = _entidad_o_404(tipo, pk)
    formato = request.GET.get("formato", "turtle")
    if formato not in _FORMATOS_RDF:
        formato = "turtle"
    base = request.build_absolute_uri("/ric/entidad/")
    g = rdf.grafo_de_entidad(entidad, base)
    return HttpResponse(g.serialize(format=formato), content_type=_FORMATOS_RDF[formato])


@login_required
def exportar_rdf_completo(request):
    """T050: todo el grafo RiC validado en un solo archivo (base de la
    proyección que luego carga el endpoint SPARQL, T051)."""
    formato = request.GET.get("formato", "turtle")
    if formato not in _FORMATOS_RDF:
        formato = "turtle"
    base = request.build_absolute_uri("/ric/entidad/")
    g = rdf.grafo_completo(base)
    return HttpResponse(g.serialize(format=formato), content_type=_FORMATOS_RDF[formato])


@login_required
def grafo_datos(request, tipo, pk):
    """T052: el subgrafo de `entidad` en el formato de nodos/aristas de Cytoscape.js."""
    entidad = _entidad_o_404(tipo, pk)
    return JsonResponse(grafo.subgrafo_json(entidad))


@login_required
def grafo_html(request, tipo, pk):
    entidad = _entidad_o_404(tipo, pk)
    return render(request, "ric/grafo.html", {"entidad": entidad, "tipo": tipo})


@login_required
def sparql_html(request):
    """T051: una página simple con un cuadro de consulta que llama al mismo
    endpoint POST /ric/sparql/ y muestra los resultados."""
    return render(request, "ric/sparql.html")


@login_required
@require_POST
def sparql_endpoint(request):
    """T051: ejecuta la consulta SPARQL de solo lectura recibida en el
    campo `query` (form-encoded) contra el grafo RiC ya validado, y
    devuelve el resultado en el formato estándar SPARQL 1.1 JSON."""
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
def busqueda_html(request):
    """T053 / F14: búsqueda contextual — texto completo ya extraído +
    nombre de entidades, cada una enlazada a su grafo de relaciones."""
    q = request.GET.get("q", "").strip()
    paginas, filas_entidades = [], []
    if q:
        paginas = busqueda.buscar_texto(q)
        filas_entidades = [
            {"entidad": e, "tipo_slug": type(e).__name__.lower(), "tipo_nombre": type(e).__name__}
            for e in busqueda.buscar_entidades(q)
        ]
    return render(request, "ric/busqueda.html", {"q": q, "paginas": paginas, "entidades": filas_entidades})


@login_required
def evaluacion_html(request):
    """T070: laboratorio de evaluación — M01-M14 calculadas de datos
    reales, con una nota explícita donde todavía falta el dato que una
    métrica necesita (nunca un número inventado)."""
    return render(request, "ric/evaluacion.html", {"metricas": metricas.calcular_metricas()})


@login_required
def evaluacion_datos(request):
    """T070: lo mismo que evaluacion_html, como JSON (GET /evaluation)."""
    return JsonResponse({"metricas": metricas.calcular_metricas()})


@login_required
def inicio(request):
    """Panel de inicio para uso diario: un punto de entrada en español
    sencillo, con las tareas más comunes como tarjetas — en vez de dejar
    al archivista en el admin de Django, pensado para quien administra el
    sistema, no para el uso diario."""
    pendientes = PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE).count()
    return render(request, "ric/inicio.html", {"pendientes": pendientes})


@login_required
def registros_html(request):
    """Lista de Record ya cargados, con acceso directo a su grafo y su RDF."""
    registros = Record.objects.select_related("record_set").order_by("nombre")
    return render(request, "ric/registros.html", {"registros": registros})
