"""M3 · Motor de análisis RiC (/analisis/:documentoId), M4 · Modelado de
relaciones (/analisis/:documentoId/grafo), M6 · Revisión archivística
(/revision/:documentoId) y M7 · Trazabilidad y auditoría
(/documentos/:documentoId/historial), con el flujo "Revisar y aprobar la
descripción de un documento" y su ruta alterna de rechazo."""

import html

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from . import desambiguacion, flujo, grafo, reglas, roles, tipos
from .models import (
    ConfiguracionSistema,
    EventoRiC,
    FormaDocumental,
    PropuestaRiC,
    Record,
    RelacionRiC,
    registrar_evento,
    verificar_cadena,
)
from .motor import enviar_al_motor

# RF-M3-01: las clases del modelo conceptual con las que se agrupan las
# fichas — cada una reúne los tipos concretos RiC-CM que le corresponden.
CLASES = [
    ("documento", "Documento", {"E03", "E04", "E05", "E06"}),
    ("agente", "Agente", {"E07", "E08", "E09", "E10", "E11", "E12", "E13"}),
    ("actividad", "Actividad / Función", {"E14", "E15"}),
    ("fecha", "Fecha", {"E18"}),
    ("lugar", "Lugar", {"E22"}),
    ("mandato", "Mandato / Regla", {"E16", "E17"}),
]
_PASO_POR_ESTADO = {
    flujo.SIN_TEXTO: 2, flujo.SIN_ANALIZAR: 3, flujo.EN_ANALISIS: 3,
    flujo.EN_REVISION: 5, flujo.PUBLICADO: 6,
}


def _clase(entidad_tipo):
    for slug, nombre, ids in CLASES:
        if entidad_tipo in ids:
            return slug, nombre
    return "otra", "Otra"


def _contexto_documento(record, paso=None):
    estado = flujo.estado_documento(record)
    return {
        "record": record, "estado": estado, "etiqueta_estado": flujo.ETIQUETAS[estado],
        "paso_actual": paso or _PASO_POR_ESTADO[estado],
    }


def _ficha(propuesta):
    try:
        info = reglas.info_relacion(propuesta.relacion_id)
    except reglas.RelacionInvalida:
        info = None
    modelo = tipos.ric_id_a_modelo(propuesta.entidad_tipo)
    duplicados = desambiguacion.candidatos_similares(modelo, propuesta.entidad_nombre) if modelo else []
    extra = propuesta.datos_extra or {}
    # CC-05: la entrada del vocabulario que el motor (o la similitud) sugiere reutilizar.
    sugerida = None
    if modelo and extra.get("entidad_sugerida_id"):
        sugerida = modelo.objects.filter(pk=extra["entidad_sugerida_id"]).first()
    if sugerida is None and modelo:
        sugerida = modelo.objects.filter(nombre__iexact=propuesta.entidad_nombre).first()
    slug, nombre_clase = _clase(propuesta.entidad_tipo)
    return {
        "propuesta": propuesta,
        "info_relacion": info,
        "modelo_nombre": modelo._meta.verbose_name if modelo else propuesta.entidad_tipo,
        "candidatas": modelo.objects.order_by("nombre")[:300] if modelo else [],
        "posibles_duplicados": duplicados,
        "duplicado_pks": {d.pk for d in duplicados},
        "existente_exacta": sugerida,
        "clase": slug, "clase_nombre": nombre_clase,
        "evidencia_en_texto": bool(propuesta.evidencia and propuesta.evidencia.verificada),
        "baja_confianza": propuesta.confianza < ConfiguracionSistema.actual().umbral_confianza_revision,  # CC-04
        "extra": extra,
        "extra_legible": ", ".join(
            f"{k.replace('_', ' ')}: {v}" for k, v in extra.items()
            if k not in ("entidad_sugerida_id", "entidad_sugerida_nombre")
        ),
    }


def _ultimo_resumen_analisis(record):
    """Advertencias y forma documental sugerida por el motor en su última
    corrida sobre este documento (regla 1 y prompt de forma documental)."""
    evento = (
        EventoRiC.objects.filter(
            instanciacion__record_resource=record, tipo=EventoRiC.Tipo.PROPUESTA_IA,
            detalle__resumen_analisis=True,
        ).order_by("-id").first()
    )
    return evento.detalle if evento else {}


