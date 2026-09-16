from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from .models import Rol


def rol_requerido(*nombres_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not request.user.roles.exists():
                messages.error(request, 'Tu cuenta no tiene roles asignados.')
                return redirect('dashboard')
            if not request.user.tiene_rol(*nombres_roles):
                messages.error(request, 'No tienes permisos para acceder a esta sección.')
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def superadmin_requerido(view_func):
    return rol_requerido(Rol.SUPERADMIN)(view_func)


def administrador_requerido(view_func):
    """Superadmin o administrador del hogar. Reservado para lo que el
    superadmin sigue pudiendo hacer entre hogares (gestión de usuarios)."""
    return rol_requerido(Rol.SUPERADMIN, Rol.ADMINISTRADOR)(view_func)


def administrador_hogar_requerido(view_func):
    """Solo administrador del hogar — el superadmin YA NO opera residentes,
    infraestructura ni catálogos de un hogar concreto."""
    return rol_requerido(Rol.ADMINISTRADOR)(view_func)


def clinico_requerido(view_func):
    """Administrador del hogar + todos los roles clínicos (incluye jefe de
    enfermería). El superadmin NO tiene acceso clínico/operativo."""
    return rol_requerido(
        Rol.ADMINISTRADOR, *Rol.ROLES_CLINICOS
    )(view_func)


def puede_exportar_requerido(view_func):
    """Quién puede exportar el expediente de un residente en PDF."""
    return rol_requerido(*Rol.ROLES_EXPORTACION)(view_func)


def gestion_diagnostico_requerido(view_func):
    """Quién puede agregar/quitar diagnósticos de un residente existente:
    solo médico y jefe de enfermería (ni siquiera administrador o
    superadmin)."""
    return rol_requerido(*Rol.ROLES_GESTION_DIAGNOSTICOS)(view_func)