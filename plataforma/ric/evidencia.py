"""Verificación de evidencia: la plataforma comprueba que el fragmento citado
por un proveedor de IA exista de verdad en el texto extraído, y en qué
página — nunca se confía en la palabra del proveedor (mismo principio que
`asistencia.proveedores.evidencia_en_texto`, aquí extendido con página).
"""


def _normalizar(texto):
    return " ".join(texto.lower().split())


def localizar_fragmento(instanciacion, fragmento):
    """Número de la primera página de `instanciacion` que contiene
    `fragmento` (sin importar mayúsculas ni espacios), o None si no
    aparece en ninguna página."""
    if not fragmento.strip():
        return None
    objetivo = _normalizar(fragmento)
    for pagina in instanciacion.paginas.all():
        if objetivo in _normalizar(pagina.texto):
            return pagina.numero
    return None


def crear_evidencia(instanciacion, fragmento, posicion=None):
    """Crea y devuelve una Evidencia verificada contra el texto real de
    `instanciacion`. `verificada=False` si el fragmento no se encontró en
    ninguna página; en ese caso `pagina` queda vacío."""
    from .models import Evidencia

    pagina = localizar_fragmento(instanciacion, fragmento)
    return Evidencia.objects.create(
        instanciacion=instanciacion,
        pagina=pagina,
        fragmento=fragmento,
        posicion=posicion,
        verificada=pagina is not None,
    )
