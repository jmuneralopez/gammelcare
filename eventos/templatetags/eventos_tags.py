from django import template

from ..models import EventoAdverso
from ..permisos import puede_reportar

register = template.Library()

CLASES = {'sin_dano': 'text-bg-light border', 'leve': 'text-bg-info', 'moderado': 'text-bg-warning',
          'grave': 'text-bg-danger', 'muerte': 'text-bg-dark'}


@register.filter
def clase_gravedad(gravedad):
    return CLASES.get(gravedad, 'text-bg-light border')


@register.filter
def gravedad_corta(evento):
    return evento.get_gravedad_display().split(' (')[0]


@register.inclusion_tag('eventos/_resumen_expediente.html', takes_context=True)
def resumen_eventos(context, residente):
    eventos = list(EventoAdverso.objects.filter(residente=residente).order_by('-fecha_hora')[:5])
    return {
        'residente': residente, 'eventos': eventos,
        'total': EventoAdverso.objects.filter(residente=residente).count(),
        'puede_reportar': puede_reportar(context['request'].user) and residente.activo,
    }
