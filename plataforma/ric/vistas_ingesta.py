"""M1 · Ingesta de documentos (/ingesta) y M2 · Preprocesamiento y OCR
(/ingesta/preproceso), con el flujo clic a clic "Cargar y procesar un
documento nuevo" y su ruta alterna de calidad baja."""

from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from acervo.extraccion import EXT_DOCX, EXT_IMAGEN, EXT_TEXTO

from . import clasificacion, flujo, roles
from .idioma import nombre_idioma
from .models import Activity, ConfiguracionSistema, EventoRiC, Instantiation, Record, RecordSet, registrar_evento

FORMATOS_SOPORTADOS = sorted(EXT_TEXTO | EXT_IMAGEN | EXT_DOCX | {".pdf"})
_EXT_IMAGEN_VISOR = {".jpg", ".jpeg", ".png"}


def _validar_archivo(archivo):
    """RF-M1-03: formato y tamaño se revisan antes de guardar nada."""
    extension = Path(archivo.name).suffix.lower()
    if extension not in FORMATOS_SOPORTADOS:
        return (
            f"«{archivo.name}»: formato {extension or 'sin extensión'} no soportado. "
            f"Se aceptan {', '.join(FORMATOS_SOPORTADOS)}."
        )
    maximo = settings.RICORA_TAMANO_MAXIMO_MB
    if archivo.size > maximo * 1024 * 1024:
        return f"«{archivo.name}»: pesa {archivo.size / 1024 / 1024:.1f} MB y el máximo es {maximo} MB."
    return None


def _estado_preproceso(instanciacion):
    if not instanciacion.eventos.filter(tipo=EventoRiC.Tipo.EXTRACCION).exists():
        return "en_cola"
    if instanciacion.paginas_calidad_baja().exists():
        return "calidad_baja"
    return "listo"


def _fecha(valor):
    import datetime

    try:
        return datetime.date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def _agrupar_por_carpeta(archivos, rutas):
    """Opción C: al subir una carpeta, el nombre de la carpeta de primer
    nivel de cada archivo es su expediente. {carpeta: [archivos]}; la
    clave "" agrupa los archivos sueltos."""
    grupos = {}
    for i, archivo in enumerate(archivos):
        ruta = rutas[i] if i < len(rutas) else ""
        partes = [p for p in ruta.replace("\\", "/").split("/") if p]
        carpeta = partes[-2] if len(partes) >= 2 else ""
        grupos.setdefault(carpeta, []).append(archivo)
    return grupos


