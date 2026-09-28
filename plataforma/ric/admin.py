from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html

from .auditoria import MuestraRiC
from .models import (
    Activity,
    ComponenteEstructural,
    CorporateBody,
    Date,
    Evidencia,
    Event,
    EventoRiC,
    Family,
    Group,
    Instantiation,
    Mandate,
    Mechanism,
    PaginaTexto,
    Person,
    Place,
    Position,
    PropuestaRiC,
    PropuestaSegmentacion,
    Record,
    RecordPart,
    RecordSet,
    RelacionRiC,
    Rule,
    VersionRiC,
)

class VerGrafoAdminMixin:
    """T052: un enlace directo, desde cualquier admin de entidad, al grafo
    de conocimiento navegable (Cytoscape.js) centrado en esa fila."""

    @admin.display(description="Grafo")
    def ver_grafo(self, obj):
        return format_html(
            '<a href="{}">grafo ↗</a>',
            reverse("ric_grafo", args=[type(obj).__name__.lower(), obj.pk]),
        )


class EntidadRicAdmin(VerGrafoAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "ver_grafo")


class FusionarAdminMixin:
    """F08: "fusionar" dos entidades que resultaron ser la misma cosa —
    mueve sus relaciones y borra la duplicada (ver `ric.fusion`). Acción de
    dos pasos, igual que "delete_selected" de Django: primero muestra una
    página para elegir cuál de las seleccionadas sobrevive, luego fusiona."""

    actions = ["fusionar_en_otra"]

    @admin.action(description="Fusionar en otra entidad seleccionada (son la misma cosa)")
    def fusionar_en_otra(self, request, queryset):
        from .fusion import ErrorDeFusion, fusionar_entidades

        if request.POST.get("confirmar_fusion"):
            try:
                superviviente = queryset.get(pk=request.POST.get("superviviente"))
            except (queryset.model.DoesNotExist, ValueError, TypeError):
                self.message_user(request, "Elija cuál de las entidades seleccionadas sobrevive.", level="error")
                return None
            duplicadas = list(queryset.exclude(pk=superviviente.pk))
            relaciones = propuestas = 0
            for duplicada in duplicadas:
                try:
                    resultado = fusionar_entidades(duplicada, superviviente, usuario=request.user)
                except ErrorDeFusion as e:
                    self.message_user(request, str(e), level="error")
                    return None
                relaciones += resultado["relaciones_movidas"]
                propuestas += resultado["propuestas_movidas"]
            self.message_user(
                request,
                f"Fusionada(s) {len(duplicadas)} entidad(es) en \"{superviviente}\": "
                f"{relaciones} relación(es) y {propuestas} propuesta(s) movidas.",
            )
            return None

        if queryset.count() < 2:
            self.message_user(request, "Seleccione al menos dos entidades del mismo tipo para fusionar.", level="warning")
            return None

        return render(request, "admin/ric/fusionar_confirmacion.html", {
            "entidades": queryset,
            "opts": self.model._meta,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
        })


def _ingerir(instanciacion, agente):
    from .ingesta import ingerir

    ingerir(instanciacion, agente)


# RecordSet y RecordPart quedan fuera de "fusionar": otros modelos los
# referencian con una FK directa (jerarquía documental), no solo con
# RelacionRiC — fusionarlos arrastraría esas decisiones (ver ric/fusion.py).
ENTIDADES_SIN_FUSION = [RecordSet, RecordPart]
ENTIDADES_FUSIONABLES = [
    Person, Group, Family, CorporateBody, Position, Mechanism,
    Event, Activity, Rule, Mandate, Date, Place,
]

for modelo in ENTIDADES_SIN_FUSION:
    admin.site.register(modelo, EntidadRicAdmin)

for modelo in ENTIDADES_FUSIONABLES:
    admin.site.register(modelo, type(f"{modelo.__name__}Admin", (FusionarAdminMixin, EntidadRicAdmin), {}))


class InstantiationInline(admin.TabularInline):
    """F01: carga masiva — varios archivos (instanciaciones) de una vez sobre
    el mismo Record, cada uno hash+OCR automáticos al guardar (ver save_formset)."""

    model = Instantiation
    fk_name = "record_resource"
    extra = 1
    fields = ("nombre", "archivo", "sha256", "tipo_soporte")
    readonly_fields = ("sha256",)


