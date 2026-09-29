"""Guía de uso de RICORA: qué hace cada pantalla y cómo se usa."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from . import ayuda


@login_required
def guia(request):
    return render(request, "ric/ayuda.html", {"procesos": ayuda.por_proceso()})
