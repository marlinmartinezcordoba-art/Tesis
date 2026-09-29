"""M1 · Ingesta de documentos (/ingesta) y M2 · Preprocesamiento y OCR
(/ingesta/preproceso), con el flujo clic a clic "Cargar y procesar un
documento nuevo" y su ruta alterna de calidad baja."""

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST


from . import carga, clasificacion, cola, flujo, roles
from .idioma import nombre_idioma
from .models import Activity, ConfiguracionSistema, EventoRiC, Instantiation, PropuestaRiC, Record, RecordSet, registrar_evento

FORMATOS_SOPORTADOS = carga.FORMATOS_SOPORTADOS
_EXT_IMAGEN_VISOR = {".jpg", ".jpeg", ".png"}


def _estado_preproceso(instanciacion):
    """El estado lo escribe el trabajador; entre «listo» y «calidad baja»
    manda la situación actual de las páginas, porque el umbral de calidad
    es configurable (M11) y las decisiones página a página la cambian."""
    estado = instanciacion.estado_proceso
    if estado in (Instantiation.EstadoProceso.LISTO, Instantiation.EstadoProceso.CALIDAD_BAJA):
        baja = instanciacion.paginas_calidad_baja().exists()
        return Instantiation.EstadoProceso.CALIDAD_BAJA if baja else Instantiation.EstadoProceso.LISTO
    return estado


def _fecha(valor):
    import datetime

    try:
        return datetime.date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _carpeta(ruta):
    """Opción C: el nombre de la carpeta que contiene al archivo es su expediente."""
    partes = [p for p in (ruta or "").replace("\\", "/").split("/") if p]
    return partes[-2] if len(partes) >= 2 else ""


def _actividad(valor):
    return Activity.objects.filter(pk=valor, mandato__isnull=False).select_related("mandato").first() if str(valor).isdigit() else None


def _expediente(valor):
    return RecordSet.objects.filter(pk=valor, tipo_conjunto=RecordSet.Tipo.EXPEDIENTE).first() if str(valor).isdigit() else None


def _resolver_expediente(post, actividad, usuario, ruta=""):
    """Carpeta > expediente elegido > expediente nuevo. Devuelve (expediente, creado)."""
    carpeta = _carpeta(ruta)
    if carpeta:
        return clasificacion.crear_expediente(actividad, carpeta, usuario, fecha_apertura=_fecha(post.get("fecha_apertura")))
    elegido = _expediente(post.get("expediente_id", "")) if post.get("modo_expediente") != "nuevo" else None
    if elegido is not None:
        if not clasificacion.expedientes_de(actividad).filter(pk=elegido.pk).exists():
            raise carga.ArchivoRechazado("el expediente elegido no pertenece a la serie seleccionada.")
        return elegido, False
    nombre = post.get("expediente_nuevo", "").strip()
    if nombre:
        return clasificacion.crear_expediente(
            actividad, nombre, usuario, codigo=post.get("expediente_codigo", "").strip(), fecha_apertura=_fecha(post.get("fecha_apertura")),
        )
    return None, False


def _fila(instanciacion):
    record = _record_de(instanciacion)
    expediente = record.record_set if record is not None else None
    return {
        "ok": True,
        "instanciacion_id": instanciacion.pk, "nombre": instanciacion.nombre, "sha256": instanciacion.sha256,
        "formato": instanciacion.formato, "tipo_mime": instanciacion.tipo_mime, "tamano_bytes": instanciacion.tamano_bytes,
        "documento_id": record.pk if record else None, "documento": str(record) if record else "",
        "expediente_id": expediente.pk if expediente else None, "expediente": str(expediente) if expediente else "",
        "visor_url": reverse("visor_documento", args=[record.pk]) + f"?inst={instanciacion.pk}" if record else "",
    }


