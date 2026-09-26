from django import forms
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from .auditoria import MuestraRiC
from .models import (
    Activity,
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
    Record,
    RecordPart,
    RecordSet,
    RelacionRiC,
    Rule,
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


ENTIDADES = [
    RecordSet, RecordPart,
    Person, Group, Family, CorporateBody, Position, Mechanism,
    Event, Activity, Rule, Mandate, Date, Place,
]
for modelo in ENTIDADES:
    admin.site.register(modelo, EntidadRicAdmin)


@admin.register(Record)
class RecordAdmin(VerGrafoAdminMixin, admin.ModelAdmin):
    list_display = ("nombre", "record_set", "tipo_forma_documental", "ver_grafo")
    actions = ["proponer_relaciones_nube", "proponer_relaciones_local"]

    def changelist_view(self, request, extra_context=None):
        messages.info(
            request,
            format_html(
                'Buscar en el texto extraído y en los nombres de entidades: <a href="{}">búsqueda</a>. '
                'Consultar el grafo validado con SPARQL: <a href="{}">consola SPARQL</a>. '
                'Métricas del sistema: <a href="{}">laboratorio de evaluación</a>.',
                reverse("ric_busqueda"), reverse("ric_sparql"), reverse("ric_evaluacion"),
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

    @admin.action(description="Proponer relaciones (IA en la nube, Claude)")
    def proponer_relaciones_nube(self, request, queryset):
        from .proveedor_claude import ErrorProveedorIA, ProveedorClaude

        self._generar(request, queryset, ProveedorClaude, ErrorProveedorIA, "la IA en la nube")

    @admin.action(description="Proponer relaciones (IA local, spaCy)")
    def proponer_relaciones_local(self, request, queryset):
        from .proveedor_local import ErrorProveedorIA, ProveedorLocal

        self._generar(request, queryset, ProveedorLocal, ErrorProveedorIA, "la IA local")


class PaginaTextoInline(admin.TabularInline):
    model = PaginaTexto
    extra = 0
    readonly_fields = ("numero", "texto", "uso_ocr", "confianza_ocr")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Instantiation)
class InstantiationAdmin(admin.ModelAdmin):
    list_display = ("nombre", "record_resource", "sha256", "fecha_registro")
    readonly_fields = ("sha256",)
    inlines = [PaginaTextoInline]

    actions = ["extraer_texto"]

    @admin.action(description="Extraer texto (OCR por página)")
    def extraer_texto(self, request, queryset):
        from .extraccion import FormatoNoSoportado, extraer_texto_de_instanciacion

        for inst in queryset:
            try:
                _, detalle = extraer_texto_de_instanciacion(inst, agente=request.user)
            except FormatoNoSoportado as e:
                self.message_user(request, f"{inst}: {e}", level="warning")
                continue
            confianza = detalle["confianza_ocr"]
            aviso = f" (confianza OCR {confianza}%)" if confianza is not None else ""
            self.message_user(request, f"{inst}: {detalle['paginas']} página(s), {detalle['caracteres']} caracteres{aviso}.")


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
