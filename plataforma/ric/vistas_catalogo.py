"""M8 · Catálogo y consulta (/catalogo) y M9 · Exportación e
interoperabilidad (/exportar), con los flujos "Buscar una entidad o un
documento en el catálogo" y "Exportar un lote de documentos"."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from urllib.parse import urlencode
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import acceso_documentos, clasificacion, valoracion, busqueda, exportacion, flujo, grafo, reglas, roles, tipos
from .models import Exportacion, Instantiation, Record, RecordSet, RelacionRiC

# Filtros de clase del panel izquierdo (RF-M8-01) -> modelos concretos.
CLASES_CATALOGO = [
    ("documento", "Documentos", ["Record"]),
    ("agente", "Agentes", ["Person", "CorporateBody", "Family", "Group", "Position", "Mechanism"]),
    ("actividad", "Actividades y funciones", ["Activity", "Event"]),
    ("fecha", "Fechas", ["Date"]),
    ("lugar", "Lugares", ["Place"]),
    ("mandato", "Mandatos y reglas", ["Mandate", "Rule"]),
]
_CLASE_POR_MODELO = {m: slug for slug, _n, modelos in CLASES_CATALOGO for m in modelos}


def _modelos(nombres):
    from django.apps import apps

    return [apps.get_model("ric", n) for n in nombres]


def _solo_publicados(usuario):
    return acceso_documentos.solo_publicados(usuario)


def documentos_visibles(usuario):
    return acceso_documentos.documentos_visibles(usuario)


def _tarjeta_documento(record):
    matriz = reglas.cargar_matriz()["relaciones"]
    relacionadas = []
    for rel in flujo.relaciones_de(record)[:4]:
        entidad = flujo.otro_lado(rel, record)
        if entidad is not None:
            relacionadas.append({"nombre": matriz.get(rel.relacion_id, {}).get("nombre", rel.relacion_id), "entidad": entidad,
                                 "slug": type(entidad).__name__.lower()})
    estado = flujo.estado_documento(record)
    return {"tipo": "documento", "record": record, "relacionadas": relacionadas, "estado": estado, "etiqueta_estado": flujo.ETIQUETAS[estado]}


def _tarjeta_entidad(entidad, visibilidad):
    """Tarjeta de una entidad con cuántos documentos (que este usuario
    puede ver) la mencionan."""
    ct = ContentType.objects.get_for_model(entidad)
    ct_record = ContentType.objects.get_for_model(Record)
    ids = set(RelacionRiC.objects.filter(
        Q(origen_content_type=ct, origen_object_id=entidad.pk, destino_content_type=ct_record)
        | Q(destino_content_type=ct, destino_object_id=entidad.pk, origen_content_type=ct_record),
        estado__in=flujo.ESTADOS_VALIDADOS,
    ).values_list("origen_object_id", "destino_object_id"))
    docs = {o if d == entidad.pk else d for o, d in ids}
    if not visibilidad.todo:
        docs &= visibilidad.records
    return {"tipo": "entidad", "entidad": entidad, "slug": type(entidad).__name__.lower(),
            "clase": _CLASE_POR_MODELO.get(type(entidad).__name__, "otra"),
            "tipo_nombre": entidad._meta.verbose_name, "documentos": len(docs)}


POR_PAGINA = 24


def _entidades_de_clase(clase, visibilidad):
    nombres = dict((s, n) for s, _x, n in CLASES_CATALOGO).get(clase, [])
    resultado = []
    for modelo in _modelos(nombres):
        resultado.extend(visibilidad.filtrar(tipos.instancias_propias(modelo).order_by("nombre")))
    return resultado


@login_required
def catalogo(request):
    """RF-M8-01: texto libre y filtro de clase, combinados; RF-M8-04: cada
    rol ve solo lo que puede consultar (también en los conteos)."""
    from django.core.paginator import Paginator

    q = request.GET.get("q", "").strip()
    clase = request.GET.get("clase", "").strip()
    if clase and clase not in {s for s, _n, _m in CLASES_CATALOGO}:
        clase = ""
    vis = acceso_documentos.Visibilidad(request.user)
    visibles = documentos_visibles(request.user)

    conteos = {"documento": visibles.count()}
    for slug, _nombre, _nombres in CLASES_CATALOGO[1:]:
        conteos[slug] = len(_entidades_de_clase(slug, vis))

    elementos = []  # (tipo, objeto): se pagina antes de armar las tarjetas
    if q:
        if clase in ("", "documento"):
            por_nombre = visibles.filter(busqueda.filtro_nombre(Record, q))
            por_texto_ids = {p.instanciacion.record_resource_id for p in busqueda.buscar_texto(q, limite=200)}
            vistos = set()
            for record in list(por_nombre.order_by("nombre")) + list(visibles.filter(pk__in=por_texto_ids)):
                if record.pk not in vistos:
                    vistos.add(record.pk)
                    elementos.append(("documento", record))
        if clase != "documento":
            if clase:
                modelos = _modelos(dict((s, n) for s, _x, n in CLASES_CATALOGO).get(clase, []))
            else:
                modelos = [m for m in busqueda.tipos_buscables() if m.__name__ not in ("Record", "RecordSet", "RecordPart", "Instantiation")]
            for entidad in busqueda.buscar_entidades(q, limite=200, modelos=modelos, visibilidad=None if vis.todo else vis):
                elementos.append(("entidad", entidad))
    elif clase in ("", "documento"):
        elementos = [("documento", r) for r in visibles.order_by("-fecha_registro")]
    else:
        elementos = [("entidad", e) for e in _entidades_de_clase(clase, vis)]

    pagina = Paginator(elementos, POR_PAGINA).get_page(request.GET.get("pagina"))
    tarjetas = [_tarjeta_documento(o) if t == "documento" else _tarjeta_entidad(o, vis) for t, o in pagina.object_list]
    parametros = urlencode({k: v for k, v in (("q", q), ("clase", clase)) if v})

    return render(request, "ric/catalogo.html", {
        "q": q, "clase": clase, "tarjetas": tarjetas, "pagina": pagina, "total": len(elementos),
        "parametros": parametros,
        "clases": [(slug, nombre, conteos.get(slug, 0)) for slug, nombre, _n in CLASES_CATALOGO],
        "solo_publicados": _solo_publicados(request.user),
    })


@login_required
def catalogo_sugerencias(request):
    """Sugerencias mientras se escribe (paso 2 del flujo de búsqueda): solo
    nombres que este usuario puede ver (RF-M8-04)."""
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"sugerencias": []})
    vis = acceso_documentos.Visibilidad(request.user)
    nombres = list(documentos_visibles(request.user).filter(busqueda.filtro_nombre(Record, q)).values_list("nombre", flat=True)[:5])
    for entidad in busqueda.buscar_entidades(q, limite=8, visibilidad=None if vis.todo else vis):
        if entidad.nombre not in nombres:
            nombres.append(entidad.nombre)
    return JsonResponse({"sugerencias": nombres[:10]})


@login_required
def catalogo_ficha(request, tipo, pk):
    modelo = tipos.modelo_por_slug(tipo)
    if modelo is None:
        raise Http404("Tipo de entidad desconocido")
    entidad = get_object_or_404(modelo, pk=pk)
    es_documento = isinstance(entidad, Record)
    vis = acceso_documentos.Visibilidad(request.user)
    if not vis.puede(entidad):
        # RF-M8-04: el rol consulta no ve lo que solo aparece en documentos sin publicar o reservados.
        messages.error(request, "Esta ficha no está disponible para consulta.")
        return redirect("catalogo")

    if request.method == "POST" and roles.puede(request.user, roles.ARCHIVISTA):
        # Clasificación de acceso de cada instanciación (RF-M8-04): decisión archivística.
        for inst in entidad.instanciaciones.all() if es_documento else []:
            valor = request.POST.get(f"acceso_{inst.pk}")
            nota = request.POST.get(f"autenticidad_{inst.pk}")
            cambio = False
            if valor in Instantiation.CondicionAcceso.values and valor != inst.condicion_acceso:
                inst.condicion_acceso = valor
                cambio = True
            if nota is not None and nota.strip() != inst.nota_autenticidad:
                inst.nota_autenticidad = nota.strip()
                cambio = True
            if cambio:
                inst.modificado_por = request.user
                inst.save()
        messages.success(request, "Condición de acceso y nota de autenticidad actualizadas.")
        return redirect("catalogo_ficha", tipo=tipo, pk=pk)

    matriz = reglas.cargar_matriz()["relaciones"]
    ct = ContentType.objects.get_for_model(entidad)
    relaciones = []
    for rel in RelacionRiC.objects.filter(
        Q(origen_content_type=ct, origen_object_id=entidad.pk) | Q(destino_content_type=ct, destino_object_id=entidad.pk),
        estado__in=flujo.ESTADOS_VALIDADOS,
    ).select_related("validado_por", "evidencia"):
        soy_origen = rel.origen_content_type_id == ct.pk and rel.origen_object_id == entidad.pk
        otro = rel.destino if soy_origen else rel.origen
        if otro is None:
            continue
        if not vis.puede(otro):
            continue
        relaciones.append({
            "relacion": rel, "nombre": matriz.get(rel.relacion_id, {}).get("nombre", rel.relacion_id),
            "categoria": grafo.CATEGORIAS[grafo.categoria_relacion(rel.relacion_id)][0],
            "otro": otro, "otro_slug": type(otro).__name__.lower(), "otro_es_documento": isinstance(otro, Record),
            "direccion": "→" if soy_origen else "←",
        })
    documentos = [r["otro"] for r in relaciones if r["otro_es_documento"]]

    contexto = {
        "entidad": entidad, "tipo": tipo, "es_documento": es_documento,
        "tipo_nombre": modelo._meta.verbose_name,
        "relaciones": relaciones, "documentos": documentos,
        "puede_editar": roles.puede(request.user, roles.ARCHIVISTA),
        "puede_revisar": roles.puede(request.user, roles.ARCHIVISTA, roles.REVISOR),
        "condiciones": Instantiation.CondicionAcceso.choices,
    }
    if es_documento:
        estado = flujo.estado_documento(entidad)
        expediente = clasificacion.expediente_de(entidad)
        contexto.update({
            "record": entidad, "estado": estado, "etiqueta_estado": flujo.ETIQUETAS[estado], "paso_actual": 6,
            "instanciaciones": entidad.instanciaciones.all(),
            "series_trd": flujo.series_trd_de(entidad),
            "expediente": expediente,
            "ruta": expediente.ruta() if expediente is not None else [],
            "valoracion": valoracion.resumen(expediente) if expediente is not None and expediente.es_expediente else None,
        })
    if isinstance(entidad, RecordSet):
        contexto.update({
            "es_conjunto": True, "ruta": entidad.ruta(),
            "subconjuntos": vis.filtrar(entidad.hijos.order_by("nombre")),
            "documentos_del_conjunto": documentos_visibles(request.user).filter(record_set=entidad).order_by("nombre"),
            "valoracion": valoracion.resumen(entidad) if entidad.es_expediente else None,
            "mandato_conjunto": entidad.mandato(),
        })
    return render(request, "ric/catalogo_ficha.html", contexto)


# ---------------------------------------------------------------------------
# M9 · Exportación e interoperabilidad
# ---------------------------------------------------------------------------

@login_required
def exportar(request):
    visibles = documentos_visibles(request.user)
    seleccion_ids = [v for v in request.GET.getlist("doc") if v.isdigit()]
    if request.method == "POST":
        ids = [v for v in request.POST.getlist("doc") if v.isdigit()]
        formato = request.POST.get("formato", "")
        records = visibles.filter(pk__in=ids)
        if not records.exists():
            messages.error(request, "Seleccione al menos un documento para exportar.")
            return redirect("exportar")
        if formato not in Exportacion.Formato.values:
            messages.error(request, "Elija un formato de exportación.")
            return redirect("exportar")
        base = request.build_absolute_uri("/ric/entidad/")
        exp = exportacion.generar_exportacion(records, formato, request.user, base)
        messages.success(request, f"Exportación generada: {exp.total_registros} registro(s) en {exp.get_formato_display()}.")
        return redirect(f"/exportar/?listo={exp.pk}")

    seleccionados = visibles.filter(pk__in=seleccion_ids) if seleccion_ids else Record.objects.none()
    historial = Exportacion.objects.select_related("usuario")
    if _solo_publicados(request.user):
        historial = historial.filter(usuario=request.user)
    listo = None
    if request.GET.get("listo", "").isdigit():
        listo = historial.filter(pk=request.GET["listo"]).first()
    return render(request, "ric/exportar.html", {
        "seleccionados": seleccionados,
        "disponibles": visibles.order_by("nombre")[:300],
        "formatos": Exportacion.Formato.choices,
        "historial": historial[:50],
        "listo": listo,
    })


@login_required
def exportar_descargar(request, pk):
    exp = get_object_or_404(Exportacion, pk=pk)
    if _solo_publicados(request.user) and exp.usuario_id != request.user.pk:
        raise Http404
    nombre = exp.archivo.name.rsplit("/", 1)[-1]
    return FileResponse(exp.archivo.open("rb"), filename=nombre, content_type=exportacion.content_type_de(exp))
