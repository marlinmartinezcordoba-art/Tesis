"""Inicio de RICORA: qué es la plataforma, el recorrido de un documento por
el proceso archivístico y lo que cada persona tiene por hacer hoy, según
su rol. Todo con cifras vigentes; cada tarea enlaza a su pantalla."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from . import acceso_documentos, flujo, indicadores, roles, valoracion
from .models import Agent, ConfiguracionSistema, Instantiation, PropuestaRiC, Record, RelacionRiC


@login_required
def inicio(request):
    usuario = request.user
    trabaja = roles.puede(usuario, roles.ARCHIVISTA, roles.REVISOR)
    ingesta = roles.puede(usuario, roles.ARCHIVISTA)
    visibles = acceso_documentos.documentos_visibles(usuario)

    cifras = {
        "documentos": visibles.count(),
        "publicados": visibles.filter(publicado=True).count(),
        "agentes": Agent.objects.count() if trabaja else None,
        "relaciones": RelacionRiC.objects.filter(estado__in=flujo.ESTADOS_VALIDADOS).count() if trabaja else None,
    }

    tareas = []
    if trabaja:
        limite = ConfiguracionSistema.actual().dias_limite_revision
        atrasados = len(indicadores.atrasados(limite))
        sin_enviar = Instantiation.objects.filter(estado_proceso=Instantiation.EstadoProceso.SIN_ENVIAR).count()
        por_decidir = PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE).values("origen_object_id").distinct().count()
        por_revisar = sum(1 for pk in indicadores.esperando_revision())
        vencidos = valoracion.conteo_vencidos()
        if ingesta:
            tareas.append({"n": sin_enviar, "texto": "archivo(s) cargados sin enviar al OCR", "url": "preproceso", "accion": "Preprocesar"})
            tareas.append({"n": por_decidir, "texto": "documento(s) con propuestas de la IA por decidir", "url": "analisis_lista", "accion": "Decidir"})
        tareas.append({"n": por_revisar, "texto": "documento(s) esperando revisión", "url": "revision_lista", "filtro": "pendientes", "accion": "Revisar"})
        tareas.append({"n": atrasados, "texto": f"con la revisión atrasada (más de {limite} días)", "url": "revision_lista", "filtro": "atrasados", "accion": "Ver", "alerta": True})
        tareas.append({"n": vencidos, "texto": "expediente(s) con retención vencida o por vencer", "url": "valoracion_transferencias", "accion": "Ver", "alerta": True})

    return render(request, "ric/inicio.html", {
        "cifras": cifras, "tareas": tareas, "trabaja": trabaja, "ingesta": ingesta,
        "pendientes_total": sum(t["n"] for t in tareas),
        "rol": roles.ETIQUETAS[roles.rol_de(usuario)],
    })
