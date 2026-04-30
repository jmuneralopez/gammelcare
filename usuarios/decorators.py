from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps


def rol_requerido(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not request.user.rol:
                messages.error(request, 'Tu cuenta no tiene un rol asignado.')
                return redirect('dashboard')
            if request.user.rol.nombre not in roles:
                messages.error(request, 'No tienes permisos para acceder a esta sección.')
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def superadmin_requerido(view_func):
    return rol_requerido('superadmin')(view_func)


def administrador_requerido(view_func):
    return rol_requerido('superadmin', 'administrador')(view_func)


def clinico_requerido(view_func):
    return rol_requerido('superadmin', 'administrador', 'clinico')(view_func)