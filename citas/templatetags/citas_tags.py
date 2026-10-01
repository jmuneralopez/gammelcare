from django import template
from django.utils import timezone

from ..permisos import puede_registrar

register = template.Library()


@register.inclusion_tag('citas/_resumen_expediente.html', takes_context=True)
def resumen_citas(context, residente):
    abiertas = list(residente.citas.filter(estado='programada').order_by('fecha_hora')[:5])
    ultima = residente.citas.exclude(estado='programada').order_by('-fecha_hora').first()
    return {
        'residente': residente,
        'abiertas': abiertas,
        'ultima': ultima,
        'ahora': timezone.now(),
        'puede_registrar': puede_registrar(context['request'].user),
    }


@register.inclusion_tag('citas/_estado.html')
def estado_cita(cita):
    return {'cita': cita}
