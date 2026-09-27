"""F03 (Comprensión documental): detección automática de componentes
estructurales sobre el texto ya extraído (F02) — encabezado, título,
campos tipo PARA/DE/ASUNTO, fechas, secciones, artículos, párrafos y
firmas —, más tablas reales cuando el original es un .docx.

Es heurística basada en reglas (expresiones regulares sobre líneas), no un
modelo de IA: cada componente guarda qué regla lo detectó (`regla`), para
que sea trazable y corregible por la persona archivista, igual que el
resto de la plataforma nunca oculta cómo llegó a un resultado.

Alcance honesto: no detecta sellos ni tablas dentro de imágenes o PDFs
escaneados — eso requiere análisis visual de la imagen (detectar líneas y
regiones en píxeles), no solo del texto extraído, y no está implementado.
Las tablas solo se detectan cuando el original es un .docx, reabriendo el
archivo directamente para leer su estructura real de filas/columnas.
"""

import re
from pathlib import Path

FECHA_RE = re.compile(r"\d{1,2} de [a-záéíóúñ]+ de \d{4}", re.IGNORECASE)
FECHA_RE_COMPLETA = re.compile(r"^\d{1,2} de [a-záéíóúñ]+ de \d{4}$", re.IGNORECASE)
CAMPO_RE = re.compile(r"^(PARA|DE|ASUNTO|LUGAR|FECHA|REF|REFERENCIA)\s*:\s*(.*)$", re.IGNORECASE)
ARTICULO_RE = re.compile(r"^ART[ÍI]CULO\s+(\d+)\.?\s*(.*)$", re.IGNORECASE)
TITULO_RE = re.compile(
    r"^(ACTA\s+DE\s+REUNI[ÓO]N|OFICIO|RESOLUCI[ÓO]N|INFORME|MEMORANDO|CIRCULAR)\b",
    re.IGNORECASE,
)
FIRMA_DISPARADORES = ("firma:", "atentamente", "cordialmente")
MAX_LINEAS_ENCABEZADO = 3


def _es_linea_mayusculas(linea):
    letras = [c for c in linea if c.isalpha()]
    return bool(letras) and all(c.isupper() for c in letras) and len(linea) >= 3


def _parece_linea_de_firma(texto):
    """Una línea corta sin punto final (nombre o cargo de cierre) se
    distingue de una oración normal, que casi siempre termina en '.'."""
    texto = texto.strip()
    if not texto or texto.endswith((".", ":")):
        return False
    return len(texto.split()) <= 6


def _fechas_inline(texto):
    return [
        {"orden": None, "tipo": "fecha", "etiqueta": "", "texto": m.group(0),
         "datos": {"fecha_texto": m.group(0)}, "confianza": 0.85, "regla": "FECHA_RE_inline"}
        for m in FECHA_RE.finditer(texto)
    ]


def _detectar_lineas(lineas):
    """Clasifica una lista de líneas no vacías de una página/documento y
    devuelve sus componentes estructurales en orden de lectura."""
    componentes = []
    en_encabezado = True
    lineas_encabezado = 0

    def emitir(tipo, texto, etiqueta="", datos=None, confianza=1.0, regla=""):
        componentes.append({
            "tipo": tipo, "etiqueta": etiqueta, "texto": texto,
            "datos": datos, "confianza": confianza, "regla": regla,
        })

    for linea in lineas:
        if en_encabezado:
            if TITULO_RE.match(linea):
                en_encabezado = False
                emitir("titulo", linea, confianza=0.9, regla="TITULO_RE")
                componentes += _fechas_inline(linea)
                continue
            if CAMPO_RE.match(linea) or FECHA_RE_COMPLETA.match(linea):
                en_encabezado = False
                # sigue al bloque general de abajo, sin 'continue'
            elif _es_linea_mayusculas(linea) and lineas_encabezado < MAX_LINEAS_ENCABEZADO:
                lineas_encabezado += 1
                emitir("encabezado", linea, confianza=0.7, regla="encabezado_mayusculas")
                componentes += _fechas_inline(linea)
                continue
            else:
                en_encabezado = False

        m_campo = CAMPO_RE.match(linea)
        if m_campo:
            etiqueta, valor = m_campo.group(1).upper(), m_campo.group(2).strip()
            emitir("campo", valor, etiqueta=etiqueta, confianza=0.95, regla="CAMPO_RE")
            componentes += _fechas_inline(valor)
            continue

        m_articulo = ARTICULO_RE.match(linea)
        if m_articulo:
            emitir("articulo", linea, etiqueta=f"ARTÍCULO {m_articulo.group(1)}", confianza=0.95, regla="ARTICULO_RE")
            componentes += _fechas_inline(linea)
            continue

        if FECHA_RE_COMPLETA.match(linea):
            emitir("fecha", linea, datos={"fecha_texto": linea}, confianza=0.9, regla="FECHA_RE_COMPLETA")
            continue

        if any(linea.strip().lower().startswith(d) for d in FIRMA_DISPARADORES):
            emitir("firma", linea, confianza=0.9, regla="firma_disparador")
            continue

        if _es_linea_mayusculas(linea):
            emitir("seccion", linea, confianza=0.6, regla="seccion_mayusculas")
            componentes += _fechas_inline(linea)
            continue

        emitir("parrafo", linea, confianza=0.3, regla="por_descarte")
        componentes += _fechas_inline(linea)

    _reclasificar_firma_final(componentes)
    for i, c in enumerate(componentes):
        c["orden"] = i
    return componentes


