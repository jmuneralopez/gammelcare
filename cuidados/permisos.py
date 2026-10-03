"""Quién hace qué en cuidados diarios y heridas.

- Ver: administrador y todos los roles clínicos.
- Registrar cuidados (baño, pañal, posición, higiene oral, movilización):
  jefe de enfermería, auxiliar de enfermería y fisioterapeuta.
- Definir el plan de cuidados de un residente: médico y jefe de enfermería.
- Registrar una herida y sus curaciones: médico, jefe y auxiliar de enfermería.
- Cerrar una herida: médico y jefe de enfermería.
- Anular un registro: quien lo hizo, dentro de las 24 horas; médico y jefe
  de enfermería en cualquier momento. Siempre con motivo.
"""
from datetime import timedelta

from django.utils import timezone

from usuarios.decorators import rol_requerido
from usuarios.models import Rol

ROLES_VER = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_CUIDADOS = [Rol.JEFE_ENFERMERIA, Rol.ENFERMERO, Rol.FISIOTERAPEUTA]
ROLES_PLAN = [Rol.MEDICO, Rol.JEFE_ENFERMERIA]
ROLES_HERIDAS = [Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO]
ROLES_CERRAR_HERIDA = [Rol.MEDICO, Rol.JEFE_ENFERMERIA]
ROLES_ANULAR_SIEMPRE = [Rol.MEDICO, Rol.JEFE_ENFERMERIA]
HORAS_ANULACION_AUTOR = 24


def _tiene(usuario, roles):
    return usuario.is_authenticated and usuario.tiene_rol(*roles)


def puede_registrar_cuidados(usuario):
    return _tiene(usuario, ROLES_CUIDADOS)


def puede_plan(usuario):
    return _tiene(usuario, ROLES_PLAN)


def puede_heridas(usuario):
    return _tiene(usuario, ROLES_HERIDAS)


def puede_cerrar_herida(usuario):
    return _tiene(usuario, ROLES_CERRAR_HERIDA)


def puede_anular(usuario, registro):
    if registro.anulado:
        return False
    if _tiene(usuario, ROLES_ANULAR_SIEMPRE):
        return True
    return (registro.registrado_por_id == usuario.pk
            and registro.fecha_registro > timezone.now() - timedelta(hours=HORAS_ANULACION_AUTOR))


def ver_requerido(f):
    return rol_requerido(*ROLES_VER)(f)


def cuidados_requerido(f):
    return rol_requerido(*ROLES_CUIDADOS)(f)


def plan_requerido(f):
    return rol_requerido(*ROLES_PLAN)(f)


def heridas_requerido(f):
    return rol_requerido(*ROLES_HERIDAS)(f)


def cerrar_herida_requerido(f):
    return rol_requerido(*ROLES_CERRAR_HERIDA)(f)
