from django import template

from .. import services
from ..models import ConfiguracionNutricion, RegistroIngesta
from ..permisos import puede_dieta

register = template.Library()

CLASES = {
    RegistroIngesta.TODO: 'text-bg-success', RegistroIngesta.TRES_CUARTOS: 'text-bg-success',
    RegistroIngesta.MITAD: 'text-bg-warning', RegistroIngesta.CUARTO: 'text-bg-danger',
    RegistroIngesta.NADA: 'text-bg-danger', RegistroIngesta.RECHAZO: 'text-bg-danger',
    RegistroIngesta.AUSENTE: 'text-bg-secondary',
}
CORTO = {
    RegistroIngesta.TODO: 'Todo', RegistroIngesta.TRES_CUARTOS: '¾', RegistroIngesta.MITAD: '½',
    RegistroIngesta.CUARTO: '¼', RegistroIngesta.NADA: 'Nada', RegistroIngesta.RECHAZO: 'Rechazó',
    RegistroIngesta.AUSENTE: 'No estaba',
}


@register.filter
def clase_consumo(consumo):
    return CLASES.get(consumo, 'text-bg-light border')


@register.filter
def corto_consumo(consumo):
    return CORTO.get(consumo, consumo)


@register.filter
def porcentaje_de(valor, total):
    try:
        return min(100, round(100 * int(valor) / int(total)))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.inclusion_tag('nutricion/_resumen_expediente.html', takes_context=True)
def resumen_nutricion(context, residente):
    config = ConfiguracionNutricion.para_hogar(residente.hogar)
    dieta = services.dieta_vigente(residente)
    cuadricula = services.cuadricula(residente, config, dias=3)
    return {
        'residente': residente, 'dieta': dieta, 'alergias': services.alergias_alimentarias(residente),
        'hoy': cuadricula[0], 'comidas': config.comidas(), 'meta': services.meta_liquidos(residente, dieta, config),
        'promedio': services.promedio([c for f in cuadricula for c in f['celdas'] if c]),
        'puede_dieta': puede_dieta(context['request'].user) and residente.activo,
    }
