from django import template

from .. import services

register = template.Library()

CLASES = {'ok': 'text-bg-success', 'leve': 'text-bg-info', 'moderado': 'text-bg-warning', 'grave': 'text-bg-danger'}


@register.filter
def clase_nivel(nivel):
    return CLASES.get(nivel, 'text-bg-light border')


@register.inclusion_tag('valoracion/_resumen_expediente.html', takes_context=True)
def resumen_valoracion(context, residente):
    filas = services.estado_por_escala(residente)
    return {
        'residente': residente,
        'aplicadas': [f for f in filas if f['ultima']],
        'vencidas': [f for f in filas if f['vencida']],
    }
