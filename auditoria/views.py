from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils.dateparse import parse_date

from usuarios.decorators import administrador_requerido
from usuarios.models import Usuario, Rol
from .models import RegistroAuditoria


@login_required
@administrador_requerido
def auditoria_lista(request):
    """Lista de auditoría. El superadmin ve TODOS los registros; el
    administrador del hogar ve solo los de usuarios de SU hogar (o
    generados por ellos, ya que `usuario` en RegistroAuditoria es quien
    ejecutó la acción). Nadie más llega aquí: administrador_requerido es
    exactamente "superadmin o administrador"."""
    if request.user.es_superadmin():
        registros = RegistroAuditoria.objects.select_related('usuario', 'usuario__hogar').all()
        usuarios_filtro = Usuario.objects.all().order_by('hogar__nombre', 'last_name', 'first_name')
    else:
        registros = RegistroAuditoria.objects.select_related('usuario', 'usuario__hogar').filter(
            usuario__hogar=request.user.hogar
        ).exclude(usuario__roles__nombre=Rol.SUPERADMIN)
        usuarios_filtro = Usuario.objects.filter(hogar=request.user.hogar).exclude(
            roles__nombre=Rol.SUPERADMIN
        ).order_by('last_name', 'first_name')

    usuario_id = request.GET.get('usuario', '')
    accion = request.GET.get('accion', '')
    desde = request.GET.get('desde', '')
    hasta = request.GET.get('hasta', '')

    if usuario_id:
        registros = registros.filter(usuario_id=usuario_id)
    if accion:
        registros = registros.filter(accion=accion)
    if desde:
        fecha_desde = parse_date(desde)
        if fecha_desde:
            registros = registros.filter(timestamp__date__gte=fecha_desde)
    if hasta:
        fecha_hasta = parse_date(hasta)
        if fecha_hasta:
            registros = registros.filter(timestamp__date__lte=fecha_hasta)

    registros = registros.order_by('-timestamp')

    paginator = Paginator(registros, 50)
    registros_pagina = paginator.get_page(request.GET.get('page'))

    return render(request, 'auditoria/auditoria_lista.html', {
        'registros': registros_pagina,
        'usuarios_filtro': usuarios_filtro,
        'acciones': RegistroAuditoria.ACCIONES,
        'usuario_seleccionado': usuario_id,
        'accion_seleccionada': accion,
        'desde': desde,
        'hasta': hasta,
    })
