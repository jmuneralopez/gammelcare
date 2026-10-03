"""Quién hace qué en nutrición e hidratación.

- Ver la planilla de comidas, las dietas y la lista para cocina: administrador
  y todos los roles clínicos.
- Registrar cuánto comió: jefe de enfermería, auxiliar de enfermería y
  nutricionista.
- Registrar líquidos (+1 vaso): los mismos roles del balance de líquidos de
  signos vitales (médico, jefe y auxiliar de enfermería).
- Indicar o cambiar la dieta: médico, nutricionista y jefe de enfermería.
- Configurar comidas y metas del hogar: administrador, jefe de enfermería y
  nutricionista.
- Corregir un registro de ingesta: quien lo hizo, dentro de las 24 horas;
  jefe de enfermería y nutricionista en cualquier momento.
"""
from datetime import timedelta

from django.utils import timezone

from signos import permisos as ps
from usuarios.decorators import rol_requerido
from usuarios.models import Rol

ROLES_VER = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_INGESTA = [Rol.JEFE_ENFERMERIA, Rol.ENFERMERO, Rol.NUTRICIONISTA]
ROLES_LIQUIDOS = ps.ROLES_LIQUIDOS
ROLES_DIETA = [Rol.MEDICO, Rol.NUTRICIONISTA, Rol.JEFE_ENFERMERIA]
ROLES_CONFIGURACION = [Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA, Rol.NUTRICIONISTA]
ROLES_CORREGIR_SIEMPRE = [Rol.JEFE_ENFERMERIA, Rol.NUTRICIONISTA]
HORAS_CORRECCION_AUTOR = 24


def _tiene(usuario, roles):
    return usuario.is_authenticated and usuario.tiene_rol(*roles)


def puede_ingesta(usuario):
    return _tiene(usuario, ROLES_INGESTA)


def puede_liquidos(usuario):
    return _tiene(usuario, ROLES_LIQUIDOS)


def puede_dieta(usuario):
    return _tiene(usuario, ROLES_DIETA)


def puede_configurar(usuario):
    return _tiene(usuario, ROLES_CONFIGURACION)


def puede_corregir(usuario, registro):
    if registro.anulado or not puede_ingesta(usuario):
        return False
    if _tiene(usuario, ROLES_CORREGIR_SIEMPRE):
        return True
    return (registro.registrado_por_id == usuario.pk
            and registro.fecha_registro > timezone.now() - timedelta(hours=HORAS_CORRECCION_AUTOR))


def ver_requerido(f):
    return rol_requerido(*ROLES_VER)(f)


def ingesta_requerido(f):
    return rol_requerido(*ROLES_INGESTA)(f)


def liquidos_requerido(f):
    return rol_requerido(*ROLES_LIQUIDOS)(f)


def dieta_requerido(f):
    return rol_requerido(*ROLES_DIETA)(f)


def configuracion_requerido(f):
    return rol_requerido(*ROLES_CONFIGURACION)(f)
