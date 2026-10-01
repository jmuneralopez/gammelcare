"""Quién registra e inactiva alergias y antecedentes.

- Registrar: el administrador (transcribe lo que llega al ingreso) y todos
  los roles clínicos: cualquiera que se entere de una alergia debe poder
  dejarla escrita de inmediato (el nutricionista, de una alergia
  alimentaria; el auxiliar, de una reacción que vio).
- Inactivar (registrado por error o descartado): médico y jefe de
  enfermería, porque quitar una alergia es la acción riesgosa.
"""
from usuarios.decorators import rol_requerido
from usuarios.models import Rol

ROLES_REGISTRO = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_INACTIVACION = [Rol.MEDICO, Rol.JEFE_ENFERMERIA]


def puede_registrar(usuario):
    return usuario.is_authenticated and usuario.tiene_rol(*ROLES_REGISTRO)


def puede_inactivar(usuario):
    return usuario.is_authenticated and usuario.tiene_rol(*ROLES_INACTIVACION)


def registro_requerido(view_func):
    return rol_requerido(*ROLES_REGISTRO)(view_func)


def inactivacion_requerida(view_func):
    return rol_requerido(*ROLES_INACTIVACION)(view_func)
