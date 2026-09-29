"""Identidad de los once módulos de la especificación funcional: número,
nombre, descripción de una línea, capa y un color propio por módulo, para
que la barra lateral y la cabecera de cada pantalla se reconozcan de un
vistazo (mismo criterio que el frontend de referencia entregado por la
usuaria: paleta cálida tipo papel, barra lateral en tinta profunda)."""

MODULOS = [
    {"numero": 1, "nombre": "Ingesta de documentos", "descripcion": "Carga de documentos y cálculo de huella digital",
     "url": "ingesta", "color": "#d97706", "capa": "entrada", "prefijos": ("ingesta",)},
    {"numero": 2, "nombre": "Preprocesamiento y OCR", "descripcion": "Texto nativo u OCR, idioma y calidad de lectura",
     "url": "preproceso", "color": "#ca8a04", "capa": "entrada", "prefijos": ("preproceso",)},
    {"numero": 3, "nombre": "Motor de análisis RiC", "descripcion": "Propuesta de entidades a partir del documento",
     "url": "analisis_lista", "color": "#7c3aed", "capa": "procesamiento", "prefijos": ("analisis",)},
    {"numero": 4, "nombre": "Modelado de relaciones", "descripcion": "Grafo de entidades y relaciones RiC",
     "url": "analisis_lista", "color": "#c026d3", "capa": "procesamiento", "prefijos": ("analisis_grafo", "analisis_relacion")},
    {"numero": 5, "nombre": "Vocabularios y autoridades", "descripcion": "Registros de autoridad y términos controlados",
     "url": "vocabularios", "color": "#0d9488", "capa": "procesamiento", "prefijos": ("vocabulario",)},
    {"numero": 6, "nombre": "Revisión archivística", "descripcion": "Validación humana de lo propuesto por el motor",
     "url": "revision_lista", "color": "#dc2626", "capa": "validacion", "prefijos": ("revision",)},
    {"numero": 7, "nombre": "Trazabilidad y auditoría", "descripcion": "Historial de decisiones sobre cada documento",
     "url": "historial_lista", "color": "#4f46e5", "capa": "validacion", "prefijos": ("historial",)},
    {"numero": 8, "nombre": "Catálogo y consulta", "descripcion": "Búsqueda y navegación por el grafo validado",
     "url": "catalogo", "color": "#0891b2", "capa": "consulta", "prefijos": ("catalogo", "ric_grafo")},
    {"numero": 9, "nombre": "Exportación e interoperabilidad", "descripcion": "Salida en RiC-O, JSON-LD y CSV",
     "url": "exportar", "color": "#ea580c", "capa": "consulta", "prefijos": ("exportar", "ric_sparql", "ric_exportar")},
    {"numero": 10, "nombre": "Panel de indicadores", "descripcion": "Avance y calidad de la descripción",
     "url": "panel", "color": "#2563eb", "capa": "consulta", "prefijos": ("panel", "ric_evaluacion")},
    {"numero": 11, "nombre": "Administración y seguridad", "descripcion": "Usuarios, roles y proveedores de IA",
     "url": "admin_usuarios", "color": "#475569", "capa": "transversal", "prefijos": ("admin_",)},
]

# `capa` de cada módulo solo decide qué rol lo ve en el menú (ver _base.html);
# el menú es una lista plana de los 11 módulos, sin encabezados por capa.


def modulo_actual(url_name):
    if not url_name:
        return None
    # los prefijos más específicos (analisis_grafo) antes que los generales (analisis)
    for m in sorted(MODULOS, key=lambda m: -max(len(p) for p in m["prefijos"])):
        if any(url_name.startswith(p) for p in m["prefijos"]):
            return m
    return None


def contexto_modulos(request):
    resolver = getattr(request, "resolver_match", None)
    actual = modulo_actual(resolver.url_name if resolver else None)
    return {
        "modulos": MODULOS,
        "modulo_actual": actual,
        "modulo_numero": actual["numero"] if actual else None,
    }
