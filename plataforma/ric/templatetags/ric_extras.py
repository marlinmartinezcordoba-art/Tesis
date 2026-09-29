from django import template

register = template.Library()


@register.filter
def dict_valor(diccionario, clave):
    """Valor de una clave en un dict dentro de la plantilla (auditoría: antes → después)."""
    if not isinstance(diccionario, dict):
        return ""
    return diccionario.get(clave, "")


@register.filter
def hace(fecha):
    """«hace 3 horas»: solo la unidad mayor, más fácil de leer que «3 horas, 47 minutos»."""
    from django.utils import timezone
    from django.utils.timesince import timesince

    if not fecha:
        return ""
    if (timezone.now() - fecha).total_seconds() < 60:
        return "hace un momento"
    return f"hace {timesince(fecha, depth=1)}"
