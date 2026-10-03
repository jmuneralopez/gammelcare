from django import template

from .. import secciones as S

register = template.Library()


@register.inclusion_tag('ayuda/_ayuda.html', takes_context=True)
def ayuda_contextual(context):
    request = context.get('request')
    usuario = getattr(request, 'user', None)
    match = getattr(request, 'resolver_match', None)
    if not usuario or not usuario.is_authenticated or not match:
        return {'seccion': None}
    codigo = S.SECCION_POR_PANTALLA.get(match.url_name)
    sec = S.seccion(codigo) if codigo else None
    if not sec:
        return {'seccion': None}
    puede, no_puede, mis_roles = S.para_usuario(sec, usuario)
    return {'seccion': sec, 'puede': puede, 'no_puede': no_puede, 'mis_roles': mis_roles}