def _texto_resaltado(texto, fichas):
    """RF-M3-02: el fragmento exacto del que salió cada propuesta, marcado
    en el texto original (sin solapar dos marcas)."""
    tramos = []
    texto_minusculas = texto.lower()
    for f in fichas:
        p = f["propuesta"]
        if not p.evidencia or not p.evidencia.fragmento:
            continue
        fragmento = p.evidencia.fragmento
        inicio = texto.find(fragmento)
        if inicio < 0:
            inicio = texto_minusculas.find(fragmento.lower())
        if inicio < 0:
            continue
        tramos.append((inicio, inicio + len(fragmento), p.pk, f["clase"]))
    tramos.sort()
    partes, cursor = [], 0
    for inicio, fin, pk, clase in tramos:
        if inicio < cursor:
            continue
        partes.append(html.escape(texto[cursor:inicio]))
        partes.append(f'<mark id="ev-{pk}" class="ev clase-{clase}" data-propuesta="{pk}">{html.escape(texto[inicio:fin])}</mark>')
        cursor = fin
    partes.append(html.escape(texto[cursor:]))
    return mark_safe("".join(partes))


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def analisis_lista(request):
    return render(request, "ric/analisis_lista.html", {"filas": flujo.documentos_con_estado()})


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def analisis(request, pk):
    record = get_object_or_404(Record, pk=pk)
    instanciacion = flujo.instanciacion_principal(record)
    texto = instanciacion.texto_extraido if instanciacion else ""
    # CC-04: primero las de menor confianza, que son las que más revisión necesitan.
    propuestas = list(
        flujo.propuestas_de(record).select_related("evidencia", "validado_por").order_by("confianza", "fecha_creacion")
    )
    fichas = [_ficha(p) for p in propuestas if p.estado == PropuestaRiC.Estado.PENDIENTE]
    resumen = _ultimo_resumen_analisis(record)
    decididas = [p for p in propuestas if p.estado != PropuestaRiC.Estado.PENDIENTE]

    grupos = []
    for slug, nombre, _ids in CLASES:
        del_grupo = [f for f in fichas if f["clase"] == slug]
        if del_grupo:
            grupos.append({"slug": slug, "nombre": nombre, "fichas": del_grupo})

    rechazada = rechazada_entidad = None
    if request.GET.get("rechazada", "").isdigit():
        rechazada = flujo.relaciones_de(record, solo_validadas=False).filter(pk=request.GET["rechazada"]).first()
        if rechazada is not None:
            rechazada_entidad = flujo.otro_lado(rechazada, record)

    return render(request, "ric/analisis.html", {
        **_contexto_documento(record, 3),
        "instanciacion": instanciacion,
        "texto_html": _texto_resaltado(texto, fichas),
        "grupos": grupos,
        "pendientes_total": sum(len(g["fichas"]) for g in grupos),
        "clases": [(slug, nombre) for slug, nombre, _ in CLASES],
        "decididas": decididas,
        "total_pendientes": len(fichas),
        "total_propuestas": len(propuestas),
        "rechazada": rechazada,
        "rechazada_entidad": rechazada_entidad,
        "formas": FormaDocumental.objects.all(),
        "relaciones_validadas": flujo.relaciones_de(record).count(),
        "puede_decidir": roles.puede(request.user, roles.ARCHIVISTA),
        "advertencias": resumen.get("advertencias") or [],
        "forma_sugerida": resumen.get("forma_documental"),
        "clases_faltantes": flujo.clases_faltantes(record) if propuestas or flujo.relaciones_de(record).exists() else [],
        "umbral_confianza": ConfiguracionSistema.actual().umbral_confianza_revision,
    })


