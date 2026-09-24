from django import forms
from django.contrib import admin

from .models import RevisionDatosPersonales


class DecisionForm(forms.ModelForm):
    class Meta:
        model = RevisionDatosPersonales
        fields = ("decision", "motivo")

    def clean(self):
        datos = super().clean()
        # Se valida contra el estado guardado, no contra el que llenó el formulario.
        original = RevisionDatosPersonales.objects.get(pk=self.instance.pk)
        try:
            original.validar_decision(datos.get("decision"), datos.get("motivo", ""))
        except ValueError as e:
            raise forms.ValidationError(str(e))
        return datos


@admin.register(RevisionDatosPersonales)
class RevisionAdmin(admin.ModelAdmin):
    form = DecisionForm
    list_display = ("documento", "fecha", "num_hallazgos", "total_sensibles", "decision", "decidido_por")
    list_filter = ("decision",)
    actions = ["marcar_publicable"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Una decisión tomada no se edita: queda como constancia.
        if obj and obj.decision != RevisionDatosPersonales.Decision.PENDIENTE:
            return False
        return super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        campos = ["documento", "fecha", "detector_version", "hallazgos_legibles",
                  "decidido_por", "fecha_decision"]
        if obj and obj.decision != RevisionDatosPersonales.Decision.PENDIENTE:
            campos += ["decision", "motivo"]
        return campos

    def get_fields(self, request, obj=None):
        return ["documento", "fecha", "detector_version", "hallazgos_legibles",
                "decision", "motivo", "decidido_por", "fecha_decision"]

    def save_model(self, request, obj, form, change):
        decision, motivo = obj.decision, obj.motivo
        obj.refresh_from_db()
        obj.decidir(request.user, decision, motivo)

    @admin.display(description="Hallazgos")
    def num_hallazgos(self, obj):
        return len(obj.hallazgos)

    @admin.display(description="Posibles datos personales")
    def hallazgos_legibles(self, obj):
        return "\n".join(f"• {h['tipo']}: «{h['texto']}»" for h in obj.hallazgos) or "Ninguno"

    @admin.action(description="Marcar como publicables (solo revisiones sin hallazgos)")
    def marcar_publicable(self, request, queryset):
        hechas = 0
        for r in queryset.filter(decision=RevisionDatosPersonales.Decision.PENDIENTE):
            if not r.hallazgos and r.vigente:
                r.decidir(request.user, RevisionDatosPersonales.Decision.PUBLICABLE)
                hechas += 1
        self.message_user(
            request,
            f"{hechas} revisión(es) marcadas como publicables. "
            "Las que tienen hallazgos deben decidirse una por una, con motivo.",
        )
