from django import template

register = template.Library()


@register.filter
def dict_valor(diccionario, clave):
    """Valor de una clave en un dict dentro de la plantilla (auditoría: antes → después)."""
    if not isinstance(diccionario, dict):
        return ""
    return diccionario.get(clave, "")
