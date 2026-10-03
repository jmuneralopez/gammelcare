from django import template

from ..configuracion import opciones

register = template.Library()


@register.filter
def tiene_configuracion(usuario):
    return bool(opciones(usuario))
