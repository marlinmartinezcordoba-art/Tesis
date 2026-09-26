from django import forms
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from .auditoria import MuestraAuditoria
from .models import SugerenciaIA


@admin.register(SugerenciaIA)
class SugerenciaAdmin(admin.ModelAdmin):
    list_display = ("documento", "proceso", "campo", "valor_propuesto", "confianza", "modelo", "estado")
    list_filter = ("estado", "proceso", "modelo")
    readonly_fields = [f.name for f in SugerenciaIA._meta.fields]
    actions = ["aceptar"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Aceptar las sugerencias seleccionadas tal como fueron propuestas")
    def aceptar(self, request, queryset):
        for s in queryset.filter(estado=SugerenciaIA.Estado.PENDIENTE):
            s.validar(request.user, aceptar=True)
        self.message_user(request, "Sugerencias aceptadas y registradas en la bitácora.")


class RevisionMuestraForm(forms.ModelForm):
    class Meta:
        model = MuestraAuditoria
        fields = ("resultado", "observacion")

    def clean(self):
        datos = super().clean()
        original = MuestraAuditoria.objects.get(pk=self.instance.pk)
        try:
            original.validar_resultado(datos.get("resultado"), datos.get("observacion", ""))
        except ValueError as e:
            raise forms.ValidationError(str(e))
        return datos


@admin.register(MuestraAuditoria)
class MuestraAuditoriaAdmin(admin.ModelAdmin):
    """Auditoría periódica por muestreo de clasificación y valoración (CLA-04, VAL-03).

    Las muestras se seleccionan con el comando `auditoria_muestra`, no desde
    aquí: es una tarea periódica de la entidad, no una acción sobre un
    documento puntual.
    """

    form = RevisionMuestraForm
    list_display = ("sugerencia", "fecha_seleccion", "resultado", "revisado_por")
    list_filter = ("resultado", "sugerencia__proceso", "sugerencia__campo")

    def changelist_view(self, request, extra_context=None):
        messages.info(
            request,
            format_html(
                'Exactitud calculada por proceso (CLA-04, VAL-03): <a href="{}">ver reporte de auditoría</a>.',
                reverse("informe_auditoria"),
            ),
        )
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        campos = ["sugerencia", "fecha_seleccion", "revisado_por", "fecha_revision"]
        if obj and obj.resultado != MuestraAuditoria.Resultado.PENDIENTE:
            campos += ["resultado", "observacion"]
        return campos

    def has_change_permission(self, request, obj=None):
        if obj and obj.resultado != MuestraAuditoria.Resultado.PENDIENTE:
            return False
        return super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        resultado, observacion = obj.resultado, obj.observacion
        obj.refresh_from_db()
        obj.revisar(request.user, resultado, observacion)
