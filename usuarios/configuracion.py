"""Página única de configuración: reúne las pantallas de configuración de
cada módulo que el usuario puede abrir, para no llenar el menú con ellas."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse

from usuarios.models import Rol


def opciones(usuario):
    if not usuario.is_authenticated or not usuario.hogar_id:
        return []
    from alertas import permisos as al
    from eventos import permisos as ev
    from nutricion import permisos as nu
    from signos import permisos as si
    from valoracion import permisos as va

    candidatas = [
        ('Alertas', 'Umbrales de cada aviso y reglas activas.', 'alertas_configuracion', 'bi-bell', al.ROLES_CONFIGURAR),
        ('Eventos adversos', 'Si se identifica a quien reporta y la vigilancia después de una caída.',
         'eventos_configuracion', 'bi-exclamation-diamond', ev.ROLES_CONFIGURAR),
        ('Medicamentos', 'Semáforo de vencimiento, horas estándar, ronda y anulaciones.', 'medicamentos_configuracion',
         'bi-capsule', [Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA]),
        ('Comidas e hidratación', 'Comidas que sirve el hogar, sus horas, el vaso y la meta de líquidos.',
         'nutricion_configuracion', 'bi-cup-hot', nu.ROLES_CONFIGURACION),
        ('Signos vitales', 'Rangos normales y críticos del hogar.', 'signos_rangos_hogar', 'bi-heart-pulse',
         si.ROLES_RANGO_HOGAR),
        ('Valoración geriátrica', 'Escalas exigidas y cada cuánto se repiten.', 'valoracion_configuracion',
         'bi-clipboard2-pulse', va.ROLES_CONFIGURAR),
        ('EPS', 'Catálogo de EPS del hogar.', 'eps_lista', 'bi-hospital', [Rol.ADMINISTRADOR]),
        ('Ambulancias', 'Servicios de ambulancia del hogar.', 'ambulancia_lista', 'bi-truck', [Rol.ADMINISTRADOR]),
    ]
    return [{'titulo': t, 'descripcion': d, 'url': reverse(u), 'icono': i}
            for t, d, u, i, roles in candidatas if usuario.tiene_rol(*roles)]


@login_required
def configuracion(request):
    lista = opciones(request.user)
    if not lista:
        return HttpResponseForbidden('No tiene opciones de configuración.')
    return render(request, 'usuarios/configuracion.html', {'opciones': lista})
