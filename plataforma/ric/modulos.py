"""El menú de RICORA, organizado por proceso archivístico y no por etapa
técnica: cada entrada agrupa las pantallas que sirven a un mismo proceso
(instrumentos, captura y clasificación, descripción, valoración y
disposición, consulta y exportación, indicadores) y la administración,
que solo ve el superusuario. Cada proceso tiene pestañas con sus pantallas.

`numero`, `nombre`, `descripcion` y `color` alimentan la cabecera de cada
pantalla; `prefijos` reconoce por el nombre de la URL a qué proceso
pertenece la pantalla actual; `ver` decide qué rol lo encuentra en el menú.
Los once módulos de la especificación funcional siguen existiendo como
pantallas: aquí solo se agrupan."""

MODULOS = [
    {"numero": 1, "nombre": "Instrumentos archivísticos", "descripcion": "Organigrama, cuadro de clasificación, TRD, vocabularios y autoridades",
     "url": "vocabularios", "color": "#0d9488", "ver": "todos", "prefijos": ("vocabulario",),
     "pestanas": (("vocabularios", "Vocabularios y autoridades", ("vocabularios", "vocabulario_ficha", "vocabulario_fusionar", "vocabularios_importar", "vocabularios_sembrar")),
                  ("vocabularios_duplicados", "Posibles duplicados", ("vocabularios_duplicados",)))},
    {"numero": 2, "nombre": "Captura y clasificación", "descripcion": "Ingesta por serie y expediente, huella digital, texto y OCR",
     "url": "ingesta", "color": "#d97706", "ver": "ingestar", "prefijos": ("ingesta", "preproceso"),
     "pestanas": (("ingesta", "Cargar documentos", ("ingesta",)),
                  ("preproceso", "Preprocesamiento y OCR", ("preproceso",)))},
    {"numero": 3, "nombre": "Descripción", "descripcion": "Análisis con IA, modelado de relaciones, revisión archivística y trazabilidad",
     "url": "analisis_lista", "color": "#7c3aed", "ver": "revisar", "prefijos": ("analisis", "revision", "historial"),
     "pestanas": (("analisis_lista", "Análisis y relaciones", ("analisis",)),
                  ("revision_lista", "Revisión archivística", ("revision",)),
                  ("historial_lista", "Trazabilidad y auditoría", ("historial",)))},
    {"numero": 4, "nombre": "Valoración y disposición", "descripcion": "Retención heredada de la TRD, transferencias e inventario documental",
     "url": "valoracion", "color": "#dc2626", "ver": "revisar", "prefijos": ("valoracion",),
     "pestanas": (("valoracion", "Expedientes y retención", ("valoracion",)),
                  ("valoracion_transferencias", "Transferencias y disposición final", ("valoracion_transferencias",)),
                  ("valoracion_fuid", "Inventario FUID", ("valoracion_fuid",)))},
    {"numero": 5, "nombre": "Consulta y exportación", "descripcion": "Catálogo, grafo validado y salida en RiC-O, JSON-LD y CSV",
     "url": "catalogo", "color": "#0891b2", "ver": "todos", "prefijos": ("catalogo", "ric_grafo", "exportar", "ric_sparql", "ric_exportar"),
     "pestanas": (("catalogo", "Catálogo", ("catalogo", "ric_grafo")),
                  ("exportar", "Exportación e interoperabilidad", ("exportar", "ric_sparql", "ric_exportar")))},
    {"numero": 6, "nombre": "Indicadores", "descripcion": "Avance y calidad de la descripción",
     "url": "panel", "color": "#2563eb", "ver": "todos", "prefijos": ("panel", "ric_evaluacion"), "pestanas": ()},
    {"numero": 7, "nombre": "Administración", "descripcion": "Usuarios, roles, proveedores de IA y parámetros",
     "url": "admin_usuarios", "color": "#475569", "ver": "administrar", "prefijos": ("admin_",), "pestanas": ()},
]


def modulo_actual(url_name):
    if not url_name:
        return None
    # los prefijos más específicos (ric_exportar) antes que los generales (exportar)
    for m in sorted(MODULOS, key=lambda m: -max(len(p) for p in m["prefijos"])):
        if any(url_name.startswith(p) for p in m["prefijos"]):
            return m
    return None


def pestana_actual(modulo, url_name):
    if modulo is None or not url_name:
        return None
    candidatas = sorted(modulo["pestanas"], key=lambda p: -max((len(x) for x in p[2]), default=0))
    for url, _nombre, prefijos in candidatas:
        if any(url_name.startswith(p) for p in prefijos):
            return url
    return None


def contexto_modulos(request):
    resolver = getattr(request, "resolver_match", None)
    url_name = resolver.url_name if resolver else None
    actual = modulo_actual(url_name)
    return {
        "modulos": MODULOS,
        "modulo_actual": actual,
        "modulo_numero": actual["numero"] if actual else None,
        "pestana_actual": pestana_actual(actual, url_name),
    }
