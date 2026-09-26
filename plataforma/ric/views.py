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

from . import grafo, reglas, rdf, tipos
from .models import PropuestaRiC

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
