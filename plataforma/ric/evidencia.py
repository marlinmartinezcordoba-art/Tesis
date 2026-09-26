"""Verificación de evidencia: la plataforma comprueba que el fragmento citado
por un proveedor de IA exista de verdad en el texto extraído, y en qué
página — nunca se confía en la palabra del proveedor (mismo principio que
`asistencia.proveedores.evidencia_en_texto`, aquí extendido con página).

F02 (OCR: coordenadas): cuando la página que contiene el fragmento tuvo OCR,
`localizar_posicion` calcula además su caja delimitadora (bbox) a partir de
las cajas por palabra que guardó la extracción (`PaginaTexto.cajas_ocr`).
"""


def _normalizar(texto):
    return " ".join(texto.lower().split())


def _pagina_que_contiene(instanciacion, fragmento):
    if not fragmento.strip():
        return None
    objetivo = _normalizar(fragmento)
    for pagina in instanciacion.paginas.all():
        if objetivo in _normalizar(pagina.texto):
            return pagina
    return None


def localizar_fragmento(instanciacion, fragmento):
    """Número de la primera página de `instanciacion` que contiene
    `fragmento` (sin importar mayúsculas ni espacios), o None si no
    aparece en ninguna página."""
    pagina = _pagina_que_contiene(instanciacion, fragmento)
    return pagina.numero if pagina else None


def localizar_posicion(pagina, fragmento):
    """Caja delimitadora (bbox) de `fragmento` dentro de las palabras que
    reconoció el OCR en `pagina` (unión de las cajas de sus palabras, en el
    mismo orden en que aparecen), o None si la página no tiene coordenadas
    de OCR o el fragmento no calza palabra por palabra con lo reconocido."""
    cajas = pagina.cajas_ocr
    if not cajas:
        return None
    objetivo = [p for p in _normalizar(fragmento).split(" ") if p]
    if not objetivo:
        return None
    palabras = [_normalizar(c["texto"]) for c in cajas]
    n = len(objetivo)
    for i in range(len(palabras) - n + 1):
        if palabras[i:i + n] == objetivo:
            ventana = cajas[i:i + n]
            izquierda = min(c["izquierda"] for c in ventana)
            arriba = min(c["arriba"] for c in ventana)
            derecha = max(c["izquierda"] + c["ancho"] for c in ventana)
            abajo = max(c["arriba"] + c["alto"] for c in ventana)
            return {"izquierda": izquierda, "arriba": arriba, "ancho": derecha - izquierda, "alto": abajo - arriba}
    return None


def crear_evidencia(instanciacion, fragmento, posicion=None):
    """Crea y devuelve una Evidencia verificada contra el texto real de
    `instanciacion`. `verificada=False` si el fragmento no se encontró en
    ninguna página; en ese caso `pagina` queda vacío. Si no se pasa
    `posicion` explícita, se calcula automáticamente con `localizar_posicion`
    cuando la página tiene coordenadas de OCR."""
    from .models import Evidencia

    pagina = _pagina_que_contiene(instanciacion, fragmento)
    if posicion is None and pagina is not None:
        posicion = localizar_posicion(pagina, fragmento)
    return Evidencia.objects.create(
        instanciacion=instanciacion,
        pagina=pagina.numero if pagina else None,
        fragmento=fragmento,
        posicion=posicion,
        verificada=pagina is not None,
    )