@admin.register(Record)
class RecordAdmin(VerGrafoAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "record_set", "tipo_forma_documental", "ver_grafo")
    actions = ["proponer_relaciones_gemini", "proponer_relaciones_claude", "proponer_relaciones_local"]
    inlines = [InstantiationInline]

    def save_formset(self, request, form, formset, change):
        instancias = formset.save(commit=False)
        for eliminada in formset.deleted_objects:
            eliminada.delete()
        for instanciacion in instancias:
            es_nueva = instanciacion.pk is None
            instanciacion.save()
            if es_nueva:
                _ingerir(instanciacion, agente=request.user)
        formset.save_m2m()

    def changelist_view(self, request, extra_context=None):
        messages.info(
            request,
            format_html(
                'Para ingerir documentos (F01): "Añadir registro (Record)" y suba los archivos '
                'en "Instanciaciones" dentro del mismo formulario — el hash, el OCR (F02) y la '
                'estructura (F03) se calculan solos. '
                'Buscar en el texto extraído y en los nombres de entidades: <a href="{}">búsqueda</a>. '
                'Consultar el grafo validado con SPARQL: <a href="{}">consola SPARQL</a>. '
                'Métricas del sistema: <a href="{}">laboratorio de evaluación</a>. '
                '<a href="{}">← Volver al panel de inicio</a>.',
                reverse("ric_busqueda"), reverse("ric_sparql"), reverse("ric_evaluacion"), reverse("ric_inicio"),
            ),
        )
        return super().changelist_view(request, extra_context)

    def _generar(self, request, queryset, proveedor_cls, error_cls, etiqueta):
        from .proveedores import generar_propuestas

        for record in queryset:
            try:
                propuestas = generar_propuestas(record, proveedor_cls())
            except error_cls as e:
                self.message_user(request, f"{record}: {e}", level="warning")
                continue
            if not propuestas:
                self.message_user(request, f"{record}: {etiqueta} no propuso nada.")
                continue
            rechazadas = sum(1 for p in propuestas if p.estado == "rechazada")
            aviso = f" ({rechazadas} rechazada(s) automáticamente por el motor de reglas)" if rechazadas else ""
            self.message_user(
                request, f"{record}: {len(propuestas)} propuesta(s) de {etiqueta} pendientes de validación{aviso}."
            )

    @admin.action(description="Proponer relaciones (IA en la nube, Gemini)")
    def proponer_relaciones_gemini(self, request, queryset):
        from .proveedor_gemini import ErrorProveedorIA, ProveedorGemini

        self._generar(request, queryset, ProveedorGemini, ErrorProveedorIA, "Gemini")

    @admin.action(description="Proponer relaciones (IA en la nube, Claude — alternativa)")
    def proponer_relaciones_claude(self, request, queryset):
        from .proveedor_claude import ErrorProveedorIA, ProveedorClaude

        self._generar(request, queryset, ProveedorClaude, ErrorProveedorIA, "Claude")

    @admin.action(description="Proponer relaciones (IA local, spaCy)")
    def proponer_relaciones_local(self, request, queryset):
        from .proveedor_local import ErrorProveedorIA, ProveedorLocal

        self._generar(request, queryset, ProveedorLocal, ErrorProveedorIA, "la IA local")


class PaginaTextoInline(admin.TabularInline):
    model = PaginaTexto
    extra = 0
    fields = ("numero", "texto", "uso_ocr", "confianza_ocr", "coordenadas")
    readonly_fields = ("numero", "texto", "uso_ocr", "confianza_ocr", "coordenadas")
    can_delete = False

    @admin.display(description="Coordenadas (F02)")
    def coordenadas(self, obj):
        if not obj.cajas_ocr:
            return "sin coordenadas (sin OCR)"
        return f"{len(obj.cajas_ocr)} palabra(s) georreferenciada(s)"

    def has_add_permission(self, request, obj=None):
        return False


class ComponenteEstructuralInline(admin.TabularInline):
    model = ComponenteEstructural
    extra = 0
    fields = ("pagina", "orden", "tipo", "etiqueta", "texto", "confianza", "regla")
    readonly_fields = ("pagina", "orden", "tipo", "etiqueta", "texto", "confianza", "regla")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Instantiation)