@roles.requiere_rol_api(roles.ARCHIVISTA)
@require_POST
def ingesta_archivo(request):
    """Carga de UN archivo (RF-M1-01 a RF-M1-04), llamada por la pantalla
    una vez por archivo con barra de avance: un archivo pesado o rechazado
    no bloquea a los demás. Responde JSON con la fila de la tabla."""
    archivo = request.FILES.get("archivo")
    if archivo is None:
        return JsonResponse({"ok": False, "error": "No llegó ningún archivo."}, status=400)
    reemplaza = Instantiation.objects.filter(pk=request.POST.get("reemplaza_id")).first() if request.POST.get("reemplaza_id", "").isdigit() else None
    record = None
    if request.POST.get("documento_id", "").isdigit():  # parte de un mismo documento ya creado en esta carga
        record = Record.objects.filter(pk=request.POST["documento_id"]).first()
    try:
        carga.validar(archivo)
        expediente, creado = None, False
        if reemplaza is None and record is None:
            actividad = _actividad(request.POST.get("serie_id", ""))
            if actividad is None:
                raise carga.ArchivoRechazado("elija primero la serie o subserie de la TRD.")
            expediente, creado = _resolver_expediente(request.POST, actividad, request.user, ruta=request.POST.get("ruta", ""))
            if expediente is None:
                raise carga.ArchivoRechazado("indique el expediente al que pertenece o escriba el nombre de uno nuevo.")
        elif record is not None:
            expediente = record.record_set
        instanciacion = carga.registrar_archivo(
            archivo, request.user, expediente=expediente, record=record, reemplaza=reemplaza,
            nombre_doc=request.POST.get("nombre_documento", "").strip() if request.POST.get("un_solo_documento") == "1" else "",
        )
    except carga.ArchivoRechazado as e:
        return JsonResponse({"ok": False, "error": f"«{archivo.name}»: {e}"}, status=400)
    fila = _fila(instanciacion)
    fila["expediente_creado"] = creado
    return JsonResponse(fila, status=201)


@roles.requiere_rol(roles.ARCHIVISTA)
def ingesta(request):
    """Captura y clasificación (opción A): 1) la serie o subserie de la TRD,
    2) el expediente de esa serie (existente o nuevo; o el nombre de la
    carpeta cargada), 3) los archivos, cada uno un documento salvo que sean
    partes de un mismo documento. La pantalla sube archivo por archivo a
    `ingesta_archivo` con su barra de avance; este POST es el respaldo sin
    JavaScript. Ninguno de los dos preprocesa: eso lo pide el archivista con
    «Enviar a preprocesamiento» cuando no queda ninguna carga en curso."""
    errores, cargados = [], []
    reemplaza = None
    if request.GET.get("reemplaza") or request.POST.get("reemplaza_id"):
        reemplaza = Instantiation.objects.filter(pk=request.GET.get("reemplaza") or request.POST.get("reemplaza_id")).select_related("record_resource").first()
    actividad = _actividad(request.POST.get("serie_id") or request.GET.get("serie", ""))
    expediente = _expediente(request.POST.get("expediente_id") or request.GET.get("expediente", ""))

    if request.method == "POST":
        archivos = request.FILES.getlist("archivos")
        rutas = request.POST.getlist("rutas")
        un_solo = request.POST.get("un_solo_documento") == "1"
        if not archivos:
            errores.append("Seleccione al menos un archivo para cargar.")
        if reemplaza is None and actividad is None:
            errores.append("Elija primero la serie o subserie de la TRD a la que pertenece el expediente.")
        elif reemplaza is None and not any(_carpeta(r) for r in rutas) and expediente is None and not request.POST.get("expediente_nuevo", "").strip():
            errores.append("Indique a qué expediente pertenece el documento, o escriba el nombre de uno nuevo.")
        # Primero se validan todos: un expediente nuevo no se crea si ningún archivo sirve.
        faltan_datos = bool(errores)
        validos = []
        for i, archivo in enumerate(archivos):
            try:
                carga.validar(archivo)
                validos.append((i, archivo))
            except carga.ArchivoRechazado as e:
                errores.append(f"«{archivo.name}»: {e}")
        if validos and not faltan_datos:
            record = None
            for i, archivo in validos:
                try:
                    if reemplaza is not None:
                        inst = carga.registrar_archivo(archivo, request.user, reemplaza=reemplaza)
                    else:
                        destino, creado = _resolver_expediente(request.POST, actividad, request.user, ruta=rutas[i] if i < len(rutas) else "")
                        if creado:
                            messages.success(request, f"Expediente «{destino.nombre}» creado en {destino.ruta_texto()}.")
                        inst = carga.registrar_archivo(
                            archivo, request.user, expediente=destino, record=record if un_solo else None,
                            nombre_doc=request.POST.get("nombre_documento", "").strip() if un_solo else "",
                        )
                        if un_solo and record is None:
                            record = _record_de(inst)
                    cargados.append(inst)
                except carga.ArchivoRechazado as e:
                    errores.append(f"«{archivo.name}»: {e}")
            if reemplaza is not None and cargados:
                reemplaza = None

    en_cola = (
        Instantiation.objects.filter(estado_proceso=Instantiation.EstadoProceso.SIN_ENVIAR)
        .exclude(pk__in=[i.pk for i in cargados])
        .select_related("record_resource")
        .order_by("-fecha_registro")[:50]
    )
    q = request.GET.get("q", "").strip()
    return render(request, "ric/ingesta.html", {
        "q": q,
        "series": clasificacion.series_trd(q) if (q or actividad is None) else [],
        "hay_series": Activity.objects.filter(mandato__isnull=False).exists(),
        "actividad": actividad,
        "oficina": clasificacion.oficina_de(actividad) if actividad else None,
        "expedientes": clasificacion.expedientes_de(actividad) if actividad else [],
        "expediente": expediente,
        "errores": errores,
        "cargados": [_fila(i) for i in cargados],
        "en_cola": en_cola,
        "reemplaza": reemplaza,
        "formatos": ", ".join(FORMATOS_SOPORTADOS),
        "extensiones": ",".join(FORMATOS_SOPORTADOS),
        "tamano_maximo": settings.RICORA_TAMANO_MAXIMO_MB,
    })


