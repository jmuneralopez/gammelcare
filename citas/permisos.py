"""Quién ve y quién agenda citas.

- Ver: el administrador y todos los roles clínicos (el administrador
  coordina transporte y acompañantes).
- Agendar, corregir, cerrar, cancelar y reprogramar: administrador, médico,
  jefe de enfermería, auxiliar de enfermería y trabajo social, que son
  quienes reciben la llamada de la EPS o hablan con la familia.
"""
from usuarios.decorators import rol_requerido
from usuarios.models import Rol

ROLES_VER = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_REGISTRO = [Rol.ADMINISTRADOR, Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO, Rol.TRABAJO_SOCIAL]


def puede_ver(usuario):
    return usuario.is_authenticated and usuario.tiene_rol(*ROLES_VER)


def puede_registrar(usuario):
    return usuario.is_authenticated and usuario.tiene_rol(*ROLES_REGISTRO)


def ver_requerido(view_func):
    return rol_requerido(*ROLES_VER)(view_func)


def registro_requerido(view_func):
    return rol_requerido(*ROLES_REGISTRO)(view_func)
