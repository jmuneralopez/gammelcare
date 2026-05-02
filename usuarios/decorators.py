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
    return rol_requerido(Rol.SUPERADMIN, Rol.ADMINISTRADOR)(view_func)


def clinico_requerido(view_func):
    return rol_requerido(
        Rol.SUPERADMIN, Rol.ADMINISTRADOR,
        Rol.MEDICO, Rol.ENFERMERO, Rol.FISIOTERAPEUTA,
        Rol.NUTRICIONISTA, Rol.PSICOLOGO,
        Rol.TRABAJO_SOCIAL, Rol.TERAPEUTA_OCUPACIONAL
    )(view_func)


def puede_exportar_requerido(view_func):
    return rol_requerido(
        Rol.SUPERADMIN, Rol.ADMINISTRADOR, Rol.MEDICO
    )(view_func)