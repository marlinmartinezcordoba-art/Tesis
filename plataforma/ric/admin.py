from django.contrib import admin

from .models import (
    Activity,
    CorporateBody,
    Date,
    Evidencia,
    Event,
    Family,
    Group,
    Instantiation,
    Mandate,
    Mechanism,
    PaginaTexto,
    Person,
    Place,
    Position,
    Record,
    RecordPart,
    RecordSet,
    RelacionRiC,
    Rule,
)

ENTIDADES = [
    RecordSet, Record, RecordPart,
    Person, Group, Family, CorporateBody, Position, Mechanism,
    Event, Activity, Rule, Mandate, Date, Place,
]
for modelo in ENTIDADES:
    admin.site.register(modelo)


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
                _, detalle = extraer_texto_de_instanciacion(inst)
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
