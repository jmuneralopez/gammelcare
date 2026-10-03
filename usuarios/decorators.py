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
            # Todo lo que no sea superadmin debe pertenecer a un hogar. Sin
            # este chequeo, una cuenta que quedó sin hogar (por un bug, una
            # migración incompleta, etc.) llega hasta el cuerpo de la vista
            # y revienta con un error de base de datos en cualquier pantalla
            # que guarde algo con `hogar=request.user.hogar` (p. ej. crear un
            # departamento) — aquí se corta de raíz, para TODAS las vistas
            # que usan rol_requerido, con un mensaje claro en vez de un 500.
            if not request.user.es_superadmin() and not request.user.hogar_id:
                messages.error(
                    request,
                    'Tu cuenta no tiene un hogar asignado. Contacta al '
                    'administrador del sistema para que te asigne uno antes '
                    'de continuar.'
                )
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
    administrador, médico y jefe de enfermería."""
    return rol_requerido(*Rol.ROLES_GESTION_DIAGNOSTICOS)(view_func)


# ── Módulo de medicamentos ──────────────────────────────────────

def registro_tratamiento_requerido(view_func):
    """Transcribir, suspender y reemplazar tratamientos formulados:
    administrador, médico y jefe de enfermería."""
    return rol_requerido(*Rol.ROLES_REGISTRO_TRATAMIENTO)(view_func)


def ingreso_medicamento_requerido(view_func):
    """Registrar la entrada de medicamentos que trae la familia:
    administrador, jefe de enfermería y enfermero/auxiliar."""
    return rol_requerido(*Rol.ROLES_INGRESO_MEDICAMENTO)(view_func)


def ronda_requerido(view_func):
    """Ronda de medicamentos: solo enfermería (jefe y auxiliares)."""
    return rol_requerido(*Rol.ROLES_RONDA)(view_func)


def administracion_requerido(view_func):
    """Registrar suministro y no administración: médico, jefe de
    enfermería y enfermero/auxiliar — el administrador nunca toca al
    residente."""
    return rol_requerido(*Rol.ROLES_ADMINISTRACION)(view_func)


def ajuste_inventario_requerido(view_func):
    """Ajustar saldos, descartar lotes vencidos y devolver a la familia:
    el acto más restringido del módulo — solo administrador y jefe de
    enfermería (ver plan-modulo-medicamentos.md, sección 4.3-a)."""
    return rol_requerido(*Rol.ROLES_AJUSTE_INVENTARIO)(view_func)