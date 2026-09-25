from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from . import exportacion
from .models import Documento, EventoPreservacion, registrar_evento


@login_required
def exportar_dublin_core(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    contenido = exportacion.dublin_core_xml(documento)
    registrar_evento(
        documento, EventoPreservacion.Tipo.EXPORTACION, agente=request.user,
        detalle={"esquema": "Dublin Core (oai_dc)"},
    )
    return HttpResponse(contenido, content_type="application/xml; charset=utf-8")


@login_required
def exportar_premis(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    contenido = exportacion.premis_xml(documento)
    registrar_evento(
        documento, EventoPreservacion.Tipo.EXPORTACION, agente=request.user,
        detalle={"esquema": "PREMIS 3"},
    )
    return HttpResponse(contenido, content_type="application/xml; charset=utf-8")