def _informar_analisis(request, record, resultado):
    if resultado.get("sin_proveedor"):
        messages.info(request, "No hay un proveedor de IA activo: actívelo en Administración → Proveedores de IA.")
    elif resultado.get("error"):
        messages.error(request, f"El motor de análisis no respondió: {resultado['error']}")
    elif resultado["propuestas"] == 0:
        messages.info(request, f"El motor de análisis no propuso nada nuevo para «{record}».")
    else:
        aviso = ""
        if resultado.get("rechazadas_por_reglas"):
            aviso = f" ({resultado['rechazadas_por_reglas']} descartada(s) por el motor de reglas RiC-CM, quedan en el historial)"
        messages.success(request, f"{resultado['propuestas']} propuesta(s) nueva(s) de entidades para «{record}»{aviso}.")


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def analisis_generar(request, pk):
    record = get_object_or_404(Record, pk=pk)
    _informar_analisis(request, record, enviar_al_motor(record, request.user))
    return redirect("analisis", pk=pk)


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def analisis_decidir(request, pk):
    """RF-M3-04 / RF-M6-02: aceptar (con el nombre corregido si hace
    falta), vincular a una entrada de vocabulario ya existente, o
    rechazar con motivo — cada ficha por separado, nunca en bloque."""
    propuesta = get_object_or_404(PropuestaRiC, pk=pk)
    record_pk = propuesta.origen_object_id
    accion = request.POST.get("accion")
    motivo = request.POST.get("motivo", "").strip()
    nombre_corregido = request.POST.get("entidad_nombre_final", "").strip()

    try:
        if accion == "aceptar":
            propuesta.validar(request.user, aceptar=True, motivo=motivo, entidad_nombre_final=nombre_corregido or None)
            if nombre_corregido and nombre_corregido != propuesta.entidad_nombre:
                messages.success(request, f'Aceptada como "{nombre_corregido}" (corregido de "{propuesta.entidad_nombre}").')
            else:
                messages.success(request, f'"{propuesta.entidad_nombre}" aceptada y agregada al grafo RiC.')
        elif accion == "vincular":
            modelo = tipos.ric_id_a_modelo(propuesta.entidad_tipo)
            entidad_existente = get_object_or_404(modelo, pk=request.POST.get("entidad_existente"))
            propuesta.validar(request.user, aceptar=True, entidad_existente=entidad_existente, motivo=motivo)
            messages.success(request, f'Vinculada a la entrada existente "{entidad_existente}" — sin crear un duplicado.')
        elif accion == "rechazar":
            if not motivo:
                messages.error(request, "Indique el motivo del rechazo antes de rechazar la propuesta (RF-M6-03).")
                return redirect("analisis", pk=record_pk)
            propuesta.validar(request.user, aceptar=False, motivo=motivo)
            messages.info(request, f'"{propuesta.entidad_nombre}" rechazada: {motivo}')
        else:
            messages.error(request, "Acción no reconocida.")
    except (ValueError, PermissionError) as e:
        messages.error(request, str(e))
    return redirect("analisis", pk=record_pk)


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def analisis_forma(request, pk):
    """Forma documental (RiC-A17) del documento, como entrada controlada del
    vocabulario de M5 — se elige una existente o se escribe una nueva."""
    record = get_object_or_404(Record, pk=pk)
    nombre = request.POST.get("forma_nombre", "").strip()
    forma_id = request.POST.get("forma_id", "").strip()
    forma = None
    if forma_id:
        forma = get_object_or_404(FormaDocumental, pk=forma_id)
    elif nombre:
        forma, creada = FormaDocumental.objects.get_or_create(nombre=nombre, defaults={"creado_por": request.user})
    if forma is None:
        messages.error(request, "Elija una forma documental o escriba una nueva.")
        return redirect("analisis", pk=pk)
    record.forma_documental = forma
    record.tipo_forma_documental = forma.nombre
    record.modificado_por = request.user
    record.save()
    messages.success(request, f"Forma documental: {forma.nombre}.")
    return redirect("analisis", pk=pk)


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def analisis_grafo(request, pk):
    record = get_object_or_404(Record, pk=pk)
    return render(request, "ric/analisis_grafo.html", {
        **_contexto_documento(record, 4),
        "categorias": [(slug, nombre, color) for slug, (nombre, color) in grafo.CATEGORIAS.items()],
        "puede_editar": roles.puede(request.user, roles.ARCHIVISTA),
        "total_pendientes": flujo.pendientes_de(record).count(),
    })


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def analisis_grafo_datos(request, pk):
    record = get_object_or_404(Record, pk=pk)
    return JsonResponse(grafo.subgrafo_documento(record))


