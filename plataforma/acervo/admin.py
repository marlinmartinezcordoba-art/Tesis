from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Documento, EventoPreservacion


class EventoInline(admin.TabularInline):
    model = EventoPreservacion
    extra = 0
    can_delete = False
    readonly_fields = ("fecha", "tipo", "agente", "detalle", "exitoso", "hash_evento")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "codigo_referencia", "nivel_descripcion", "fecha_ingreso", "informe")
    list_filter = ("nivel_descripcion",)
    search_fields = ("titulo", "codigo_referencia", "productor", "texto_extraido")
    readonly_fields = ("sha256", "formato", "tamano_bytes", "fecha_ingreso")
    inlines = [EventoInline]
    actions = ["verificar_fijeza"]

    def get_readonly_fields(self, request, obj=None):
        # El archivo no se puede reemplazar después del ingreso.
        return self.readonly_fields + (("archivo",) if obj else ())

    @admin.display(description="Verificación")
    def informe(self, obj):
        return format_html('<a href="{}">Ver informe</a>', reverse("informe", args=[obj.pk]))

    @admin.action(description="Verificar fijeza (hash) de los documentos seleccionados")
    def verificar_fijeza(self, request, queryset):
        fallidos = [d for d in queryset if not d.verificar_fijeza(agente=request.user)]
        if fallidos:
            self.message_user(request, f"Fijeza fallida en: {', '.join(map(str, fallidos))}", level="error")
        else:
            self.message_user(request, f"{queryset.count()} documento(s) íntegro(s).")


@admin.register(EventoPreservacion)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "documento", "tipo", "agente", "exitoso")
    list_filter = ("tipo", "exitoso")

    # La bitácora es de solo lectura: nadie la edita ni la borra desde la interfaz.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
