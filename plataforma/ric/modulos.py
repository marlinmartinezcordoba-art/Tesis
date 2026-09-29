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

# Los módulos de la especificación funcional (M0 a M11) y su estado frente a
# la Definición de Terminado del prompt de desarrollo, para que quien valida
# sepa en cada pantalla qué módulo está viendo.
VALIDADO, POR_VALIDAR, ANTERIOR, PENDIENTE = "validado", "por_validar", "anterior", "pendiente"
ESTADOS_MODULO = {
    VALIDADO: "Validado",
    POR_VALIDAR: "Por validar",
    ANTERIOR: "Construido antes · sin revisar",
    PENDIENTE: "Pendiente de rehacer",
}
MODULOS_ESPEC = {
    0: ("Autenticación, autorización y auditoría", VALIDADO),
    1: ("Ingesta y visor documental", VALIDADO),
    2: ("Preprocesamiento y OCR", VALIDADO),
    3: ("Motor de análisis RiC", ANTERIOR),
    4: ("Modelado de relaciones", ANTERIOR),
    5: ("Vocabularios y autoridades", ANTERIOR),
    6: ("Revisión archivística", VALIDADO),
    7: ("Trazabilidad", VALIDADO),
    8: ("Catálogo y consulta", VALIDADO),
    9: ("Exportación e interoperabilidad", VALIDADO),
    10: ("Panel de indicadores", POR_VALIDAR),
    11: ("Administración", PENDIENTE),
}
# Pantalla (nombre de URL de la pestaña o del proceso) -> módulo de la especificación.
MODULO_DE_PANTALLA = {
    "vocabularios": 5, "vocabularios_duplicados": 5,
    "ingesta": 1, "preproceso": 2,
    "analisis_lista": 3, "revision_lista": 6, "historial_lista": 7,
    "catalogo": 8, "exportar": 9,
    "panel": 10, "admin_usuarios": 11,
}

# El módulo 0 no tiene pantalla propia: vive en Administración (pestañas
# Auditoría y Eliminados, revocación de sesiones) y en el inicio de sesión.
TAMBIEN_EN = {"admin_usuarios": (0,), "analisis_lista": (4,)}


def modulo_espec(numero):
    if numero is None:
        return None
    nombre, estado = MODULOS_ESPEC[numero]
    return {"numero": numero, "codigo": f"M{numero}", "nombre": nombre, "estado": estado, "estado_texto": ESTADOS_MODULO[estado]}


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
     "url": "catalogo", "color": "#0891b2", "ver": "todos", "prefijos": ("catalogo", "ric_grafo", "exportar", "ric_sparql", "ric_exportar", "visor"),
     "pestanas": (("catalogo", "Catálogo", ("catalogo", "ric_grafo", "visor")),
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


# Administración reparte sus pantallas por el parámetro ?pestana=; el
# módulo 0 (auditoría y borrado lógico) vive ahí junto al 11.
PANTALLAS_ADMIN = (
    ("usuarios", "Usuarios y roles", 11),
    ("proveedores", "Proveedores de IA", 11),
    ("parametros", "Parámetros", 11),
    ("auditoria", "Auditoría", 0),
    ("eliminados", "Eliminados (restaurar)", 0),
    ("modulos", "Estado de los módulos", None),
)


def _submenu(m, pestana, request, url_name):
    from django.urls import reverse

    if m["url"] == "admin_usuarios":
        actual = request.GET.get("pestana", "usuarios") if (url_name or "").startswith("admin_") else None
        return [{"href": f"{reverse('admin_usuarios')}?pestana={clave}", "nombre": nombre, "espec": modulo_espec(num),
                 "activa": actual == clave, "clave": clave} for clave, nombre, num in PANTALLAS_ADMIN]
    return [{"href": reverse(u), "nombre": n, "espec": modulo_espec(MODULO_DE_PANTALLA.get(u)), "activa": pestana == u, "clave": u}
            for u, n, _p in m["pestanas"]]


def contexto_modulos(request):
    resolver = getattr(request, "resolver_match", None)
    url_name = resolver.url_name if resolver else None
    actual = modulo_actual(url_name)
    pestana = pestana_actual(actual, url_name)
    espec = MODULO_DE_PANTALLA.get(pestana or (actual["url"] if actual else None))
    menu = []
    for m in MODULOS:
        urls = [p[0] for p in m["pestanas"]] or [m["url"]]
        codigos = sorted({MODULO_DE_PANTALLA[u] for u in urls if u in MODULO_DE_PANTALLA} | set(TAMBIEN_EN.get(m["url"], ())))
        submenu = _submenu(m, pestana, request, url_name)
        if actual is m and m["url"] == "admin_usuarios":
            activa = next((x for x in submenu if x["activa"]), None)
            espec = activa["espec"]["numero"] if activa and activa["espec"] else 11
        menu.append({**m, "codigos": ", ".join(f"M{c}" for c in codigos), "submenu": submenu})
    activa = next((x for m in menu if actual and m["numero"] == actual["numero"] for x in m["submenu"] if x["activa"]), None)
    from .ayuda import guia_de

    return {
        "guia": guia_de(url_name or ("inicio" if request.path == "/" else "")),
        "pantalla_nombre": activa["nombre"] if activa else "",
        "modulos": menu,
        "modulo_actual": next((m for m in menu if actual and m["numero"] == actual["numero"]), None),
        "modulo_numero": actual["numero"] if actual else None,
        "pestana_actual": pestana,
        "modulo_espec": modulo_espec(espec),
    }
