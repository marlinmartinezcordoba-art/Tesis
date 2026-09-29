"""Valoración y disposición (/valoracion): expedientes con la retención
heredada de su serie de la TRD, fases, listas de transferencia y
disposición final, e inventario documental (FUID) en CSV."""

import datetime

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import roles, valoracion
from .models import EventoRiC, RecordSet, registrar_evento


def _fecha(valor):
    try:
        return datetime.date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def valoracion_lista(request):
    q = request.GET.get("q", "").strip()
    fase = request.GET.get("fase", "").strip()
    filas = valoracion.resumenes()
    if q:
        filas = [r for r in filas if q.lower() in r["expediente"].nombre.lower() or (r["serie"] and q.lower() in r["serie"].nombre.lower()) or (r["serie"] and q.lower() in r["serie"].identificador.lower())]
    if fase:
        filas = [r for r in filas if r["fase"] == fase]
    conteo = {}
    for r in valoracion.resumenes():
        conteo[r["fase"]] = conteo.get(r["fase"], 0) + 1
    return render(request, "ric/valoracion.html", {
        "filas": filas, "q": q, "fase": fase,
        "fases": [(clave, valoracion.ETIQUETAS[clave], conteo.get(clave, 0)) for clave in (valoracion.ABIERTO, valoracion.GESTION, valoracion.CENTRAL, valoracion.DISPOSICION, valoracion.SIN_TRD)],
        "puede_editar": roles.puede(request.user, roles.ARCHIVISTA),
        "dias_aviso": valoracion.DIAS_AVISO,
    })


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def valoracion_expediente(request, pk):
    """Fechas de apertura y cierre del expediente: desde el cierre corre la retención."""
    expediente = get_object_or_404(RecordSet, pk=pk, tipo_conjunto=RecordSet.Tipo.EXPEDIENTE)
    apertura, cierre = _fecha(request.POST.get("fecha_apertura")), _fecha(request.POST.get("fecha_cierre"))
    if cierre and apertura and cierre < apertura:
        messages.error(request, "La fecha de cierre no puede ser anterior a la de apertura.")
        return redirect("valoracion")
    expediente.fecha_apertura, expediente.fecha_cierre = apertura, cierre
    expediente.modificado_por = request.user
    expediente.save()
    registrar_evento(None, EventoRiC.Tipo.VALIDACION, agente=request.user, detalle={
        "accion": "fechas_expediente", "expediente_id": expediente.pk, "expediente": expediente.nombre,
        "fecha_apertura": apertura.isoformat() if apertura else None, "fecha_cierre": cierre.isoformat() if cierre else None,
    })
    r = valoracion.resumen(expediente)
    messages.success(request, f"«{expediente.nombre}»: {r['etiqueta'].lower()}" + (f" · fin de gestión {r['fin_gestion']:%d/%m/%Y} · fin de central {r['fin_central']:%d/%m/%Y}." if r["fin_central"] else "."))
    return redirect("valoracion")


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def valoracion_transferencias(request):
    listas = valoracion.transferencias()
    return render(request, "ric/valoracion_transferencias.html", {**listas, "dias_aviso": valoracion.DIAS_AVISO})


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def valoracion_fuid(request):
    contenido = valoracion.fuid_csv()
    registrar_evento(None, EventoRiC.Tipo.EXPORTACION, agente=request.user, detalle={"formato": "fuid_csv", "expedientes": contenido.count("\n") - 1})
    respuesta = HttpResponse("﻿" + contenido, content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="FUID_{datetime.date.today():%Y%m%d}.csv"'
    return respuesta
