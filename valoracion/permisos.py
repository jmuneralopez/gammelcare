"""Quién aplica cada escala (definido en escalas.py), quién ve y quién
configura.

- Ver: administrador y todos los roles clínicos.
- Aplicar: los roles de cada escala (p. ej. Tinetti: médico, fisioterapia,
  jefe de enfermería; Norton y Braden también auxiliar de enfermería).
- Anular: quien la aplicó, el mismo día; médico y jefe de enfermería
  siempre. Con motivo.
- Configurar la periodicidad del hogar: administrador, médico y jefe.
"""
from django.utils import timezone

from usuarios.decorators import rol_requerido
from usuarios.models import Rol

from . import escalas as E

ROLES_VER = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_APLICAR_ALGUNA = sorted({r for e in E.ESCALAS for r in e.roles})
ROLES_ANULAR_SIEMPRE = [Rol.MEDICO, Rol.JEFE_ENFERMERIA]
ROLES_CONFIGURAR = [Rol.ADMINISTRADOR, Rol.MEDICO, Rol.JEFE_ENFERMERIA]


def puede_aplicar(usuario, escala):
    return usuario.is_authenticated and usuario.tiene_rol(*escala.roles)


def escalas_que_aplica(usuario):
    return [e for e in E.ESCALAS if puede_aplicar(usuario, e)]


def puede_anular(usuario, valoracion):
    if valoracion.anulada:
        return False
    if usuario.tiene_rol(*ROLES_ANULAR_SIEMPRE):
        return True
    return (valoracion.registrado_por_id == usuario.pk
            and timezone.localdate(valoracion.fecha_registro) == timezone.localdate())


def puede_configurar(usuario):
    return usuario.is_authenticated and usuario.tiene_rol(*ROLES_CONFIGURAR)


def ver_requerido(f):
    return rol_requerido(*ROLES_VER)(f)


def aplicar_requerido(f):
    return rol_requerido(*ROLES_APLICAR_ALGUNA)(f)


def configurar_requerido(f):
    return rol_requerido(*ROLES_CONFIGURAR)(f)
