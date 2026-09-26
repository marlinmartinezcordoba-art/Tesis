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
    RecordSet, Record, RecordPart, Instantiation,
    Person, Group, Family, CorporateBody, Position, Mechanism,
    Event, Activity, Rule, Mandate, Date, Place,
]
for modelo in ENTIDADES:
    admin.site.register(modelo)


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
