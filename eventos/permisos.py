"""Quién hace qué en eventos adversos.

- Reportar un evento: todo el personal clínico y el administrador (por
  ejemplo, una fuga la puede ver cualquiera).
- Ver todos los eventos, la bandeja e indicadores: jefe de enfermería, médico
  y administrador. El resto del personal ve los eventos en el expediente del
  residente y los que reportó con su nombre.
- Analizar y cerrar un evento: jefe de enfermería y médico.
- Registrar la vigilancia después de una caída: médico, jefe y auxiliar de
  enfermería.
- Configurar (modo de reporte y vigilancia): administrador y jefe de enfermería.
- Quién reportó: según el modo del hogar (identificado: jefe, médico y
  administrador; confidencial: solo el jefe de enfermería; anónimo: nadie si
  quien reportó no dejó su nombre).
"""
from usuarios.decorators import rol_requerido
from usuarios.models import Rol

from .models import ConfiguracionEventos

ROLES_REPORTAR = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_SUPERVISION = [Rol.JEFE_ENFERMERIA, Rol.MEDICO, Rol.ADMINISTRADOR]
ROLES_ANALIZAR = [Rol.JEFE_ENFERMERIA, Rol.MEDICO]
ROLES_VIGILANCIA = [Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO]
ROLES_CONFIGURAR = [Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA]


def _tiene(usuario, roles):
    return usuario.is_authenticated and usuario.tiene_rol(*roles)


def puede_reportar(usuario):
    return _tiene(usuario, ROLES_REPORTAR)


def puede_supervisar(usuario):
    return _tiene(usuario, ROLES_SUPERVISION)


def puede_analizar(usuario):
    return _tiene(usuario, ROLES_ANALIZAR)


def puede_vigilancia(usuario):
    return _tiene(usuario, ROLES_VIGILANCIA)


def puede_configurar(usuario):
    return _tiene(usuario, ROLES_CONFIGURAR)


def ve_quien_reporto(usuario, evento, config=None):
    if evento.anonimo or evento.reportado_por_id is None:
        return False
    if evento.reportado_por_id == usuario.pk:
        return True
    config = config or ConfiguracionEventos.para_hogar(evento.hogar)
    if config.modo_reporte == ConfiguracionEventos.IDENTIFICADO:
        return puede_supervisar(usuario)
    return _tiene(usuario, [Rol.JEFE_ENFERMERIA])


def reportar_requerido(f):
    return rol_requerido(*ROLES_REPORTAR)(f)


def supervision_requerido(f):
    return rol_requerido(*ROLES_SUPERVISION)(f)


def analizar_requerido(f):
    return rol_requerido(*ROLES_ANALIZAR)(f)


def vigilancia_requerido(f):
    return rol_requerido(*ROLES_VIGILANCIA)(f)


def configurar_requerido(f):
    return rol_requerido(*ROLES_CONFIGURAR)(f)
