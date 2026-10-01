"""Quién hace qué con las alertas.

- Cada persona ve las alertas dirigidas a sus roles.
- Administrador y jefe de enfermería pueden ver todas las del hogar, y son
  quienes ajustan los umbrales y activan o desactivan reglas.
- Atender: cualquiera a quien vaya dirigida (o administrador/jefe).
- Descartar ("no aplica"): administrador, jefe de enfermería y médico; un
  aviso manual también lo puede descartar quien lo publicó.
- Publicar avisos: administrador y todos los roles clínicos.
"""
from usuarios.decorators import rol_requerido
from usuarios.models import Rol

ROLES_VER_TODAS = [Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA]
ROLES_CONFIGURAR = [Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA]
ROLES_DESCARTAR = [Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA, Rol.MEDICO]
ROLES_AVISOS = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]
ROLES_PERSONAL = [Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS]


def roles_de(usuario):
    if not hasattr(usuario, '_roles_alertas'):
        usuario._roles_alertas = list(usuario.roles.values_list('nombre', flat=True))
    return usuario._roles_alertas


def puede_ver_todas(usuario):
    return bool(set(roles_de(usuario)) & set(ROLES_VER_TODAS))


def puede_configurar(usuario):
    return bool(set(roles_de(usuario)) & set(ROLES_CONFIGURAR))


def puede_publicar(usuario):
    return bool(set(roles_de(usuario)) & set(ROLES_AVISOS))


def puede_atender(usuario, alerta):
    return alerta.activa and (puede_ver_todas(usuario) or bool(set(roles_de(usuario)) & set(alerta.lista_roles)))


def puede_descartar(usuario, alerta):
    if not alerta.activa:
        return False
    if alerta.origen == alerta.MANUAL and alerta.creada_por_id == usuario.pk:
        return True
    return bool(set(roles_de(usuario)) & set(ROLES_DESCARTAR))


def personal_requerido(view_func):
    return rol_requerido(*ROLES_PERSONAL)(view_func)


def configurar_requerido(view_func):
    return rol_requerido(*ROLES_CONFIGURAR)(view_func)


def publicar_requerido(view_func):
    return rol_requerido(*ROLES_AVISOS)(view_func)
