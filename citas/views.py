from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from gammelcare.archivos_privados import tipo_por_extension
from residentes.models import Residente

from . import services
from .forms import CancelarForm, CerrarForm, CitaForm, ReprogramarForm
from .models import Cita
from .permisos import puede_registrar, registro_requerido, ver_requerido


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=request.user, accion=accion, descripcion=descripcion, ip_address=get_client_ip(request),
    )


def _cita(request, pk):
    return get_object_or_404(Cita.objects.select_related('residente'), pk=pk, residente__hogar=request.user.hogar)


@login_required
@ver_requerido
def agenda(request):
    """Agenda del hogar: citas y demás fechas pendientes (revisiones de plan,
    escalas por aplicar, próximas curaciones, órdenes que terminan), por día.
    Lo vencido se muestra hoy."""
    from residentes import calendario
    dias = request.GET.get('dias', '7')
    dias = int(dias) if dias in ('1', '7', '30', '90') else 7
    ver = 'citas' if request.GET.get('ver') == 'citas' else 'todo'
    hoy = timezone.localdate()
    proximas = services.proximas(request.user.hogar, dias=dias)
    por_dia = {}
    for c in proximas:
        por_dia.setdefault(timezone.localdate(c.fecha_hora), {'citas': [], 'otros': []})['citas'].append(c)
    if ver == 'todo':
        capas = [c for c in calendario.CAPAS_AGENDA if c != 'citas']
        for e in calendario.agenda_hogar(request.user.hogar, hoy, hoy + timedelta(days=dias - 1), capas):
            por_dia.setdefault(e.fecha, {'citas': [], 'otros': []})['otros'].append(e)
    sin_cierre = [c for c in services.sin_cierre(request.user.hogar) if timezone.localdate(c.fecha_hora) < hoy]
    return render(request, 'citas/agenda.html', {
        'por_dia': [(d, dict(g, total=len(g['citas']) + len(g['otros']))) for d, g in sorted(por_dia.items())],
        'sin_cierre': sin_cierre,
        'dias': dias,
        'ver': ver,
        'hoy': hoy,
        'manana': hoy + timedelta(days=1),
        'puede_registrar': puede_registrar(request.user),
        'colores': calendario.COLOR,
        'nombres_capa': calendario.NOMBRE_CAPA,
    })


@login_required
@ver_requerido
def residente_citas(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    citas = residente.citas.select_related('cerrada_por', 'registrado_por')
    return render(request, 'citas/residente_citas.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'abiertas': [c for c in citas if c.abierta],
        'historial': sorted((c for c in citas if not c.abierta), key=lambda c: c.fecha_hora, reverse=True),
        'puede_registrar': puede_registrar(request.user),
    })


@login_required
@registro_requerido
def cita_crear(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar, activo=True)
    form = CitaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cita = form.save(commit=False)
        cita.residente = residente
        cita.registrado_por = request.user
        cita.save()
        _auditar(request, RegistroAuditoria.CITA_REGISTRADA, f'Cita agendada para el residente #{residente.pk}: {cita}')
        messages.success(request, 'Cita agendada.')
        return redirect('citas_residente', pk=residente.pk)
    return render(request, 'citas/cita_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(), 'cita': None,
    })


@login_required
@registro_requerido
def cita_editar(request, pk):
    cita = _cita(request, pk)
    if not cita.abierta:
        messages.error(request, 'Solo se corrigen citas programadas.')
        return redirect('cita_detalle', pk=cita.pk)
    form = CitaForm(request.POST or None, instance=cita)
    if request.method == 'POST' and form.is_valid():
        form.save()
        _auditar(request, RegistroAuditoria.CITA_MODIFICADA,
                 f'Cita #{cita.pk} corregida (residente #{cita.residente_id}): campos {", ".join(form.changed_data) or "ninguno"}')
        messages.success(request, 'Cita corregida.')
        return redirect('cita_detalle', pk=cita.pk)
    return render(request, 'citas/cita_form.html', {
        'form': form, 'residente': cita.residente, 'nombre': cita.nombre_residente, 'cita': cita,
    })


