from django import template

from .. import services
from ..models import ICONOS, TIPOS_CUIDADO, Herida
from ..permisos import puede_heridas, puede_registrar_cuidados

register = template.Library()


@register.filter
def hace(minutos):
    """'hace 2 h 15 min' a partir de minutos."""
    if minutos is None:
        return 'sin registros'
    if minutos < 1:
        return 'hace un momento'
    if minutos < 60:
        return f'hace {minutos} min'
    h, m = divmod(minutos, 60)
    if h >= 48:
        return f'hace {h // 24} días'
    return f'hace {h} h' + (f' {m} min' if m and h < 6 else '')


@register.filter
def get_item(diccionario, clave):
    return (diccionario or {}).get(clave)


@register.filter
def icono_cuidado(tipo):
    return ICONOS.get(tipo, 'bi-check2')


@register.inclusion_tag('cuidados/_resumen_expediente.html', takes_context=True)
def resumen_cuidados(context, residente):
    usuario = context['request'].user
    plan = services.plan_de(residente)
    _, _, inicio, _ = services.turno_actual()
    return {
        'residente': residente, 'plan': plan, 'plan_guardado': bool(plan.pk),
        'celdas': [services.celda(residente, plan, t, inicio) for t in plan.tipos()],
        'nombres': dict(TIPOS_CUIDADO),
        'heridas': list(residente.heridas.filter(estado=Herida.ACTIVA)),
        'puede_registrar': puede_registrar_cuidados(usuario) and residente.activo,
        'puede_heridas': puede_heridas(usuario) and residente.activo,
    }
