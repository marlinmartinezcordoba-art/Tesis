"""Bandeja de validación (T040): la vista que muestra a la vez documento +
evidencia + propuesta de IA + entidad/relación RiC + decisión del
archivista, tal como lo exige el Entregable 3 (sección 8: "la interfaz debe
mostrar simultáneamente..."). Antes de esto, la única forma de validar una
PropuestaRiC era el admin de Django, que no reúne las cinco cosas a la vez.
"""

import datetime
from functools import wraps
from pathlib import Path

from django.apps import apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import auditoria, busqueda, desambiguacion, grafo, metricas, reglas, rdf, sparql, tipos
from .models import Instantiation, PropuestaRiC, Record, RelacionRiC

# Slug de URL (nombre de modelo en minúsculas) -> nombre real del modelo,
# para las vistas que reciben el tipo de entidad como texto en la URL.
_MODELOS_POR_SLUG = {nombre.lower(): nombre for nombre in tipos.RIC_ID_A_MODELO_NOMBRE.values()}

# F04 (Entidades RiC): IDs de entidad que de verdad se pueden navegar aquí
# — el mismo inventario que ya registra el admin, uno por uno. Ver
# ric.tipos.TIPOS_CONCRETOS / instancias_propias (compartido con ric.rdf,
# que necesita el mismo recorrido "por tipo, sin duplicar hijos MTI" para
# la exportación RDF completa).
_TIPOS_NAVEGABLES = tipos.TIPOS_CONCRETOS
_instancias_propias = tipos.instancias_propias


def archivista_requerido(vista):
    """F16: dos perfiles — archivista (is_staff, el mismo que ya usa el
    panel técnico de Django) puede ingerir y validar; cualquier otra
    sesión iniciada es de "solo consulta": puede buscar, ver el grafo
    validado y exportarlo, pero no subir documentos ni decidir propuestas.
    Los usuarios de consulta se crean igual que cualquier otro, desde
    Panel técnico → Usuarios, sin marcar la casilla "Es staff"."""

    @wraps(vista)
    @login_required
    def envoltura(request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, "Tu perfil es de solo consulta: no puede ingerir documentos ni validar propuestas.")
            return redirect("ric_inicio")
        return vista(request, *args, **kwargs)

    return envoltura

# F06: formatos sobre los que tiene sentido dibujar el recuadro de posición
# (izquierda/arriba/ancho/alto son píxeles de la imagen tal cual se subió).
# Un PDF necesitaría renderizar la página aparte; eso no está construido.
_EXT_IMAGEN_CON_RESALTADO = {".jpg", ".jpeg", ".png"}


def _entidad_o_404(tipo, pk):
    nombre_modelo = _MODELOS_POR_SLUG.get(tipo)
    if nombre_modelo is None:
        raise Http404(f"Tipo de entidad desconocido: {tipo!r}")
    modelo = apps.get_model("ric", nombre_modelo)
    return get_object_or_404(modelo, pk=pk)


def _fila(propuesta):
    """Arma todo lo que la plantilla necesita para una propuesta: la info
    de la relación verificada en RiC-CM/RiC-O, las entidades ya existentes
    del mismo tipo (para poder "vincular" en vez de crear un duplicado),
    cuáles de esas se parecen al nombre propuesto (F10: la IA sugiere el
    posible duplicado, nunca decide sola), y si la evidencia (F06) se
    puede mostrar resaltada sobre la imagen real del documento — no solo
    como texto citado."""
    try:
        info = reglas.info_relacion(propuesta.relacion_id)
    except reglas.RelacionInvalida:
        info = None
    modelo = tipos.ric_id_a_modelo(propuesta.entidad_tipo)

    evidencia = propuesta.evidencia
    resaltado_visual = False
    if evidencia and evidencia.posicion and evidencia.instanciacion and evidencia.instanciacion.archivo:
        extension = Path(evidencia.instanciacion.archivo.name).suffix.lower()
        resaltado_visual = extension in _EXT_IMAGEN_CON_RESALTADO

    posibles_duplicados = (
        desambiguacion.candidatos_similares(modelo, propuesta.entidad_nombre) if modelo else []
    )

    return {
        "propuesta": propuesta,
        "info_relacion": info,
        "modelo_nombre": modelo.__name__ if modelo else propuesta.entidad_tipo,
        "candidatas": modelo.objects.order_by("nombre") if modelo else [],
        "posibles_duplicados": posibles_duplicados,
        "duplicado_pks": {d.pk for d in posibles_duplicados},
        "resaltado_visual": resaltado_visual,
    }


