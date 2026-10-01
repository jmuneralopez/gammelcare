"""Roles y decoradores del módulo de exámenes.

Viven aquí (y no en usuarios/models.py) para no tocar archivos que otras
ramas modifican a menudo.

- Registrar órdenes, cargar resultados, adendas y correcciones: es
  transcripción de documentos externos (la orden de la EPS, el reporte del
  laboratorio), igual que el registro de tratamientos. Lo hacen el
  administrador del hogar, el médico, el jefe de enfermería y el auxiliar
  de enfermería, que suele ser quien recibe el resultado.
- Revisar un resultado y dejar conducta: acto médico, solo el médico.
- Consultar: cualquier rol clínico más el administrador (clinico_requerido).
"""
from usuarios.decorators import rol_requerido
from usuarios.models import Rol

ROLES_REGISTRO_EXAMENES = [
    Rol.ADMINISTRADOR, Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO,
]
ROLES_REVISION_EXAMENES = [Rol.MEDICO]


def puede_registrar_examenes(usuario):
    return usuario.is_authenticated and usuario.tiene_rol(*ROLES_REGISTRO_EXAMENES)


def puede_revisar_examenes(usuario):
    return usuario.is_authenticated and usuario.tiene_rol(*ROLES_REVISION_EXAMENES)


def registro_examen_requerido(view_func):
    return rol_requerido(*ROLES_REGISTRO_EXAMENES)(view_func)


def revision_examen_requerido(view_func):
    return rol_requerido(*ROLES_REVISION_EXAMENES)(view_func)
