from django import template

from .. import services
from ..permisos import puede_registrar

register = template.Library()


@register.inclusion_tag('antecedentes/_banner_alergias.html')
def banner_alergias(residente, compacto=False):
    """Franja de alergias para el encabezado de cualquier pantalla del
    residente: en rojo si tiene alergias, en verde si se declaró que no
    tiene, y en gris si nadie lo ha registrado todavía."""
    return {
        'residente': residente,
        'alergias': services.alergias_activas(residente),
        'estado': services.estado_alergias(residente),
        'compacto': compacto,
    }


@register.inclusion_tag('antecedentes/_resumen_expediente.html', takes_context=True)
def resumen_antecedentes(context, residente):
    usuario = context['request'].user
    return {
        'residente': residente,
        'alergias': services.alergias_activas(residente),
        'estado': services.estado_alergias(residente),
        'antecedentes': list(residente.antecedentes.filter(activo=True).select_related('codigo_cie10')[:8]),
        'puede_registrar': puede_registrar(usuario),
    }


@register.filter
def alergias_texto(residente):
    """'Penicilina, Mariscos' o '' — para las filas de la ronda."""
    return ', '.join(a.sustancia for a in services.alergias_activas(residente))