@archivista_requerido
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


@archivista_requerido
def decidir_propuesta(request, pk):
    if request.method != "POST":
        return redirect("ric_bandeja")

    propuesta = get_object_or_404(PropuestaRiC, pk=pk)
    accion = request.POST.get("accion")
    motivo = request.POST.get("motivo", "").strip()
    nombre_corregido = request.POST.get("entidad_nombre_final", "").strip()

    try:
        if accion == "aceptar":
            propuesta.validar(
                request.user, aceptar=True, motivo=motivo,
                entidad_nombre_final=nombre_corregido or None,
            )
            if nombre_corregido and nombre_corregido != propuesta.entidad_nombre:
                messages.success(
                    request,
                    f"'{propuesta.relacion_id}' aceptada y agregada al grafo RiC como \"{nombre_corregido}\" "
                    f"(corregido de \"{propuesta.entidad_nombre}\").",
                )
            else:
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


_COLORES_DISTRIBUCION = ["#c08a3e", "#2f7d4f", "#a9660a", "#7046d9", "#c0392b", "#1f6f8b"]


def _distribucion_entidades():
    """Cuántas entidades de cada gran tipo RiC-CM existen ya guardadas —
    datos reales, para el donut de "tipos de entidad" del inicio.

    Cuenta cada tabla concreta de más alto nivel (Agent, no sus subtipos
    por separado): con herencia multitabla, `Group.objects.count()` YA
    incluye cada `Family`/`CorporateBody` (tienen fila también en la tabla
    de Group), así que sumar Person+Group+Family+CorporateBody+... contaría
    cada agente varias veces. `Agent.objects.count()` es exacto: cada
    agente, sin importar su subtipo, tiene exactamente una fila ahí."""
    from .models import Activity, Agent, Date, Place

    filas = [
        {"tipo": "Record", "total": Record.objects.count()},
        {"tipo": "Agent", "total": Agent.objects.count()},
        {"tipo": "Activity", "total": Activity.objects.count()},
        {"tipo": "Instantiation", "total": Instantiation.objects.count()},
        {"tipo": "Date", "total": Date.objects.count()},
        {"tipo": "Place", "total": Place.objects.count()},
    ]
    for fila, color in zip(filas, _COLORES_DISTRIBUCION):
        fila["color"] = color
    return filas


def _gradiente_conico(distribucion):
    """'color1 0% 40%, color2 40% 70%, ...' para dibujar el donut con
    conic-gradient — vacío (gris parejo) si todavía no hay ninguna entidad."""
    total = sum(f["total"] for f in distribucion)
    if not total:
        return "#e6e3dc 0% 100%"
    partes = []
    acumulado = 0
    for f in distribucion:
        if not f["total"]:
            continue
        inicio = acumulado / total * 100
        acumulado += f["total"]
        partes.append(f"{f['color']} {inicio:.2f}% {acumulado / total * 100:.2f}%")
    return ", ".join(partes)


def _actividad_ultimos_dias(dias=14):
    """Documentos ingeridos por día en los últimos `dias` días — datos
    reales de Instantiation.fecha_registro, nunca simulados. Devuelve una
    lista de {"etiqueta", "total", "porcentaje"} lista para dibujar barras."""
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    from django.utils import timezone

    hoy = timezone.localdate()
    desde = hoy - datetime.timedelta(days=dias - 1)
    conteos = dict(
        Instantiation.objects.filter(fecha_registro__date__gte=desde)
        .annotate(dia=TruncDate("fecha_registro"))
        .values("dia")
        .annotate(total=Count("pk"))
        .values_list("dia", "total")
    )
    serie = []
    for i in range(dias):
        dia = desde + datetime.timedelta(days=i)
        serie.append({"etiqueta": dia.strftime("%d/%m"), "total": conteos.get(dia, 0)})
    maximo = max((d["total"] for d in serie), default=0) or 1
    for d in serie:
        d["porcentaje"] = round(d["total"] / maximo * 100)
    return serie