def _record_de(instanciacion):
    """El Record concreto (herencia multitabla: la FK apunta a RecordResource)."""
    return Record.objects.filter(pk=instanciacion.record_resource_id).first()


def _filas_preproceso(instanciaciones):
    filas = []
    for inst in instanciaciones:
        record = _record_de(inst) or inst.record_resource
        estado_doc = flujo.estado_documento(record) if isinstance(record, Record) else None
        filas.append({
            "instanciacion": inst,
            "estado": _estado_preproceso(inst),
            "perdido": cola.perdido(inst),
            "paginas": inst.paginas.count(),
            "calidad_baja": list(inst.paginas_calidad_baja().values_list("numero", flat=True)),
            "idioma": nombre_idioma(inst.idioma_detectado),
            # Propuestas reales del motor (M3): las relaciones estructurales que
            # deja la clasificación en el expediente no cuentan como análisis.
            "tiene_propuestas": bool(estado_doc) and PropuestaRiC.objects.filter(
                origen_content_type=_ct_record(), origen_object_id=record.pk).exists(),
            "record": record,
        })
    return filas


def _ct_record():
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(Record)


def _estado_json(fila):
    inst, record = fila["instanciacion"], fila["record"]
    accion = None
    if fila["estado"] == Instantiation.EstadoProceso.CALIDAD_BAJA:
        accion = {"tipo": "decidir", "paginas": [
            {"numero": n, "url": reverse("preproceso_pagina", args=[inst.pk, n])} for n in fila["calidad_baja"]]}
    elif fila["estado"] == Instantiation.EstadoProceso.LISTO and isinstance(record, Record):
        accion = {"tipo": "propuestas", "url": reverse("analisis", args=[record.pk])} if fila["tiene_propuestas"] else \
            {"tipo": "motor", "url": reverse("analisis_generar", args=[record.pk])}
    return {
        "id": inst.pk, "estado": fila["estado"], "etiqueta": inst.get_estado_proceso_display(),
        "progreso": inst.progreso, "etapa": inst.etapa, "mensaje": inst.mensaje_proceso,
        "paginas": fila["paginas"], "idioma": fila["idioma"], "perdido": fila["perdido"],
        "reintentar": fila["estado"] in (Instantiation.EstadoProceso.ERROR, Instantiation.EstadoProceso.SIN_ENVIAR) or fila["perdido"],
        "accion": accion,
    }


def _instanciaciones_preproceso():
    return Instantiation.objects.select_related("record_resource").order_by("-fecha_registro")[:100]


@roles.requiere_rol(roles.ARCHIVISTA)
def preproceso(request):
    filas = _filas_preproceso(_instanciaciones_preproceso())
    activos = any(f["estado"] in cola.ACTIVOS for f in filas)
    return render(request, "ric/preproceso.html", {
        "filas": filas,
        "sin_trabajador": activos and not cola.trabajadores_activos(),
    })


@roles.requiere_rol_api(roles.ARCHIVISTA)
def preproceso_estado(request):
    """Consulta de la pantalla cada 2 s mientras haya archivos en cola o
    procesando (RF-M2-01: avance visible por archivo)."""
    ids = [v for v in request.GET.get("ids", "").split(",") if v.isdigit()][:100]
    consulta = Instantiation.objects.select_related("record_resource")
    consulta = consulta.filter(pk__in=ids) if ids else _instanciaciones_preproceso()
    filas = [_estado_json(f) for f in _filas_preproceso(consulta)]
    activos = any(f["estado"] in cola.ACTIVOS for f in filas)
    return JsonResponse({"archivos": filas, "trabajadores": cola.trabajadores_activos(),
                         "sin_trabajador": activos and not cola.trabajadores_activos()})


