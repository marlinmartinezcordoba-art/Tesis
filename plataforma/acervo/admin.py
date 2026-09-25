from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from . import extraccion
from .models import Documento, Entidad, EventoPreservacion, UnidadClasificacion


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
    list_display = ("titulo", "codigo_referencia", "unidad_clasificacion", "nivel_descripcion",
                     "publicado", "fecha_ingreso", "informe")
    list_filter = ("nivel_descripcion", "publicado", "unidad_clasificacion")
    search_fields = ("titulo", "codigo_referencia", "productor", "texto_extraido")
    readonly_fields = ("sha256", "formato", "tamano_bytes", "fecha_ingreso", "publicado", "texto_publico")
    inlines = [EventoInline]
    actions = ["verificar_fijeza", "extraer_texto", "revisar_datos_personales", "aprobar_publicacion",
               "generar_descripcion_nube", "generar_descripcion_local",
               "clasificar_nube", "clasificar_local",
               "valorar_nube", "valorar_local"]

    def get_readonly_fields(self, request, obj=None):
        # El archivo no se puede reemplazar después del ingreso.
        return self.readonly_fields + (("archivo",) if obj else ())

    def has_delete_permission(self, request, obj=None):
        # Un archivo histórico de conservación total no elimina documentos
        # desde la interfaz (lineamiento VAL-01): ni la IA ni una persona
        # con acceso a MAZUCA pueden borrar un documento ya ingresado. Una
        # disposición real requeriría un proceso aparte, fuera de esta
        # plataforma.
        return False

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

    @admin.action(description="Extraer texto (OCR) de los documentos seleccionados")
    def extraer_texto(self, request, queryset):
        for doc in queryset:
            try:
                _, detalle = extraccion.extraer_texto(doc, agente=request.user)
            except extraccion.FormatoNoSoportado as e:
                self.message_user(request, f"{doc}: {e}", level="warning")
                continue
            confianza = detalle["confianza_ocr"]
            aviso = f" (confianza OCR {confianza}%)" if confianza is not None else ""
            self.message_user(request, f"{doc}: {detalle['caracteres']} caracteres extraídos{aviso}.")


    @admin.action(description="Revisar datos personales (Ley 1581 de 2012)")
    def revisar_datos_personales(self, request, queryset):
        from acceso.servicios import revisar_datos_personales

        for doc in queryset:
            try:
                r = revisar_datos_personales(doc, agente=request.user)
            except ValueError as e:
                self.message_user(request, f"{doc}: {e}", level="warning")
                continue
            self.message_user(
                request,
                f"{doc}: {len(r.hallazgos)} posible(s) dato(s) personal(es), "
                f"{r.total_sensibles} sensible(s). Decida en «Revisiones de datos personales».",
            )

    @admin.action(description="Aprobar publicación en el portal de consulta")
    def aprobar_publicacion(self, request, queryset):
        from acceso.servicios import aprobar_publicacion

        for doc in queryset:
            ok, faltantes = aprobar_publicacion(doc, request.user)
            if ok:
                self.message_user(request, f"{doc}: aprobado para publicación.")
            else:
                self.message_user(request, f"{doc}: no se puede publicar. " + " ".join(faltantes), level="warning")


    def _generar_sugerencias(self, request, queryset, proveedor_cls, error_cls, etiqueta):
        from asistencia.proveedores import generar_sugerencias

        for doc in queryset:
            try:
                proveedor = proveedor_cls()
                sugerencias = generar_sugerencias(doc, proveedor)
            except error_cls as e:
                self.message_user(request, f"{doc}: {e}", level="warning")
                continue
            if not sugerencias:
                self.message_user(request, f"{doc}: {etiqueta} no propuso datos nuevos.")
                continue
            sin_evidencia = sum(1 for s in sugerencias if not s.evidencia_verificada)
            aviso = f" ({sin_evidencia} sin evidencia verificada)" if sin_evidencia else ""
            self.message_user(
                request,
                f"{doc}: {len(sugerencias)} sugerencia(s) de {etiqueta} pendientes de validación{aviso}.",
            )

    @admin.action(description="Generar borrador de descripción (IA en la nube, Claude)")
    def generar_descripcion_nube(self, request, queryset):
        from asistencia.proveedor_claude import ErrorProveedorIA, ProveedorClaude

        self._generar_sugerencias(request, queryset, ProveedorClaude, ErrorProveedorIA, "la IA en la nube")

    @admin.action(description="Generar borrador de descripción (IA local, sin conexión)")
    def generar_descripcion_local(self, request, queryset):
        from asistencia.proveedor_local import ErrorProveedorIA, ProveedorLocal

        self._generar_sugerencias(request, queryset, ProveedorLocal, ErrorProveedorIA, "la IA local")

    @admin.action(description="Proponer clasificación (IA en la nube, Claude)")
    def clasificar_nube(self, request, queryset):
        from asistencia.proveedor_claude import ErrorProveedorIA, ProveedorClasificacionClaude

        self._generar_sugerencias(
            request, queryset, ProveedorClasificacionClaude, ErrorProveedorIA, "la clasificación por IA en la nube"
        )

    @admin.action(description="Proponer clasificación (IA local, por palabras clave)")
    def clasificar_local(self, request, queryset):
        from asistencia.proveedor_local import ErrorProveedorIA, ProveedorClasificacionLocal

        self._generar_sugerencias(
            request, queryset, ProveedorClasificacionLocal, ErrorProveedorIA, "la clasificación por IA local"
        )

    @admin.action(description="Señalar indicios de valor secundario (IA en la nube, Claude)")
    def valorar_nube(self, request, queryset):
        from asistencia.proveedor_claude import ErrorProveedorIA, ProveedorValoracionClaude

        self._generar_sugerencias(
            request, queryset, ProveedorValoracionClaude, ErrorProveedorIA, "la valoración por IA en la nube"
        )

    @admin.action(description="Señalar indicios de valor secundario (IA local, por palabras clave)")
    def valorar_local(self, request, queryset):
        from asistencia.proveedor_local import ErrorProveedorIA, ProveedorValoracionLocal

        self._generar_sugerencias(
            request, queryset, ProveedorValoracionLocal, ErrorProveedorIA, "la valoración por IA local"
        )


@admin.register(UnidadClasificacion)
class UnidadClasificacionAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "tipo", "padre", "num_documentos")
    list_filter = ("tipo",)
    search_fields = ("codigo", "nombre", "descripcion", "palabras_clave")

    @admin.display(description="Documentos")
    def num_documentos(self, obj):
        return obj.documentos.count()


@admin.register(Entidad)
class EntidadAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "num_documentos")
    list_filter = ("tipo",)
    search_fields = ("nombre",)
    filter_horizontal = ("documentos",)

    @admin.display(description="Documentos")
    def num_documentos(self, obj):
        return obj.documentos.count()


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

