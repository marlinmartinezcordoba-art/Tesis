"""M5 · Vocabularios y autoridades (/vocabularios): el catálogo único de
agentes, lugares, actividades/funciones, mandatos, fechas y formas
documentales ya validados (RF-M5-01), con buscador para reutilizar una
entrada antes de crear otra (RF-M5-02), vínculo con la TRD (RF-M5-03) y
registro de quién creó o modificó cada entrada y cuándo (RF-M5-04).

La TRD vive aquí como Mandato (serie/subserie con retención y disposición
final) + Actividad (la función, ejecutada por su oficina productora) +
formas documentales (los tipos que produce la serie), según la corrección
de la especificación v3."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import acceso_documentos, desambiguacion, flujo, fusion, instrumentos, reglas, roles, tipos
from .models import Activity, FormaDocumental, Mandate, Record, RelacionRiC

_SLUG_FORMA = "formadocumental"


def _tipos_autoridad():
    """Los tipos concretos que son entradas de autoridad (no documentos)."""
    from django.apps import apps

    catalogo = []
    for rid in tipos.TIPOS_CONCRETOS:
        if rid in tipos.TIPOS_DOCUMENTALES:
            continue
        nombre_modelo = tipos.RIC_ID_A_MODELO_NOMBRE[rid]
        modelo = apps.get_model("ric", nombre_modelo)
        catalogo.append({
            "ric_id": rid, "slug": nombre_modelo.lower(), "modelo": modelo,
            "nombre": modelo._meta.verbose_name_plural.capitalize(),
            "total": tipos.instancias_propias(modelo).count(),
        })
    catalogo.append({
        "ric_id": "A17", "slug": _SLUG_FORMA, "modelo": FormaDocumental,
        "nombre": "Formas documentales", "total": FormaDocumental.objects.count(),
    })
    return catalogo


def _modelos_con_duplicados():
    return fusion.modelos_fusionables() + [FormaDocumental]


def _total_duplicados(total_entradas):
    """El conteo recorre todo el vocabulario con trigramas; se guarda unos
    minutos y se recalcula solo cuando cambia el número de entradas."""
    return cache.get_or_set(
        f"ric_duplicados_{total_entradas}",
        lambda: sum(len(desambiguacion.pares_similares(m)) for m in _modelos_con_duplicados()),
        300,
    )


@login_required
def vocabularios(request):
    if request.method == "POST":
        if not roles.puede(request.user, roles.ARCHIVISTA):
            messages.error(request, "Solo una cuenta archivista puede crear entradas de vocabulario.")
            return redirect("vocabularios")
        nombre = request.POST.get("nombre", "").strip()
        if not nombre:
            messages.error(request, "Escriba el nombre de la forma documental.")
            return redirect(f"/vocabularios/?tipo={_SLUG_FORMA}")
        forma, creada = FormaDocumental.objects.get_or_create(
            nombre=nombre,
            defaults={
                "definicion": request.POST.get("definicion", "").strip(),
                "serie_trd": request.POST.get("serie_trd", "").strip(),
                "creado_por": request.user,
            },
        )
        if creada:
            messages.success(request, f"Forma documental «{forma.nombre}» creada.")
        else:
            messages.info(request, f"«{forma.nombre}» ya existía en el vocabulario (RF-M5-02: no se duplicó).")
        return redirect(f"/vocabularios/?tipo={_SLUG_FORMA}")

    filtro = request.GET.get("tipo", "").strip().lower()
    q = request.GET.get("q", "").strip()
    catalogo = _tipos_autoridad()
    por_slug = {c["slug"]: c for c in catalogo}

    filas = []
    if filtro == _SLUG_FORMA:
        qs = FormaDocumental.objects.all()
        if q:
            qs = qs.filter(nombre__icontains=q)
        for f in qs[:2000]:
            filas.append({"pk": f.pk, "nombre": f.nombre, "tipo": "Forma documental", "slug": _SLUG_FORMA,
                          "serie_trd": f.serie_trd, "fecha": f.fecha_registro, "creado_por": f.creado_por})
    else:
        seleccion = [por_slug[filtro]] if filtro in por_slug else [c for c in catalogo if c["slug"] != _SLUG_FORMA]
        limite = 2000 if filtro else 60
        for c in seleccion:
            qs = tipos.instancias_propias(c["modelo"]).select_related("creado_por").order_by("nombre" if filtro else "-fecha_registro")
            if q:
                qs = qs.filter(Q(nombre__icontains=q) | Q(identificador__icontains=q))
            for e in qs[:limite]:
                filas.append({"pk": e.pk, "nombre": e.nombre, "tipo": c["modelo"]._meta.verbose_name, "slug": c["slug"],
                              "serie_trd": e.serie_trd, "fecha": e.fecha_registro, "creado_por": e.creado_por,
                              "identificador": e.identificador})
        if not filtro:
            filas.sort(key=lambda f: f["fecha"], reverse=True)
            filas = filas[:120]

    # RF-M8-04: el rol consulta solo ve autoridades presentes en documentos
    # que puede consultar o en los instrumentos archivísticos (públicos).
    vis = acceso_documentos.Visibilidad(request.user)
    if not vis.todo and filtro != _SLUG_FORMA:
        modelos = {c["slug"]: c["modelo"] for c in catalogo}
        filas = [f for f in filas if f["slug"] not in modelos or vis.puede(modelos[f["slug"]](pk=f["pk"]))]
    total = sum(c["total"] for c in catalogo)
    from urllib.parse import urlencode

    from django.core.paginator import Paginator

    pagina = Paginator(filas, 15).get_page(request.GET.get("pagina"))
    return render(request, "ric/vocabularios.html", {
        "catalogo": catalogo, "filas": pagina.object_list, "total_filas": len(filas), "pagina": pagina,
        "parametros": urlencode({k: v for k, v in (("tipo", filtro), ("q", q)) if v}),
        "filtro": filtro, "q": q,
        "total": total,
        "es_forma": filtro == _SLUG_FORMA,
        "puede_editar": roles.puede(request.user, roles.ARCHIVISTA),
        "duplicados": _total_duplicados(total),
        "columnas_instrumentos": {k: v["obligatorias"] + v["opcionales"] for k, v in instrumentos.COLUMNAS.items()},
        "semilla_mads": instrumentos.semilla_mads_disponible(),
        "series_trd": Mandate.objects.filter(tipo_mandato=instrumentos.TIPO_MANDATO_TRD).count(),
    })


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def vocabularios_importar(request):
    """Precarga de TRD, cuadro de clasificación u organigrama (CSV o JSON):
    el insumo que CC-05 necesita para tener contra qué verificar."""
    tipo = request.POST.get("instrumento", "")
    archivo = request.FILES.get("archivo")
    if tipo not in instrumentos.IMPORTADORES or archivo is None:
        messages.error(request, "Elija el instrumento (TRD, CCD u organigrama) y su archivo CSV o JSON.")
        return redirect("vocabularios")
    try:
        resultado = instrumentos.IMPORTADORES[tipo](archivo.read(), request.user)
    except instrumentos.ErrorDeImportacion as e:
        messages.error(request, f"No se importó «{archivo.name}»: {e}")
        return redirect("vocabularios")
    detalle = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in resultado.items() if k != "filas")
    messages.success(request, f"{tipo.upper()} «{archivo.name}»: {resultado['filas']} fila(s) leídas — {detalle}.")
    return redirect("vocabularios")


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def vocabularios_sembrar(request):
    """Carga la semilla del Ministerio de Ambiente (organigrama + 54 TRD
    oficiales) incluida en ric/fixtures/mads. Idempotente."""
    try:
        resumen = instrumentos.sembrar_mads(request.user)
    except instrumentos.ErrorDeImportacion as e:
        messages.error(request, str(e))
        return redirect("vocabularios")
    o, t = resumen["organigrama"], resumen["trd"]
    messages.success(
        request,
        f"Semilla MADS cargada: {o['creadas']} dependencias y {o['funcionarios']} funcionarios nuevos; "
        f"{t['series']} series de la TRD leídas ({t['mandatos']} mandatos y {t['actividades']} actividades nuevas), "
        f"{t['formas_documentales']} formas documentales nuevas y {o['relaciones'] + t['relaciones']} relaciones RiC nuevas.",
    )
    return redirect("vocabularios")


def _documentos_relacionados(entidad):
    """Los Record que apuntan a esta entidad mediante una relación validada."""
    ct = ContentType.objects.get_for_model(entidad)
    ct_record = ContentType.objects.get_for_model(Record)
    pks = (
        RelacionRiC.objects.filter(
            destino_content_type=ct, destino_object_id=entidad.pk,
            origen_content_type=ct_record, estado__in=flujo.ESTADOS_VALIDADOS,
        ).values_list("origen_object_id", flat=True)
    )
    return Record.objects.filter(pk__in=pks).order_by("nombre")


def _relaciones_de_entidad(entidad):
    ct = ContentType.objects.get_for_model(entidad)
    matriz = reglas.cargar_matriz()["relaciones"]
    filas = []
    for rel in RelacionRiC.objects.filter(
        Q(origen_content_type=ct, origen_object_id=entidad.pk) | Q(destino_content_type=ct, destino_object_id=entidad.pk),
        estado__in=flujo.ESTADOS_VALIDADOS,
    ).select_related("validado_por"):
        soy_origen = rel.origen_content_type_id == ct.pk and rel.origen_object_id == entidad.pk
        otro = rel.destino if soy_origen else rel.origen
        if otro is None:
            continue
        filas.append({
            "relacion": rel, "nombre": matriz.get(rel.relacion_id, {}).get("nombre", rel.relacion_id),
            "otro": otro, "otro_slug": type(otro).__name__.lower(), "direccion": "→" if soy_origen else "←",
        })
    return filas


def _entero_o_none(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return max(0, int(valor))
    except ValueError:
        return None


def _fecha_o_none(valor):
    import datetime

    try:
        return datetime.date.fromisoformat((valor or "").strip()) if (valor or "").strip() else None
    except ValueError:
        return None


def _guardar_mandato(mandato, post, usuario):
    """Los campos de la TRD que la especificación v3 pone sobre el Mandato."""
    mandato.codigo_serie = post.get("codigo_serie", "").strip()
    mandato.codigo_subserie = post.get("codigo_subserie", "").strip()
    mandato.tiempo_retencion_archivo_gestion = _entero_o_none(post.get("retencion_gestion"))
    mandato.tiempo_retencion_archivo_central = _entero_o_none(post.get("retencion_central"))
    for campo, codigo, _ in Mandate.DISPOSICIONES:
        setattr(mandato, campo, post.get(f"disposicion_{codigo}") == "1")
    mandato.soporte = post.get("soporte", "").strip()
    mandato.procedimiento = post.get("procedimiento", "").strip()
    if mandato.es_serie_trd and not mandato.tipo_mandato:
        mandato.tipo_mandato = instrumentos.TIPO_MANDATO_TRD


@login_required
def vocabulario_ficha(request, tipo, pk):
    puede_editar = roles.puede(request.user, roles.ARCHIVISTA)
    if tipo == _SLUG_FORMA:
        forma = get_object_or_404(FormaDocumental, pk=pk)
        if request.method == "POST":
            if not puede_editar:
                messages.error(request, "Solo una cuenta archivista puede editar el vocabulario.")
                return redirect("vocabulario_ficha", tipo=tipo, pk=pk)
            forma.nombre = request.POST.get("nombre", forma.nombre).strip() or forma.nombre
            forma.definicion = request.POST.get("definicion", "").strip()
            forma.serie_trd = request.POST.get("serie_trd", "").strip()
            forma.modificado_por = request.user
            forma.save()
            messages.success(request, "Forma documental actualizada.")
            return redirect("vocabulario_ficha", tipo=tipo, pk=pk)
        return render(request, "ric/vocabulario_ficha.html", {
            "es_forma": True, "entidad": forma, "tipo": tipo, "puede_editar": puede_editar,
            "documentos": acceso_documentos.documentos_visibles(request.user).filter(forma_documental=forma).order_by("nombre"),
            "series": forma.series(),
            "duplicados": desambiguacion.candidatos_similares(FormaDocumental, forma.nombre, excluir_pk=forma.pk),
            "fusionable": True,
        })

    modelo = tipos.modelo_por_slug(tipo)
    if modelo is None:
        messages.error(request, f"Tipo de entidad desconocido: {tipo}.")
        return redirect("vocabularios")
    entidad = get_object_or_404(modelo, pk=pk)
    vis = acceso_documentos.Visibilidad(request.user)
    if not vis.puede(entidad):
        messages.error(request, "Esta ficha no está disponible para consulta.")
        return redirect("vocabularios")
    es_mandato = isinstance(entidad, Mandate)
    es_actividad = isinstance(entidad, Activity)

    if request.method == "POST":
        if not puede_editar:
            messages.error(request, "Solo una cuenta archivista puede editar el vocabulario.")
            return redirect("vocabulario_ficha", tipo=tipo, pk=pk)
        entidad.nombre = request.POST.get("nombre", entidad.nombre).strip() or entidad.nombre
        entidad.identificador = request.POST.get("identificador", "").strip()
        entidad.descripcion_general = request.POST.get("descripcion_general", "").strip()
        entidad.serie_trd = request.POST.get("serie_trd", "").strip()
        if hasattr(entidad, "nombres_alternativos"):  # Agent (especificación v5)
            entidad.nombres_alternativos = "\n".join(l.strip() for l in request.POST.get("nombres_alternativos", "").splitlines() if l.strip())
        if hasattr(entidad, "fecha_expedicion"):  # Rule / Mandate
            entidad.fecha_expedicion = _fecha_o_none(request.POST.get("fecha_expedicion"))
            entidad.enlace_texto_completo = request.POST.get("enlace_texto_completo", "").strip()
        if es_mandato:
            _guardar_mandato(entidad, request.POST, request.user)
        entidad.modificado_por = request.user
        entidad.save()  # F07: la versión anterior queda en VersionRiC
        messages.success(request, f"Entrada «{entidad.nombre}» actualizada.")
        return redirect("vocabulario_ficha", tipo=tipo, pk=pk)

    fusionable = type(entidad).__name__ in fusion.NOMBRES_MODELOS_FUSIONABLES
    contexto = {
        "es_forma": False, "entidad": entidad, "tipo": tipo, "puede_editar": puede_editar,
        "tipo_nombre": modelo._meta.verbose_name, "ric_id": {v: k for k, v in tipos.RIC_ID_A_MODELO_NOMBRE.items()}[modelo.__name__],
        "relaciones": [r for r in _relaciones_de_entidad(entidad) if vis.puede(r["otro"])],
        "documentos": [d for d in _documentos_relacionados(entidad) if vis.puede(d)],
        "duplicados": desambiguacion.candidatos_similares(type(entidad), entidad.nombre, excluir_pk=entidad.pk, identificador=entidad.identificador) if fusionable else [],
        "fusionable": fusionable,
        "es_mandato": es_mandato, "es_actividad": es_actividad,
        "es_agente": hasattr(entidad, "nombres_alternativos"), "es_regla": hasattr(entidad, "fecha_expedicion"),
    }
    if es_mandato:
        contexto["disposiciones"] = [(codigo, nombre, getattr(entidad, campo)) for campo, codigo, nombre in Mandate.DISPOSICIONES]
        contexto["actividades_reguladas"] = entidad.actividades.order_by("nombre")
    if es_actividad:
        contexto["formas_actividad"] = entidad.formas_documentales.order_by("nombre")
    return render(request, "ric/vocabulario_ficha.html", contexto)


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def vocabularios_duplicados(request):
    from django.core.paginator import Paginator

    grupos, filas = [], []
    for modelo in _modelos_con_duplicados():
        pares = desambiguacion.pares_similares(modelo)
        if pares:
            grupos.append({"nombre_verbose": modelo._meta.verbose_name_plural, "slug": modelo.__name__.lower(), "pares": pares})
            filas.extend({"clase": modelo._meta.verbose_name_plural, "slug": modelo.__name__.lower(), "a": a, "b": b} for a, b in pares)
    pagina = Paginator(filas, 15).get_page(request.GET.get("pagina"))
    return render(request, "ric/vocabularios_duplicados.html", {
        "grupos": grupos, "total": len(filas), "pagina": pagina, "parametros": "",
        "puede_editar": roles.puede(request.user, roles.ARCHIVISTA),
    })


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def vocabulario_fusionar(request, tipo, pk):
    """Fusionar una entrada duplicada en esta (F08): mueve sus relaciones y
    la retira, conservando su fotografía en el historial de versiones."""
    if tipo == _SLUG_FORMA:
        superviviente = get_object_or_404(FormaDocumental, pk=pk)
        duplicada = get_object_or_404(FormaDocumental, pk=request.POST.get("duplicada"))
        try:
            resultado = fusion.fusionar_formas(duplicada, superviviente, usuario=request.user)
        except fusion.ErrorDeFusion as e:
            messages.error(request, str(e))
            return redirect("vocabulario_ficha", tipo=tipo, pk=pk)
        messages.success(
            request,
            f"«{duplicada}» fusionada en «{superviviente}»: {resultado['documentos_movidos']} documento(s) y "
            f"{resultado['series_movidas']} serie(s) de la TRD ahora apuntan a esta forma documental.",
        )
        return redirect("vocabulario_ficha", tipo=tipo, pk=pk)

    modelo = tipos.modelo_por_slug(tipo)
    superviviente = get_object_or_404(modelo, pk=pk)
    duplicada = get_object_or_404(modelo, pk=request.POST.get("duplicada"))
    try:
        resultado = fusion.fusionar_entidades(duplicada, superviviente, usuario=request.user)
    except fusion.ErrorDeFusion as e:
        messages.error(request, str(e))
        return redirect("vocabulario_ficha", tipo=tipo, pk=pk)
    superviviente.modificado_por = request.user
    superviviente.save(update_fields=["modificado_por"])
    messages.success(
        request,
        f"«{duplicada}» fusionada en «{superviviente}»: {resultado['relaciones_movidas']} relación(es) y "
        f"{resultado['propuestas_movidas']} propuesta(s) movidas.",
    )
    return redirect("vocabulario_ficha", tipo=tipo, pk=pk)
