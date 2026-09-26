"""Bandeja de validación (T040): la vista que muestra a la vez documento +
evidencia + propuesta de IA + entidad/relación RiC + decisión del
archivista, tal como lo exige el Entregable 3 (sección 8: "la interfaz debe
mostrar simultáneamente..."). Antes de esto, la única forma de validar una
PropuestaRiC era el admin de Django, que no reúne las cinco cosas a la vez.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from . import reglas, tipos
from .models import PropuestaRiC


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