def _reclasificar_firma_final(componentes):
    """Barrido final: si las últimas líneas quedaron como 'párrafo' por
    descarte pero tienen forma de nombre/cargo de cierre, se reclasifican
    como firma — patrón común en actas y resoluciones que no usan la
    palabra 'Firma:' explícita (ver RESOLUCION_045/099 del paquete de
    pruebas: terminan en 'Nombre' + 'Cargo' sin ningún disparador)."""
    i = len(componentes) - 1
    reclasificadas = 0
    while i >= 0 and reclasificadas < 2 and componentes[i]["tipo"] == "parrafo" \
            and _parece_linea_de_firma(componentes[i]["texto"]):
        componentes[i]["tipo"] = "firma"
        componentes[i]["confianza"] = 0.6
        componentes[i]["regla"] = "firma_cola_final"
        reclasificadas += 1
        i -= 1


def _tablas_de_docx(ruta):
    """Tablas reales de un .docx (filas × columnas exactas, leídas de su
    estructura XML) — no es una suposición sobre texto plano."""
    import docx

    documento = docx.Document(str(ruta))
    tablas = []
    for tabla in documento.tables:
        filas = [[celda.text for celda in fila.cells] for fila in tabla.rows]
        if filas:
            tablas.append(filas)
    return tablas


def detectar_estructura(instanciacion):
    """Componentes estructurales de `instanciacion`, recorriendo sus
    páginas ya extraídas (F02) más, si el original es un .docx, sus tablas
    reales. Devuelve una lista de dicts listos para `guardar_componentes`."""
    componentes = []
    for pagina in instanciacion.paginas.all():
        lineas = [l.strip() for l in pagina.texto.splitlines() if l.strip()]
        for c in _detectar_lineas(lineas):
            componentes.append({**c, "pagina": pagina.numero})

    extension = Path(instanciacion.archivo.name).suffix.lower()
    if extension == ".docx":
        for tabla in _tablas_de_docx(instanciacion.archivo.path):
            componentes.append({
                "pagina": 1, "orden": len(componentes), "tipo": "tabla", "etiqueta": "",
                "texto": f"Tabla de {len(tabla)} fila(s) × {len(tabla[0])} columna(s)",
                "datos": {"filas": tabla}, "confianza": 1.0, "regla": "docx_tabla_real",
            })

    return componentes


def guardar_componentes(instanciacion, componentes):
    """Reemplaza los componentes estructurales de `instanciacion` por los
    recién detectados (igual que la re-extracción de texto reemplaza sus
    PaginaTexto: si el archivo cambió, la estructura vieja ya no aplica)."""
    from .models import ComponenteEstructural

    instanciacion.componentes.all().delete()
    ComponenteEstructural.objects.bulk_create([
        ComponenteEstructural(instanciacion=instanciacion, **c) for c in componentes
    ])


def detectar_y_guardar_estructura(instanciacion):
    componentes = detectar_estructura(instanciacion)
    guardar_componentes(instanciacion, componentes)
    return componentes