@roles.requiere_rol(roles.ARCHIVISTA)
def ingesta(request):
    """Captura y clasificación (opción A): 1) la serie o subserie de la TRD,
    2) el expediente de esa serie (existente o nuevo; o el nombre de la
    carpeta cargada), 3) los archivos, cada uno un documento salvo que sean
    partes de un mismo documento. Al cargar, el preprocesamiento (texto u
    OCR, idioma, calidad) corre solo y el documento pasa al motor."""
    from .ingesta import preprocesar

    errores, cargados = [], []
    reemplaza = None
    if request.GET.get("reemplaza") or request.POST.get("reemplaza_id"):
        reemplaza = Instantiation.objects.filter(pk=request.GET.get("reemplaza") or request.POST.get("reemplaza_id")).select_related("record_resource").first()

    serie_id = request.POST.get("serie_id") or request.GET.get("serie", "")
    actividad = Activity.objects.filter(pk=serie_id, mandato__isnull=False).select_related("mandato").first() if str(serie_id).isdigit() else None
    expediente_id = request.POST.get("expediente_id") or request.GET.get("expediente", "")
    expediente = RecordSet.objects.filter(pk=expediente_id, tipo_conjunto=RecordSet.Tipo.EXPEDIENTE).first() if str(expediente_id).isdigit() else None

    if request.method == "POST":
        archivos = request.FILES.getlist("archivos")
        rutas = request.POST.getlist("rutas")
        nombre_nuevo = request.POST.get("expediente_nuevo", "").strip()
        un_solo = request.POST.get("un_solo_documento") == "1"
        grupos = _agrupar_por_carpeta(archivos, rutas)
        con_carpetas = any(grupos) and expediente is None

        if not archivos:
            errores.append("Seleccione al menos un archivo para cargar.")
        for archivo in archivos:
            error = _validar_archivo(archivo)
            if error:
                errores.append(error)
        if reemplaza is None:
            if actividad is None:
                errores.append("Elija primero la serie o subserie de la TRD a la que pertenece el expediente.")
            elif expediente is None and not nombre_nuevo and not con_carpetas:
                errores.append("Indique a qué expediente pertenece el documento, o escriba el nombre de uno nuevo.")

        if not errores:
            nuevas = []
            if reemplaza is not None:
                record = _record_de(reemplaza)
                for archivo in archivos:
                    inst = Instantiation.objects.create(nombre=archivo.name, record_resource=record, archivo=archivo, creado_por=request.user, instanciacion_origen=reemplaza)
                    registrar_evento(inst, EventoRiC.Tipo.INGESTA, agente=request.user, detalle={"archivo": archivo.name, "formato": inst.formato, "tamano_bytes": inst.tamano_bytes, "sha256": inst.sha256, "reescaneo_de": reemplaza.nombre})
                    nuevas.append(inst)
                reemplaza = None
            elif con_carpetas:
                for carpeta, lista in grupos.items():
                    destino = expediente
                    if carpeta:
                        destino, _ = clasificacion.crear_expediente(actividad, carpeta, request.user, fecha_apertura=_fecha(request.POST.get("fecha_apertura")))
                    elif nombre_nuevo:
                        destino, _ = clasificacion.crear_expediente(actividad, nombre_nuevo, request.user, codigo=request.POST.get("expediente_codigo", "").strip(), fecha_apertura=_fecha(request.POST.get("fecha_apertura")))
                    if destino is None:
                        errores.append(f"{len(lista)} archivo(s) sueltos sin expediente: póngalos en una carpeta o escriba el nombre de un expediente nuevo.")
                        continue
                    nuevas += clasificacion.registrar_documentos(destino, lista, request.user, un_solo_documento=un_solo, nombre_documento=request.POST.get("nombre_documento", "").strip())
            else:
                if expediente is None:
                    expediente, creado = clasificacion.crear_expediente(
                        actividad, nombre_nuevo, request.user, codigo=request.POST.get("expediente_codigo", "").strip(),
                        fecha_apertura=_fecha(request.POST.get("fecha_apertura")),
                    )
                    if creado:
                        messages.success(request, f"Expediente «{expediente.nombre}» creado en {expediente.ruta_texto()}.")
                nuevas = clasificacion.registrar_documentos(expediente, archivos, request.user, un_solo_documento=un_solo, nombre_documento=request.POST.get("nombre_documento", "").strip())

            for inst in nuevas:
                resultado = preprocesar(inst, agente=request.user)
                _informar_resultado(request, inst, resultado)
                cargados.append(inst)

    en_cola = (
        Instantiation.objects.exclude(eventos__tipo=EventoRiC.Tipo.EXTRACCION)
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
        "cargados": [{"instanciacion": i, "estado": _estado_preproceso(i), "record": _record_de(i)} for i in cargados],
        "en_cola": en_cola,
        "reemplaza": reemplaza,
        "formatos": ", ".join(FORMATOS_SOPORTADOS),
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
            "paginas": inst.paginas.count(),
            "calidad_baja": list(inst.paginas_calidad_baja().values_list("numero", flat=True)),
            "idioma": nombre_idioma(inst.idioma_detectado),
            "tiene_propuestas": bool(estado_doc and estado_doc != flujo.SIN_TEXTO and estado_doc != flujo.SIN_ANALIZAR),
            "record": record,
        })
    return filas


