from django import template

from usuarios.models import Rol

register = template.Library()


@register.filter
def puede_ver_botiquin(usuario):
    """Quién ve el enlace al botiquín del hogar en el menú: los mismos roles
    que guardan medicamentos (administrador, jefe de enfermería, auxiliar)."""
    return usuario.is_authenticated and usuario.tiene_rol(*Rol.ROLES_INGRESO_MEDICAMENTO)
