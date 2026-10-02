from django import template

from .. import services

register = template.Library()


@register.inclusion_tag('plan_atencion/_resumen_expediente.html')
def resumen_plan(residente):
    v = services.vigente(residente)
    return {'residente': residente, 'vigente': v, 'avance': v.avance() if v else None,
            'borrador': services.borrador(residente), 'falta': services.falta_plan(residente),
            'objetivos': list(v.objetivos.filter(estado='en_curso')[:6]) if v else []}
