from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from acervo.views import exportar_dublin_core, exportar_premis
from lineamientos.views import informe, informe_auditoria
from ric.views import (
    bandeja_validacion,
    busqueda_html,
    decidir_propuesta,
    evaluacion_datos,
    evaluacion_html,
    exportar_rdf,
    exportar_rdf_completo,
    grafo_datos,
    grafo_html,
    inicio,
    registros_html,
    sparql_endpoint,
    sparql_html,
)

admin.site.site_header = "MAZUCA · Automatización archivística asistida por IA"
admin.site.site_title = "MAZUCA"
admin.site.index_title = "Archivo histórico"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auditoria/", informe_auditoria, name="informe_auditoria"),
    path("documentos/<int:pk>/informe/", informe, name="informe"),
    path("documentos/<int:pk>/exportar/dublin-core.xml", exportar_dublin_core, name="exportar_dublin_core"),
    path("documentos/<int:pk>/exportar/premis.xml", exportar_premis, name="exportar_premis"),
    path("ric/", inicio, name="ric_inicio"),
    path("ric/registros/", registros_html, name="ric_registros"),
    path("ric/bandeja/", bandeja_validacion, name="ric_bandeja"),
    path("ric/bandeja/<int:pk>/decidir/", decidir_propuesta, name="ric_decidir_propuesta"),
    path("ric/rdf/", exportar_rdf_completo, name="ric_exportar_rdf_completo"),
    path("ric/rdf/<str:tipo>/<int:pk>/", exportar_rdf, name="ric_exportar_rdf"),
    path("ric/grafo/<str:tipo>/<int:pk>/", grafo_html, name="ric_grafo"),
    path("ric/grafo/<str:tipo>/<int:pk>/datos.json", grafo_datos, name="ric_grafo_datos"),
    path("ric/sparql/", sparql_html, name="ric_sparql"),
    path("ric/sparql/consultar/", sparql_endpoint, name="ric_sparql_endpoint"),
    path("ric/search/", busqueda_html, name="ric_busqueda"),
    path("ric/evaluacion/", evaluacion_html, name="ric_evaluacion"),
    path("ric/evaluacion/datos.json", evaluacion_datos, name="ric_evaluacion_datos"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