class InstantiationAdmin(admin.ModelAdmin):
    list_display = ("nombre", "record_resource", "sha256", "fecha_registro")
    readonly_fields = ("sha256", "ver_original")
    inlines = [PaginaTextoInline, ComponenteEstructuralInline]

    actions = ["extraer_texto", "detectar_estructura_accion"]

    @admin.display(description="Archivo original")
    def ver_original(self, obj):
        # F16: nunca el enlace directo a /media/ — en producción (DEBUG=0)
        # esa URL no existe; esta pasa siempre por servir_archivo (con sesión).
        if not obj.pk:
            return "Guarde primero para poder verlo."
        return format_html('<a href="{}" target="_blank">abrir ↗</a>', reverse("ric_archivo", args=[obj.pk]))

    def changelist_view(self, request, extra_context=None):
        messages.info(
            request,
            "Para subir (ingerir) un documento nuevo, use \"Añadir\" arriba a la derecha. "
            "Al guardar, se ejecutan solos: F01 (hash del original), F02 (OCR por página), "
            "F03 (estructura: encabezado, título, campos, fechas, firmas...) y F04 (si detecta "
            "más de un documento en el mismo archivo, queda como propuesta de segmentación).",
        )
        return super().changelist_view(request, extra_context)

    def save_model(self, request, obj, form, change):
        es_nueva = obj.pk is None
        super().save_model(request, obj, form, change)
        if es_nueva:
            _ingerir(obj, agente=request.user)

    @admin.action(description="Extraer texto (OCR por página)")
    def extraer_texto(self, request, queryset):
        from .ingesta import ingerir

        for inst in queryset:
            resultado = ingerir(inst, agente=request.user)
            if resultado["formato_no_soportado"]:
                self.message_user(request, f"{inst}: formato no soportado para extraer texto.", level="warning")
                continue
            aviso = f" (confianza OCR {resultado['confianza_ocr']}%)" if resultado["confianza_ocr"] is not None else ""
            self.message_user(
                request,
                f"{inst}: {resultado['paginas']} página(s), {resultado['caracteres']} caracteres{aviso}, "
                f"{resultado['componentes']} componente(s) estructural(es).",
            )

    @admin.action(description="Detectar estructura documental (F03)")
    def detectar_estructura_accion(self, request, queryset):
        from .estructura import detectar_y_guardar_estructura

        for inst in queryset:
            componentes = detectar_y_guardar_estructura(inst)
            self.message_user(request, f"{inst}: {len(componentes)} componente(s) estructural(es) detectado(s).")


@admin.register(Evidencia)
class EvidenciaAdmin(admin.ModelAdmin):
    list_display = ("instanciacion", "pagina", "verificada")
    list_filter = ("verificada",)
    search_fields = ("fragmento",)


@admin.register(PropuestaRiC)
class PropuestaRiCAdmin(admin.ModelAdmin):
    list_display = ("relacion_id", "entidad_tipo", "entidad_nombre", "origen", "proveedor", "confianza", "estado")
    list_filter = ("estado", "proveedor", "relacion_id")
    readonly_fields = [f.name for f in PropuestaRiC._meta.fields]

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        messages.info(
            request,
            format_html(
                'Para validar viendo a la vez el documento, la evidencia y la propuesta: '
                '<a href="{}">bandeja de validación</a>.',
                reverse("ric_bandeja"),
            ),
        )
        return super().changelist_view(request, extra_context)

    actions = ["aceptar"]

    @admin.action(description="Aceptar las propuestas seleccionadas tal como fueron generadas")
    def aceptar(self, request, queryset):
        aceptadas, fallidas = 0, 0
        for p in queryset.filter(estado=PropuestaRiC.Estado.PENDIENTE):
            try:
                p.validar(request.user, aceptar=True)
                aceptadas += 1
            except Exception as e:
                fallidas += 1
                self.message_user(request, f"{p}: {e}", level="warning")
        self.message_user(request, f"{aceptadas} propuesta(s) aceptada(s), registradas en el grafo RiC.")