@roles.requiere_rol(roles.ARCHIVISTA)
@require_POST
def analisis_relacion(request, pk, relacion_pk):
    """RF-M4-03: corregir el tipo de una relación desde la lista controlada;
    RF-M4-04: retirar una relación mal propuesta — se marca rechazada (queda
    en el historial, M7) y las entidades que conectaba no se tocan."""
    record = get_object_or_404(Record, pk=pk)
    relacion = get_object_or_404(flujo.relaciones_de(record, solo_validadas=False), pk=relacion_pk)
    entidad = flujo.otro_lado(relacion, record)
    accion = request.POST.get("accion")
    instanciacion = flujo.instanciacion_principal(record)

    if accion == "cambiar_tipo":
        nuevo = request.POST.get("relacion_id", "").strip()
        anterior = relacion.relacion_id
        try:
            reglas.validar_relacion(nuevo, relacion.origen, relacion.destino)
        except reglas.RelacionInvalida as e:
            messages.error(request, str(e))
            return redirect("analisis_grafo", pk=pk)
        relacion.relacion_id = nuevo
        relacion.estado = RelacionRiC.Estado.MODIFICADA
        relacion.validado_por = request.user
        relacion.fecha_validacion = timezone.now()
        relacion.save()
        registrar_evento(
            instanciacion, EventoRiC.Tipo.RELACION_EDITADA, agente=request.user,
            detalle={"relacion": relacion.pk, "de": anterior, "a": nuevo, "entidad": str(entidad)},
        )
        messages.success(request, f"Tipo de relación corregido: {reglas.info_relacion(nuevo)['nombre']}.")
    elif accion == "eliminar":
        motivo = request.POST.get("motivo", "").strip() or "Retirada en el modelado de relaciones."
        relacion.estado = RelacionRiC.Estado.RECHAZADA
        relacion.motivo_decision = motivo
        relacion.validado_por = request.user
        relacion.fecha_validacion = timezone.now()
        relacion.save()
        registrar_evento(
            instanciacion, EventoRiC.Tipo.RELACION_EDITADA, agente=request.user,
            detalle={"relacion": relacion.pk, "retirada": True, "motivo": motivo, "entidad": str(entidad)},
        )
        messages.info(request, f"Relación retirada del grafo; la entidad «{entidad}» se conserva en los vocabularios.")
    else:
        messages.error(request, "Acción no reconocida.")
    return redirect("analisis_grafo", pk=pk)


# ---------------------------------------------------------------------------
# M6 · Revisión archivística
# ---------------------------------------------------------------------------

def _fichas_revision(record):
    fichas = []
    matriz = reglas.cargar_matriz()["relaciones"]
    for rel in flujo.relaciones_de(record, solo_validadas=False).order_by("fecha_creacion"):
        propuesta = rel.evidencia.propuestas.first() if rel.evidencia else None
        fichas.append({
            "relacion": rel,
            "entidad": flujo.otro_lado(rel, record),
            "nombre_relacion": matriz.get(rel.relacion_id, {}).get("nombre", rel.relacion_id),
            "propuesta": propuesta,
            "categoria": grafo.CATEGORIAS[grafo.categoria_relacion(rel.relacion_id)][0],
            "validada": rel.estado in flujo.ESTADOS_VALIDADOS,
        })
    return fichas