@login_required
@ver_requerido
def cita_detalle(request, pk):
    cita = _cita(request, pk)
    return render(request, 'citas/cita_detalle.html', {
        'cita': cita,
        'residente': cita.residente,
        'nombre': cita.nombre_residente,
        'puede_registrar': puede_registrar(request.user),
        'cerrar_form': CerrarForm(),
        'cancelar_form': CancelarForm(),
        'reprogramar_form': ReprogramarForm(),
        'puede_cerrar_hoy': timezone.localdate(cita.fecha_hora) <= timezone.localdate(),
    })


def _volver_con_errores(request, cita, nombre_form, form):
    contexto = {
        'cita': cita, 'residente': cita.residente, 'nombre': cita.nombre_residente,
        'puede_registrar': True,
        'cerrar_form': CerrarForm(), 'cancelar_form': CancelarForm(), 'reprogramar_form': ReprogramarForm(),
        'puede_cerrar_hoy': timezone.localdate(cita.fecha_hora) <= timezone.localdate(),
        'abrir': nombre_form,
    }
    contexto[f'{nombre_form}_form'] = form
    return render(request, 'citas/cita_detalle.html', contexto, status=400)


@login_required
@registro_requerido
@require_POST
def cita_cerrar(request, pk):
    cita = _cita(request, pk)
    form = CerrarForm(request.POST, request.FILES)
    if not form.is_valid():
        return _volver_con_errores(request, cita, 'cerrar', form)
    try:
        services.cerrar(cita, request.user, form.cleaned_data['estado'], form.cleaned_data['resumen'],
                        form.cleaned_data.get('archivo'))
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect('cita_detalle', pk=cita.pk)
    cita.refresh_from_db()
    _auditar(request, RegistroAuditoria.CITA_CERRADA,
             f'Cita #{cita.pk} cerrada como "{cita.get_estado_display()}" (residente #{cita.residente_id})')
    messages.success(request, f'Cita registrada como "{cita.get_estado_display().lower()}".')
    return redirect('cita_detalle', pk=cita.pk)


@login_required
@registro_requerido
@require_POST
def cita_cancelar(request, pk):
    cita = _cita(request, pk)
    form = CancelarForm(request.POST)
    if not form.is_valid():
        return _volver_con_errores(request, cita, 'cancelar', form)
    try:
        services.cancelar(cita, request.user, form.cleaned_data['motivo'])
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect('cita_detalle', pk=cita.pk)
    _auditar(request, RegistroAuditoria.CITA_CANCELADA,
             f'Cita #{cita.pk} cancelada (residente #{cita.residente_id}): {form.cleaned_data["motivo"][:150]}')
    messages.success(request, 'Cita cancelada. Queda en el historial.')
    return redirect('citas_residente', pk=cita.residente_id)


@login_required
@registro_requerido
@require_POST
def cita_reprogramar(request, pk):
    cita = _cita(request, pk)
    form = ReprogramarForm(request.POST)
    if not form.is_valid():
        return _volver_con_errores(request, cita, 'reprogramar', form)
    try:
        nueva = services.reprogramar(cita, request.user, form.cleaned_data['fecha_hora'],
                                     form.cleaned_data['motivo'], form.cleaned_data['lugar'])
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect('cita_detalle', pk=cita.pk)
    _auditar(request, RegistroAuditoria.CITA_MODIFICADA,
             f'Cita #{cita.pk} reprogramada como cita #{nueva.pk} (residente #{cita.residente_id}): '
             f'{form.cleaned_data["motivo"][:150]}')
    messages.success(request, f'Cita reprogramada para el {timezone.localtime(nueva.fecha_hora):%d/%m/%Y a las %H:%M}.')
    return redirect('cita_detalle', pk=nueva.pk)


@login_required
@ver_requerido
def cita_soporte_ver(request, pk):
    cita = _cita(request, pk)
    if not cita.archivo_soporte:
        raise Http404('Esta cita no tiene soporte.')
    try:
        handle = cita.archivo_soporte.open('rb')
    except FileNotFoundError:
        raise Http404('El archivo no se encuentra en el almacenamiento.')
    _auditar(request, RegistroAuditoria.CONSULTA_EXPEDIENTE,
             f'Consulta del soporte de la cita #{cita.pk} (residente #{cita.residente_id})')
    nombre = cita.archivo_soporte.name.rsplit('/', 1)[-1]
    respuesta = FileResponse(handle, content_type=tipo_por_extension(nombre), filename=nombre)
    respuesta['X-Content-Type-Options'] = 'nosniff'
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta
