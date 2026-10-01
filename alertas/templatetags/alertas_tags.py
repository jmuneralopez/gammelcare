from django import template

from ..models import Alerta

register = template.Library()


@register.inclusion_tag('alertas/_residente.html', takes_context=True)
def alertas_residente(context, residente):
    """Alertas activas del residente, para el expediente."""
    alertas = (Alerta.objects.filter(residente=residente, estado__in=Alerta.ACTIVAS)
               .order_by('fecha_creacion'))
    alertas = sorted(alertas, key=lambda a: (a.orden, a.fecha_creacion))
    return {'alertas': alertas, 'residente': residente, 'request': context['request']}


@register.inclusion_tag('alertas/_gravedad.html')
def gravedad(alerta):
    return {'alerta': alerta}
