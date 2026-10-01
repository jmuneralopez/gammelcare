from django import template

from ..models import Examen, ValorResultado
from ..permisos import puede_registrar_examenes, puede_revisar_examenes

register = template.Library()


@register.inclusion_tag('examenes/_resumen_expediente.html', takes_context=True)
def resumen_examenes(context, residente):
    """Tarjeta de exámenes para el expediente del residente. Es un tag para
    que el expediente solo necesite una línea y no dependa de la vista."""
    usuario = context['request'].user
    examenes = list(residente.examenes.exclude(estado=Examen.CANCELADO).order_by('-fecha_registro')[:5])
    return {
        'residente': residente,
        'examenes': examenes,
        'pendientes': residente.examenes.filter(estado=Examen.PENDIENTE).count(),
        'por_revisar': residente.examenes.filter(estado=Examen.RESULTADO).count(),
        'puede_registrar': puede_registrar_examenes(usuario),
    }


ETIQUETAS = {
    ValorResultado.CRITICO_BAJO: ('Crítico bajo', 'danger'),
    ValorResultado.CRITICO_ALTO: ('Crítico alto', 'danger'),
    ValorResultado.BAJO: ('Bajo', 'warning'),
    ValorResultado.ALTO: ('Alto', 'warning'),
    ValorResultado.NORMAL: ('Normal', 'success'),
    ValorResultado.SIN_RANGO: ('Sin rango', 'secondary'),
}


@register.inclusion_tag('examenes/_interpretacion.html')
def interpretacion(valor):
    texto, color = ETIQUETAS[valor.interpretacion()]
    return {'texto': texto, 'color': color}


@register.inclusion_tag('examenes/_estado.html')
def estado_examen(examen):
    colores = {
        Examen.PENDIENTE: 'secondary',
        Examen.RESULTADO: 'warning',
        Examen.REVISADO: 'success',
        Examen.CANCELADO: 'light',
    }
    return {'examen': examen, 'color': colores[examen.estado]}
