from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from django.views.generic import RedirectView

from acervo.views import exportar_dublin_core, exportar_premis
from lineamientos.views import informe, informe_auditoria
from ric import vistas_admin, vistas_analisis, vistas_catalogo, vistas_ingesta, vistas_panel, vistas_vocabularios
from ric.views import (
    evaluacion_datos,
    evaluacion_html,
    exportar_rdf,
    exportar_rdf_completo,
    grafo_datos,
    grafo_html,
    servir_archivo,
    sparql_endpoint,
    sparql_html,
)

admin.site.site_header = "RICORA · Panel técnico"
admin.site.site_title = "RICORA"
admin.site.index_title = "Archivo histórico"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="panel", permanent=False)),

    # M11 · Administración y seguridad (antes de admin/ para no chocar con el panel técnico)
    path("admin/usuarios/", vistas_admin.admin_usuarios, name="admin_usuarios"),
    path("admin/usuarios/<int:pk>/", vistas_admin.admin_usuario_editar, name="admin_usuario_editar"),
    path("admin/usuarios/proveedores/", vistas_admin.admin_proveedor_agregar, name="admin_proveedor_agregar"),
    path("admin/usuarios/proveedores/<int:pk>/probar/", vistas_admin.admin_proveedor_probar, name="admin_proveedor_probar"),
    path("admin/usuarios/proveedores/<int:pk>/activar/", vistas_admin.admin_proveedor_activar, name="admin_proveedor_activar"),
    path("admin/usuarios/proveedores/<int:pk>/eliminar/", vistas_admin.admin_proveedor_eliminar, name="admin_proveedor_eliminar"),
    path("admin/usuarios/parametros/", vistas_admin.admin_parametros, name="admin_parametros"),
    path("admin/", admin.site.urls),

    # M1 · Ingesta y M2 · Preprocesamiento y OCR
    path("ingesta/", vistas_ingesta.ingesta, name="ingesta"),
    path("ingesta/preproceso/", vistas_ingesta.preproceso, name="preproceso"),
    path("ingesta/preproceso/enviar/", vistas_ingesta.preproceso_enviar, name="preproceso_enviar"),
    path("ingesta/preproceso/<int:pk>/pagina/<int:numero>/", vistas_ingesta.preproceso_pagina, name="preproceso_pagina"),
    path("ingesta/preproceso/<int:pk>/pagina/<int:numero>/decidir/", vistas_ingesta.preproceso_pagina_decidir, name="preproceso_pagina_decidir"),

    # M3 · Motor de análisis RiC y M4 · Modelado de relaciones
    path("analisis/", vistas_analisis.analisis_lista, name="analisis_lista"),
    path("analisis/<int:pk>/", vistas_analisis.analisis, name="analisis"),
    path("analisis/<int:pk>/generar/", vistas_analisis.analisis_generar, name="analisis_generar"),
    path("analisis/<int:pk>/forma/", vistas_analisis.analisis_forma, name="analisis_forma"),
    path("analisis/propuesta/<int:pk>/decidir/", vistas_analisis.analisis_decidir, name="analisis_decidir"),
    path("analisis/<int:pk>/grafo/", vistas_analisis.analisis_grafo, name="analisis_grafo"),
    path("analisis/<int:pk>/grafo/datos.json", vistas_analisis.analisis_grafo_datos, name="analisis_grafo_datos"),
    path("analisis/<int:pk>/relacion/<int:relacion_pk>/", vistas_analisis.analisis_relacion, name="analisis_relacion"),

    # M5 · Vocabularios y autoridades
    path("vocabularios/", vistas_vocabularios.vocabularios, name="vocabularios"),
    path("vocabularios/duplicados/", vistas_vocabularios.vocabularios_duplicados, name="vocabularios_duplicados"),
    path("vocabularios/importar/", vistas_vocabularios.vocabularios_importar, name="vocabularios_importar"),
    path("vocabularios/<str:tipo>/<int:pk>/", vistas_vocabularios.vocabulario_ficha, name="vocabulario_ficha"),
    path("vocabularios/<str:tipo>/<int:pk>/fusionar/", vistas_vocabularios.vocabulario_fusionar, name="vocabulario_fusionar"),

    # M6 · Revisión archivística
    path("revision/", vistas_analisis.revision_lista, name="revision_lista"),
    path("revision/<int:pk>/", vistas_analisis.revision, name="revision"),
    path("revision/<int:pk>/aprobar/", vistas_analisis.revision_aprobar, name="revision_aprobar"),
    path("revision/<int:pk>/relacion/<int:relacion_pk>/rechazar/", vistas_analisis.revision_rechazar, name="revision_rechazar"),

    # M7 · Trazabilidad y auditoría
    path("documentos/", vistas_analisis.historial_lista, name="historial_lista"),
    path("documentos/<int:pk>/historial/", vistas_analisis.historial, name="historial"),

    # M8 · Catálogo y consulta y M9 · Exportación e interoperabilidad
    path("catalogo/", vistas_catalogo.catalogo, name="catalogo"),
    path("catalogo/sugerencias/", vistas_catalogo.catalogo_sugerencias, name="catalogo_sugerencias"),
    path("catalogo/<str:tipo>/<int:pk>/", vistas_catalogo.catalogo_ficha, name="catalogo_ficha"),
    path("exportar/", vistas_catalogo.exportar, name="exportar"),
    path("exportar/<int:pk>/descargar/", vistas_catalogo.exportar_descargar, name="exportar_descargar"),

    # M10 · Panel de indicadores
    path("panel/", vistas_panel.panel, name="panel"),

    # Acceso y utilidades compartidas
    path("ric/entrar/", LoginView.as_view(template_name="ric/login.html", redirect_authenticated_user=True), name="ric_login"),
    path("ric/salir/", LogoutView.as_view(next_page="ric_login"), name="ric_logout"),
    path("ric/archivo/<int:pk>/", servir_archivo, name="ric_archivo"),
    path("ric/rdf/", exportar_rdf_completo, name="ric_exportar_rdf_completo"),
    path("ric/rdf/<str:tipo>/<int:pk>/", exportar_rdf, name="ric_exportar_rdf"),
    path("ric/grafo/<str:tipo>/<int:pk>/", grafo_html, name="ric_grafo"),
    path("ric/grafo/<str:tipo>/<int:pk>/datos.json", grafo_datos, name="ric_grafo_datos"),
    path("ric/sparql/", sparql_html, name="ric_sparql"),
    path("ric/sparql/consultar/", sparql_endpoint, name="ric_sparql_endpoint"),
    path("ric/evaluacion/", evaluacion_html, name="ric_evaluacion"),
    path("ric/evaluacion/datos.json", evaluacion_datos, name="ric_evaluacion_datos"),

    # Módulos heredados (acervo / lineamientos)
    path("auditoria/", informe_auditoria, name="informe_auditoria"),
    path("documentos/<int:pk>/informe/", informe, name="informe"),
    path("documentos/<int:pk>/exportar/dublin-core.xml", exportar_dublin_core, name="exportar_dublin_core"),
    path("documentos/<int:pk>/exportar/premis.xml", exportar_premis, name="exportar_premis"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
