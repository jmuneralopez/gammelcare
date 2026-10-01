from django import template
from django.utils import timezone

from .. import parametros as P
from .. import services
from ..permisos import puede_registrar

register = template.Library()

CLASES = {
    P.CRITICO_BAJO: 'text-bg-danger', P.CRITICO_ALTO: 'text-bg-danger',
    P.BAJO: 'text-bg-warning', P.ALTO: 'text-bg-warning', P.NORMAL: 'text-bg-light border',
}


@register.filter
def clase_signo(interpretacion):
    return CLASES.get(interpretacion, 'text-bg-light border')


@register.filter
def etiqueta_signo(interpretacion):
    return P.ETIQUETAS.get(interpretacion, '')


@register.filter
def valor_signo(dato):
    if not dato:
        return '—'
    p = dato['parametro']
    return f'{dato["valor"]:.{p.decimales}f}'


@register.filter
def dato(diccionario, clave):
    return (diccionario or {}).get(clave)


@register.inclusion_tag('signos/_resumen_expediente.html', takes_context=True)
def resumen_signos(context, residente):
    control = services.ultimo_control(residente)
    lectura = services.interpretar_control(control) if control else {}
    dias_dep, _ = services.dias_sin_deposicion(residente)
    return {
        'residente': residente,
        'control': control,
        'lectura': lectura,
        'parametros': P.PARAMETROS,
        'dias_sin_deposicion': dias_dep,
        'horas': int((timezone.now() - control.fecha_hora).total_seconds() // 3600) if control else None,
        'puede_registrar': puede_registrar(context['request'].user) and residente.activo,
    }


@register.filter
def partir(texto):
    """'a b c'|partir → ['a', 'b', 'c'] (para recorrer listas fijas en plantillas)."""
    return texto.split()