def _encolar_varios(request, instanciaciones, tarea=cola.PREPROCESAR):
    enviados, ya_en_cola = 0, 0
    for inst in instanciaciones:
        try:
            if cola.encolar(inst, request.user, tarea=tarea):
                enviados += 1
            else:
                ya_en_cola += 1
        except cola.ColaNoDisponible:
            messages.error(request, "La cola de procesamiento no está disponible en este momento. Intente de nuevo en unos "
                           "minutos; si persiste, avise al administrador.")
            return
    if enviados:
        messages.success(request, f"{enviados} archivo(s) enviados a preprocesamiento. Puede seguir trabajando: "
                         "el avance se actualiza solo en esta pantalla.")
    if ya_en_cola:
        messages.info(request, f"{ya_en_cola} archivo(s) ya estaban en la cola; no se enviaron de nuevo.")


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def preproceso_enviar(request):
    """Paso 5 del flujo: "Enviar a preprocesamiento". Pone los archivos en
    la cola y vuelve de inmediato; el trabajador hace OCR, idioma, calidad
    y la entrega al motor de análisis (M3) en segundo plano."""
    ids = [v for v in request.POST.getlist("instanciacion") if str(v).isdigit()]
    instanciaciones = list(Instantiation.objects.filter(pk__in=ids))
    if not instanciaciones:
        messages.error(request, "No se indicó ningún archivo para preprocesar.")
        return redirect("ingesta")
    _encolar_varios(request, instanciaciones)
    return redirect("preproceso")


@roles.requiere_rol(roles.ARCHIVISTA)
def preproceso_pagina(request, pk, numero):
    """Ruta alterna, calidad baja: el visor ampliado de una página."""
    instanciacion = get_object_or_404(Instantiation.objects.select_related("record_resource"), pk=pk)
    pagina = get_object_or_404(instanciacion.paginas, numero=numero)
    extension = Path(instanciacion.archivo.name).suffix.lower()
    return render(request, "ric/preproceso_pagina.html", {
        "instanciacion": instanciacion,
        "pagina": pagina,
        "es_imagen": extension in _EXT_IMAGEN_VISOR,
        "umbral": ConfiguracionSistema.actual().umbral_calidad_ocr,
    })


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def preproceso_pagina_decidir(request, pk, numero):
    instanciacion = get_object_or_404(Instantiation.objects.select_related("record_resource"), pk=pk)
    pagina = get_object_or_404(instanciacion.paginas, numero=numero)
    decision = request.POST.get("decision")
    if decision == "aceptar":
        pagina.calidad_aceptada = True
        pagina.save(update_fields=["calidad_aceptada"])
        registrar_evento(
            instanciacion, EventoRiC.Tipo.EXTRACCION, agente=request.user,
            detalle={"pagina": numero, "decision": "aceptar_igual", "confianza_ocr": pagina.confianza_ocr},
        )
        messages.success(request, f"Página {numero} aceptada tal como está.")
        if not instanciacion.paginas_calidad_baja().exists():
            record = _record_de(instanciacion)
            if record is not None and flujo.estado_documento(record) == flujo.SIN_ANALIZAR:
                _encolar_varios(request, [instanciacion], tarea=cola.ANALIZAR)
            else:
                Instantiation.objects.filter(pk=instanciacion.pk).update(
                    estado_proceso=Instantiation.EstadoProceso.LISTO, mensaje_proceso="Páginas de calidad baja aceptadas.")
        return redirect("preproceso")
    if decision == "reescanear":
        pagina.calidad_aceptada = False
        pagina.save(update_fields=["calidad_aceptada"])
        registrar_evento(
            instanciacion, EventoRiC.Tipo.EXTRACCION, agente=request.user,
            detalle={"pagina": numero, "decision": "reescanear", "confianza_ocr": pagina.confianza_ocr},
        )
        if not instanciacion.paginas_calidad_baja().exists():
            Instantiation.objects.filter(pk=instanciacion.pk).update(
                estado_proceso=Instantiation.EstadoProceso.LISTO,
                mensaje_proceso="Página(s) marcadas para reescanear: cargue el nuevo escaneo en el mismo expediente.")
        messages.info(
            request,
            f"Página {numero} devuelta a ingesta: cargue el nuevo escaneo de «{instanciacion.nombre}» en el mismo expediente. "
            "El archivo original se conserva intacto, con su huella digital.",
        )
        return redirect(f"/ingesta/?reemplaza={instanciacion.pk}")
    messages.error(request, "Decisión no reconocida.")
    return redirect("preproceso_pagina", pk=pk, numero=numero)
