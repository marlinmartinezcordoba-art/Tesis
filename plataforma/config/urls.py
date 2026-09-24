from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from lineamientos.views import informe

admin.site.site_header = "MAZUCA · Automatización archivística asistida por IA"
admin.site.site_title = "MAZUCA"
admin.site.index_title = "Archivo histórico"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("documentos/<int:pk>/informe/", informe, name="informe"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