@login_required
def inicio(request):
    """Panel de inicio para uso diario: un punto de entrada en español
    sencillo, con las tareas más comunes a la vista — en vez de dejar al
    archivista en el admin de Django, pensado para quien administra el
    sistema, no para el uso diario. Todo lo que muestra son datos reales
    del sistema, nunca simulados ni de ejemplo."""
    from .models import EventoRiC

    propuestas_pendientes = PropuestaRiC.objects.filter(estado=PropuestaRiC.Estado.PENDIENTE)
    muestras_pendientes = auditoria.MuestraRiC.objects.filter(
        resultado=auditoria.MuestraRiC.Resultado.PENDIENTE
    ).count()
    documentos_sin_texto = Instantiation.objects.filter(paginas__isnull=True).distinct().count()
    distribucion = _distribucion_entidades()

    contexto = {
        "pendientes": propuestas_pendientes.count(),
        "total_registros": Record.objects.count(),
        "relaciones_validadas": RelacionRiC.objects.filter(
            estado__in=(RelacionRiC.Estado.ACEPTADA, RelacionRiC.Estado.MODIFICADA)
        ).count(),
        "muestras_pendientes": muestras_pendientes,
        "atencion": [_fila(p) for p in propuestas_pendientes.order_by("-confianza")[:5]],
    }

    if request.user.is_staff:
        contexto.update({
            "documentos_sin_texto": documentos_sin_texto,
            "distribucion": distribucion,
            "gradiente_distribucion": _gradiente_conico(distribucion),
            "total_entidades": sum(f["total"] for f in distribucion),
            "actividad_dias": _actividad_ultimos_dias(),
            "eventos_recientes": (
                EventoRiC.objects.select_related("instanciacion").order_by("-id")[:8]
            ),
            "documentos_recientes": (
                Instantiation.objects.select_related("record_resource")
                .order_by("-fecha_registro")[:8]
            ),
        })

    return render(request, "ric/inicio.html", contexto)


@login_required
def registros_html(request):
    """Lista de Record ya cargados, con acceso directo a su grafo y su RDF."""
    registros = Record.objects.select_related("record_set").order_by("nombre")
    return render(request, "ric/registros.html", {"registros": registros})


@login_required
def entidades_html(request):
    """Todas las entidades RiC ya guardadas, sin importar su tipo — hasta
    ahora solo se podían ver una por una en el admin de Django, o los
    Record en "Registros". Sin filtro, muestra las más recientes de cada
    tipo (16 consultas pequeñas, acotadas, combinadas en memoria); con
    filtro de tipo, la lista completa de ese tipo."""
    filtro = request.GET.get("tipo", "").strip()
    q = request.GET.get("q", "").strip()

    catalogo = []
    for rid in _TIPOS_NAVEGABLES:
        nombre_modelo = tipos.RIC_ID_A_MODELO_NOMBRE[rid]
        modelo = apps.get_model("ric", nombre_modelo)
        catalogo.append({
            "ric_id": rid,
            "slug": nombre_modelo.lower(),
            "nombre": modelo._meta.verbose_name.capitalize(),
            "total": _instancias_propias(modelo).count(),
        })

    filas = []
    if filtro and filtro in _MODELOS_POR_SLUG:
        modelo = apps.get_model("ric", _MODELOS_POR_SLUG[filtro])
        qs = _instancias_propias(modelo).order_by("nombre")
        if q:
            qs = qs.filter(nombre__icontains=q)
        for e in qs.values("pk", "nombre", "identificador", "fecha_registro")[:200]:
            filas.append({**e, "tipo": modelo._meta.verbose_name, "slug": filtro})
    else:
        for rid in _TIPOS_NAVEGABLES:
            nombre_modelo = tipos.RIC_ID_A_MODELO_NOMBRE[rid]
            modelo = apps.get_model("ric", nombre_modelo)
            qs = _instancias_propias(modelo).order_by("-fecha_registro")
            if q:
                qs = qs.filter(nombre__icontains=q)
            for e in qs.values("pk", "nombre", "identificador", "fecha_registro")[:30]:
                filas.append({**e, "tipo": modelo._meta.verbose_name, "slug": nombre_modelo.lower()})
        filas.sort(key=lambda f: f["fecha_registro"], reverse=True)
        filas = filas[:50]

    return render(request, "ric/entidades.html", {
        "catalogo": catalogo,
        "filas": filas,
        "filtro": filtro,
        "q": q,
        "total_entidades": sum(c["total"] for c in catalogo),
    })


