from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from acervo.views import exportar_dublin_core, exportar_premis
from lineamientos.views import informe, informe_auditoria
from ric.views import bandeja_validacion, decidir_propuesta

admin.site.site_header = "MAZUCA · Automatización archivística asistida por IA"
admin.site.site_title = "MAZUCA"
admin.site.index_title = "Archivo histórico"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auditoria/", informe_auditoria, name="informe_auditoria"),
    path("documentos/<int:pk>/informe/", informe, name="informe"),
    path("documentos/<int:pk>/exportar/dublin-core.xml", exportar_dublin_core, name="exportar_dublin_core"),
    path("documentos/<int:pk>/exportar/premis.xml", exportar_premis, name="exportar_premis"),
    path("ric/bandeja/", bandeja_validacion, name="ric_bandeja"),
    path("ric/bandeja/<int:pk>/decidir/", decidir_propuesta, name="ric_decidir_propuesta"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
