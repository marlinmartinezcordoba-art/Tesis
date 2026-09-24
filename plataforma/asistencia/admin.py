from django.contrib import admin

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