@roles.requiere_rol(roles.ARCHIVISTA)
def preproceso(request):
    instanciaciones = Instantiation.objects.select_related("record_resource").order_by("-fecha_registro")[:100]
    return render(request, "ric/preproceso.html", {"filas": _filas_preproceso(instanciaciones)})


def _informar_resultado(request, instanciacion, resultado):
    nombre = instanciacion.nombre
    if resultado["formato_no_soportado"]:
        messages.warning(request, f"«{nombre}»: no fue posible extraer texto de este formato.")
        return
    partes = [f"{resultado['paginas']} página(s)"]
    if resultado["confianza_ocr"] is not None:
        partes.append(f"confianza OCR {resultado['confianza_ocr']}%")
    if resultado["idioma"]:
        partes.append(f"idioma {nombre_idioma(resultado['idioma']).lower()}")
    messages.success(request, f"«{nombre}» preprocesado: {', '.join(partes)}.")
    if resultado["calidad_baja"]:
        messages.warning(
            request,
            f"«{nombre}»: {resultado['calidad_baja']} página(s) con calidad de lectura baja. "
            "Decida si se reescanean o se aceptan antes de enviar al motor de análisis.",
        )
        return
    analisis = resultado.get("analisis") or {}
    if analisis.get("sin_proveedor"):
        messages.info(
            request,
            f"«{nombre}» está listo, pero no hay un proveedor de IA activo: configúrelo en "
            "Administración → Proveedores de IA para que el motor de análisis proponga entidades.",
        )
    elif analisis.get("error"):
        messages.error(request, f"«{nombre}»: el motor de análisis no respondió — {analisis['error']}")
    else:
        messages.success(request, f"«{nombre}» enviado al motor de análisis: {analisis.get('propuestas', 0)} propuesta(s) de entidades.")


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def preproceso_enviar(request):
    """Paso 5 del flujo: "Enviar a preprocesamiento" — OCR, idioma, calidad
    y entrega al motor de análisis, para uno o varios archivos."""
    from .ingesta import preprocesar

    ids = request.POST.getlist("instanciacion")
    instanciaciones = Instantiation.objects.filter(pk__in=ids).select_related("record_resource")
    if not instanciaciones:
        messages.error(request, "No se indicó ningún archivo para preprocesar.")
        return redirect("ingesta")
    for instanciacion in instanciaciones:
        resultado = preprocesar(instanciacion, agente=request.user)
        _informar_resultado(request, instanciacion, resultado)
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
    from .motor import enviar_al_motor

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
                analisis = enviar_al_motor(record, request.user)
                if analisis.get("sin_proveedor"):
                    messages.info(request, "Listo para el motor de análisis, pero no hay proveedor de IA activo (Administración → Proveedores de IA).")
                elif analisis.get("error"):
                    messages.error(request, f"El motor de análisis no respondió: {analisis['error']}")
                else:
                    messages.success(request, f"Enviado al motor de análisis: {analisis['propuestas']} propuesta(s).")
        return redirect("preproceso")
    if decision == "reescanear":
        pagina.calidad_aceptada = False
        pagina.save(update_fields=["calidad_aceptada"])
        registrar_evento(
            instanciacion, EventoRiC.Tipo.EXTRACCION, agente=request.user,
            detalle={"pagina": numero, "decision": "reescanear", "confianza_ocr": pagina.confianza_ocr},
        )
        messages.info(
            request,
            f"Página {numero} devuelta a ingesta: cargue el nuevo escaneo de «{instanciacion.nombre}» en el mismo expediente. "
            "El archivo original se conserva intacto, con su huella digital.",
        )
        return redirect(f"/ingesta/?reemplaza={instanciacion.pk}")
    messages.error(request, "Decisión no reconocida.")
    return redirect("preproceso_pagina", pk=pk, numero=numero)