@admin.register(PropuestaSegmentacion)
class PropuestaSegmentacionAdmin(admin.ModelAdmin):
    """F04: revisar y validar las propuestas de segmentación — nunca se
    separa un archivo automáticamente, solo al aceptar aquí."""

    list_display = ("instanciacion", "pagina_inicio", "pagina_fin", "titulo_detectado", "confianza", "estado")
    list_filter = ("estado",)
    readonly_fields = [f.name for f in PropuestaSegmentacion._meta.fields]

    def has_add_permission(self, request):
        return False

    actions = ["aceptar", "rechazar"]

    @admin.action(description="Aceptar: crear el documento segmentado")
    def aceptar(self, request, queryset):
        aceptadas, fallidas = 0, 0
        for p in queryset.filter(estado=PropuestaSegmentacion.Estado.PENDIENTE):
            try:
                p.validar(request.user, aceptar=True)
                aceptadas += 1
            except Exception as e:
                fallidas += 1
                self.message_user(request, f"{p}: {e}", level="warning")
        self.message_user(request, f"{aceptadas} segmentación(es) aceptada(s), documento(s) nuevo(s) creado(s).")

    @admin.action(description="Rechazar: el archivo sigue siendo un solo documento")
    def rechazar(self, request, queryset):
        rechazadas = 0
        for p in queryset.filter(estado=PropuestaSegmentacion.Estado.PENDIENTE):
            p.validar(request.user, aceptar=False, motivo="Rechazada desde el panel de administración.")
            rechazadas += 1
        self.message_user(request, f"{rechazadas} segmentación(es) rechazada(s).")


@admin.register(EventoRiC)
class EventoRiCAdmin(admin.ModelAdmin):
    list_display = ("fecha", "instanciacion", "tipo", "agente", "exitoso")
    list_filter = ("tipo", "exitoso")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RelacionRiC)
class RelacionRiCAdmin(admin.ModelAdmin):
    list_display = ("relacion_id", "origen", "destino", "estado", "certeza", "fecha_creacion")
    list_filter = ("relacion_id", "estado", "certeza")
    readonly_fields = ("fecha_creacion",)

    actions = ["aceptar"]

    @admin.action(description="Aceptar las relaciones seleccionadas tal como fueron propuestas")
    def aceptar(self, request, queryset):
        for r in queryset.filter(estado=RelacionRiC.Estado.PENDIENTE):
            r.estado = RelacionRiC.Estado.ACEPTADA
            r.validado_por = request.user
            from django.utils import timezone

            r.fecha_validacion = timezone.now()
            r.save()
        self.message_user(request, "Relaciones aceptadas.")


@admin.register(VersionRiC)
class VersionRiCAdmin(admin.ModelAdmin):
    """F07 (versionado, RF-016): historial de solo lectura, una fila por
    cada vez que una entidad o relación existente se sobrescribió."""

    list_display = ("fecha", "content_type", "object_id")
    list_filter = ("content_type",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RevisionMuestraRiCForm(forms.ModelForm):
    class Meta:
        model = MuestraRiC
        fields = ("resultado", "observacion")

    def clean(self):
        datos = super().clean()
        original = MuestraRiC.objects.get(pk=self.instance.pk)
        try:
            original.validar_resultado(datos.get("resultado"), datos.get("observacion", ""))
        except ValueError as e:
            raise forms.ValidationError(str(e))
        return datos


@admin.register(MuestraRiC)
class MuestraRiCAdmin(admin.ModelAdmin):
    """Auditoría periódica por muestreo de relaciones RiC (T071).

    Las muestras se seleccionan con el comando `auditoria_muestra_ric`, no
    desde aquí: es una tarea periódica de la entidad, no una acción sobre
    un documento puntual.
    """

    form = RevisionMuestraRiCForm
    list_display = ("relacion", "fecha_seleccion", "resultado", "revisado_por")
    list_filter = ("resultado", "relacion__relacion_id")

    def changelist_view(self, request, extra_context=None):
        messages.info(
            request,
            format_html(
                'Exactitud calculada (M03, T071): <a href="{}">ver laboratorio de evaluación</a>.',
                reverse("ric_evaluacion"),
            ),
        )
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        campos = ["relacion", "fecha_seleccion", "revisado_por", "fecha_revision"]
        if obj and obj.resultado != MuestraRiC.Resultado.PENDIENTE:
            campos += ["resultado", "observacion"]
        return campos

    def has_change_permission(self, request, obj=None):
        if obj and obj.resultado != MuestraRiC.Resultado.PENDIENTE:
            return False
        return super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        resultado, observacion = obj.resultado, obj.observacion
        obj.refresh_from_db()
        obj.revisar(request.user, resultado, observacion)