@archivista_requerido
def subir_documento(request):
    """F01: pantalla simple para subir uno o varios documentos, en lenguaje
    llano, sin pasar por el panel técnico de Django. El hash (F01), el OCR
    (F02), la estructura (F03) y la propuesta de segmentación (F04) se
    calculan solos — ver ric.ingesta.ingerir."""
    errores = []
    resultados = []
    record = None

    if request.method == "POST":
        from .ingesta import ingerir

        record_id = request.POST.get("record_id", "").strip()
        nombre_nuevo = request.POST.get("nombre_nuevo", "").strip()
        archivos = request.FILES.getlist("archivos")

        if not record_id and not nombre_nuevo:
            errores.append("Indique a qué expediente pertenece el documento, o escriba el nombre de uno nuevo.")
        if not archivos:
            errores.append("Seleccione al menos un archivo para subir.")

        if not errores:
            record = get_object_or_404(Record, pk=record_id) if record_id else Record.objects.create(nombre=nombre_nuevo)
            for archivo in archivos:
                instanciacion = Instantiation.objects.create(
                    nombre=archivo.name, record_resource=record, archivo=archivo,
                )
                detalle = ingerir(instanciacion, agente=request.user)
                resultados.append({"instanciacion": instanciacion, "detalle": detalle})

    return render(request, "ric/subir.html", {
        "registros": Record.objects.order_by("nombre"),
        "errores": errores,
        "resultados": resultados,
        "record": record,
    })


@login_required
def servir_archivo(request, pk):
    """F16: el original solo se entrega a través de esta vista, que exige
    sesión iniciada — nunca directo por /media/. En producción (DEBUG=0)
    Django ni siquiera expone /media/ (es un ayudante de solo-desarrollo),
    así que antes de esta vista el archivo no tenía ninguna URL real en el
    servidor desplegado; ahora además queda protegido por contraseña."""
    instanciacion = get_object_or_404(Instantiation, pk=pk)
    nombre = instanciacion.archivo.name.rsplit("/", 1)[-1]
    return FileResponse(instanciacion.archivo.open("rb"), filename=nombre)


@archivista_requerido
def duplicados_html(request):
    """F10 (Desambiguación), el lado "sola, sin que nadie proponga nada
    nuevo": recorre las entidades que YA existen (no solo las propuestas
    pendientes, que ya se avisan en la bandeja) y agrupa los pares que se
    parecen. Aquí solo se sugiere — fusionar de verdad se hace desde el
    panel técnico (F08, ric.fusion), con el enlace directo a cada tipo."""
    from . import fusion

    grupos = []
    for modelo in fusion.modelos_fusionables():
        pares = desambiguacion.pares_similares(modelo)
        if pares:
            grupos.append({
                "modelo_nombre": modelo.__name__,
                "nombre_verbose": modelo._meta.verbose_name_plural,
                "pares": pares,
                "url_admin": reverse(f"admin:ric_{modelo.__name__.lower()}_changelist"),
            })
    total = sum(len(g["pares"]) for g in grupos)
    return render(request, "ric/duplicados.html", {"grupos": grupos, "total": total})
