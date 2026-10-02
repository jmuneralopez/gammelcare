"""Quién hace qué en el plan de atención.

- Ver: administrador y todos los roles clínicos.
- Elaborar (crear el borrador, escribir el resumen, agregar objetivos de su
  área): médico, jefe de enfermería, fisioterapia, nutrición, psicología,
  trabajo social y terapia ocupacional.
- Activar el plan (lo vuelve vigente) y revisar (crea la siguiente versión):
  médico y jefe de enfermería.
- Registrar seguimiento de objetivos: todos los roles clínicos, incluida la
  auxiliar de enfermería, que es quien ve el día a día.
"""
from usuarios.decorators import rol_requerido
from usuarios.models import Rol

ROLES_VER = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_ELABORAR = [Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.FISIOTERAPEUTA, Rol.NUTRICIONISTA, Rol.PSICOLOGO,
                  Rol.TRABAJO_SOCIAL, Rol.TERAPEUTA_OCUPACIONAL]
ROLES_ACTIVAR = [Rol.MEDICO, Rol.JEFE_ENFERMERIA]
ROLES_SEGUIMIENTO = list(Rol.ROLES_CLINICOS)


def _tiene(u, roles):
    return u.is_authenticated and u.tiene_rol(*roles)


def puede_elaborar(u):
    return _tiene(u, ROLES_ELABORAR)


def puede_activar(u):
    return _tiene(u, ROLES_ACTIVAR)


def puede_seguimiento(u):
    return _tiene(u, ROLES_SEGUIMIENTO)


def ver_requerido(f):
    return rol_requerido(*ROLES_VER)(f)


def elaborar_requerido(f):
    return rol_requerido(*ROLES_ELABORAR)(f)


def activar_requerido(f):
    return rol_requerido(*ROLES_ACTIVAR)(f)


def seguimiento_requerido(f):
    return rol_requerido(*ROLES_SEGUIMIENTO)(f)