def _tiene_procedencia(record):
    return any(grafo.categoria_relacion(r.relacion_id) == "procedencia" for r in flujo.relaciones_de(record))


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def revision_lista(request):
    orden = {flujo.EN_REVISION: 0, flujo.EN_ANALISIS: 1, flujo.SIN_ANALIZAR: 2, flujo.SIN_TEXTO: 3, flujo.PUBLICADO: 4}
    filas = sorted(flujo.documentos_con_estado(), key=lambda f: orden[f["estado"]])
    return render(request, "ric/revision_lista.html", {"filas": filas})


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def revision(request, pk):
    record = get_object_or_404(Record, pk=pk)
    fichas = _fichas_revision(record)
    return render(request, "ric/revision.html", {
        **_contexto_documento(record, 5),
        "fichas": [f for f in fichas if f["validada"]],
        "rechazadas": [f for f in fichas if not f["validada"]],
        "pendientes": list(flujo.pendientes_de(record)),
        "puede_aprobar": roles.puede(request.user, roles.ARCHIVISTA, roles.REVISOR),
        "tiene_procedencia": _tiene_procedencia(record),
        "umbral_confianza": ConfiguracionSistema.actual().umbral_confianza_revision,
        "clases_faltantes": flujo.clases_faltantes(record),
    })


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
@require_POST
def revision_aprobar(request, pk):
    """RF-M6-04: nada pasa al catálogo mientras haya elementos por decidir."""
    record = get_object_or_404(Record, pk=pk)
    pendientes = flujo.pendientes_de(record).count()
    if pendientes:
        messages.error(request, f"No se puede publicar: quedan {pendientes} elemento(s) pendientes de decisión en el motor de análisis.")
        return redirect("revision", pk=pk)
    # CC-03 (verificado en el servidor, no solo en pantalla): sin al menos
    # una relación de procedencia confirmada, el documento no se publica.
    if not _tiene_procedencia(record):
        messages.error(
            request,
            "No se puede publicar (CC-03): el documento necesita al menos una relación de procedencia "
            "confirmada — quién lo produjo o firmó (por ejemplo R027 \"has creator\").",
        )
        return redirect("revision", pk=pk)
    record.publicado = True
    record.fecha_publicacion = timezone.now()
    record.publicado_por = request.user
    record.modificado_por = request.user
    record.save()
    registrar_evento(
        flujo.instanciacion_principal(record), EventoRiC.Tipo.PUBLICACION, agente=request.user,
        detalle={"record": record.pk, "relaciones": flujo.relaciones_de(record).count()},
    )
    messages.success(request, f"«{record}» aprobado y publicado: ya es visible en el catálogo.")
    return redirect("catalogo")


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
@require_POST
def revision_rechazar(request, pk, relacion_pk):
    """Ruta alterna de rechazo: la ficha vuelve al motor de análisis con su
    motivo (RF-M6-03) y el documento sale del catálogo si estaba publicado."""
    record = get_object_or_404(Record, pk=pk)
    relacion = get_object_or_404(flujo.relaciones_de(record, solo_validadas=False), pk=relacion_pk)
    entidad = flujo.otro_lado(relacion, record)
    motivo = request.POST.get("motivo", "").strip()
    if not motivo:
        messages.error(request, "Escriba el motivo del rechazo antes de confirmar (RF-M6-03).")
        return redirect("revision", pk=pk)
    relacion.estado = RelacionRiC.Estado.RECHAZADA
    relacion.motivo_decision = motivo
    relacion.validado_por = request.user
    relacion.fecha_validacion = timezone.now()
    relacion.save()
    estaba_publicado = record.publicado
    if estaba_publicado:
        record.publicado = False
        record.modificado_por = request.user
        record.save()
    registrar_evento(
        flujo.instanciacion_principal(record), EventoRiC.Tipo.VALIDACION, agente=request.user,
        detalle={"relacion": relacion.pk, "rechazada_en_revision": True, "motivo": motivo,
                 "retirado_del_catalogo": estaba_publicado},
    )
    messages.info(request, f"Rechazada: «{entidad}» ({motivo}). El documento vuelve al motor de análisis para una nueva propuesta.")
    return redirect(f"/analisis/{pk}/?rechazada={relacion.pk}")


# ---------------------------------------------------------------------------
# M7 · Trazabilidad y auditoría
# ---------------------------------------------------------------------------

@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def historial_lista(request):
    return render(request, "ric/historial_lista.html", {"filas": flujo.documentos_con_estado()})


@roles.requiere_rol(roles.ARCHIVISTA, roles.REVISOR)
def historial(request, pk):
    record = get_object_or_404(Record, pk=pk)
    eventos = list(
        EventoRiC.objects.filter(instanciacion__record_resource=record)
        .select_related("instanciacion").order_by("fecha", "id")
    )
    momento, reconstruccion = None, None
    if request.GET.get("momento"):
        momento = parse_datetime(request.GET["momento"])
        if momento is not None:
            if timezone.is_naive(momento):
                momento = timezone.make_aware(momento)
            reconstruccion = flujo.descripcion_en(record, momento)
    matriz = reglas.cargar_matriz()["relaciones"]
    if reconstruccion is not None:
        for fila in reconstruccion:
            fila["nombre_relacion"] = matriz.get(fila["relacion_id"], {}).get("nombre", fila["relacion_id"])
    return render(request, "ric/historial.html", {
        **_contexto_documento(record),
        "eventos": eventos,
        "momento": momento,
        "reconstruccion": reconstruccion,
        "cadena_intacta": all(verificar_cadena(i)[0] for i in record.instanciaciones.all()),
    })
