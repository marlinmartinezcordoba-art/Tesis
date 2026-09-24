from django.contrib import admin

from .models import Criterio


@admin.register(Criterio)
class CriterioAdmin(admin.ModelAdmin):
    list_display = ("codigo", "proceso", "atributo", "fuente_normativa", "obligatorio", "estado")
    list_filter = ("proceso", "atributo", "estado", "obligatorio")
    search_fields = ("codigo", "enunciado", "fuente_normativa")
