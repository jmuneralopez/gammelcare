"""Quién hace qué en signos vitales.

- Ver: administrador y todos los roles clínicos.
- Registrar signos y peso: médico, jefe de enfermería, auxiliar de
  enfermería, nutricionista (peso) y fisioterapeuta.
- Registrar líquidos: médico, jefe y auxiliar de enfermería.
- Anular un registro: quien lo hizo, dentro de las 24 horas; médico y jefe
  de enfermería en cualquier momento. Siempre con motivo.
- Rangos de un residente: solo el médico.
- Rangos del hogar: administrador, jefe de enfermería y médico.
"""
from datetime import timedelta

from django.utils import timezone

from usuarios.decorators import rol_requerido
from usuarios.models import Rol

ROLES_VER = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_REGISTRO = [Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO, Rol.NUTRICIONISTA, Rol.FISIOTERAPEUTA]
ROLES_LIQUIDOS = [Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO]
ROLES_ANULAR_SIEMPRE = [Rol.MEDICO, Rol.JEFE_ENFERMERIA]
ROLES_RANGO_RESIDENTE = [Rol.MEDICO]
ROLES_RANGO_HOGAR = [Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA, Rol.MEDICO]
HORAS_ANULACION_AUTOR = 24


def _tiene(usuario, roles):
    return usuario.is_authenticated and usuario.tiene_rol(*roles)


def puede_registrar(usuario):
    return _tiene(usuario, ROLES_REGISTRO)


def puede_registrar_liquidos(usuario):
    return _tiene(usuario, ROLES_LIQUIDOS)


def puede_rango_residente(usuario):
    return _tiene(usuario, ROLES_RANGO_RESIDENTE)


def puede_rango_hogar(usuario):
    return _tiene(usuario, ROLES_RANGO_HOGAR)


def puede_anular(usuario, registro):
    if registro.anulado:
        return False
    if _tiene(usuario, ROLES_ANULAR_SIEMPRE):
        return True
    return (registro.registrado_por_id == usuario.pk
            and registro.fecha_registro > timezone.now() - timedelta(hours=HORAS_ANULACION_AUTOR))


def ver_requerido(f):
    return rol_requerido(*ROLES_VER)(f)


def registro_requerido(f):
    return rol_requerido(*ROLES_REGISTRO)(f)


def liquidos_requerido(f):
    return rol_requerido(*ROLES_LIQUIDOS)(f)


def rango_residente_requerido(f):
    return rol_requerido(*ROLES_RANGO_RESIDENTE)(f)


def rango_hogar_requerido(f):
    return rol_requerido(*ROLES_RANGO_HOGAR)(f)
