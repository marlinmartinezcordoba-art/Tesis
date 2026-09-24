from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from acervo.models import Documento

from .models import Proceso
from .verificacion import CUMPLE, NO_CUMPLE, evaluar_documento


@login_required
def informe(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    resultados = evaluar_documento(documento)
    por_proceso = defaultdict(list)
    for r in resultados:
        por_proceso[r.criterio.get_proceso_display()].append(r)
    orden = [etiqueta for _, etiqueta in Proceso.choices if etiqueta in por_proceso]
    return render(request, "lineamientos/informe.html", {
        "documento": documento,
        "secciones": [(p, por_proceso[p]) for p in orden],
        "cumple": sum(r.estado == CUMPLE for r in resultados),
        "no_cumple": sum(r.estado == NO_CUMPLE for r in resultados),
        "total": len(resultados),
    })
