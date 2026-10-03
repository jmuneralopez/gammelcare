from django import template

from usuarios.models import Rol

register = template.Library()


@register.filter
def puede_ver_botiquin(usuario):
    """Quién ve el enlace al botiquín del hogar en el menú: los mismos roles
    que guardan medicamentos (administrador, jefe de enfermería, auxiliar)."""
    return usuario.is_authenticated and usuario.tiene_rol(*Rol.ROLES_INGRESO_MEDICAMENTO)


@register.filter
def puede_configurar_medicamentos(usuario):
    return usuario.is_authenticated and usuario.tiene_rol(Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA)


@register.inclusion_tag('medicamentos/_resumen_expediente.html', takes_context=True)
def resumen_medicamentos(context, residente):
    from .. import services
    from ..models import Prescripcion
    usuario = context['request'].user
    return {
        'residente': residente,
        'hoy': services.tomas_de_hoy(residente) if residente.activo else None,
        'ordenes': Prescripcion.objects.filter(residente=residente, estado=Prescripcion.ACTIVA).count(),
        'puede_devolver': usuario.tiene_rol(*Rol.ROLES_AJUSTE_INVENTARIO),
    }


@register.inclusion_tag('medicamentos/_indicador_tarjeta.html')
def indicador_medicamentos(residente):
    """Indicador para la tarjeta de 'Atención a Residentes'."""
    from .. import services
    return {'residente': residente, 'hoy': services.tomas_de_hoy(residente)}


@register.inclusion_tag('medicamentos/_turno_nota.html')
def medicamentos_del_turno(residente, horas=12):
    """Panel de solo lectura en la nota clínica: lo suministrado y no
    suministrado en las últimas horas y lo pendiente de hoy, con un botón
    para copiar el resumen en el texto de la nota."""
    from django.utils import timezone

    from .. import services
    registros = list(services.suministros_recientes(residente, horas))
    filas, _ = services.hoja_del_dia(residente)
    ahora = timezone.now()
    pendientes = [f for f in filas if f['pendiente'] and f['fecha_programada'] <= ahora]
    lineas = []
    for a in registros:
        hora = timezone.localtime(a.fecha_administracion).strftime('%H:%M')
        if a.estado == a.ADMINISTRADO:
            lineas.append(f'{hora} {a.prescripcion.medicamento}: suministrado ({a.cantidad_administrada}).')
        else:
            lineas.append(f'{hora} {a.prescripcion.medicamento}: no suministrado — {a.get_motivo_no_administracion_display()}.')
    for f in pendientes:
        lineas.append(f'{timezone.localtime(f["fecha_programada"]):%H:%M} {f["prescripcion"].medicamento}: pendiente sin registrar.')
    return {'residente': residente, 'registros': registros, 'pendientes': pendientes, 'horas': horas,
            'texto': 'Medicamentos del turno: ' + ' '.join(lineas) if lineas else ''}
