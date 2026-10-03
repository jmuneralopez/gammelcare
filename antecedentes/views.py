from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente
from usuarios.decorators import clinico_requerido

from . import services
from .forms import AlergiaForm, AntecedenteForm, InactivarForm
from .models import Alergia, Antecedente
from .permisos import inactivacion_requerida, puede_inactivar, puede_registrar, registro_requerido


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=request.user, accion=accion, descripcion=descripcion, ip_address=get_client_ip(request),
    )


def _residente(request, pk):
    return get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)


@login_required
@clinico_requerido
def residente_antecedentes(request, pk):
    residente = _residente(request, pk)
    return render(request, 'antecedentes/residente_antecedentes.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'alergias': residente.alergias.select_related('medicamento', 'registrado_por', 'inactivado_por'),
        'antecedentes': residente.antecedentes.select_related('codigo_cie10', 'registrado_por', 'inactivado_por'),
        'estado': services.estado_alergias(residente),
        'puede_registrar': puede_registrar(request.user),
        'puede_inactivar': puede_inactivar(request.user),
        'inactivar_form': InactivarForm(),
    })


@login_required
@registro_requerido
def alergia_crear(request, pk):
    residente = _residente(request, pk)
    form = AlergiaForm(request.POST or None, hogar=request.user.hogar)
    if request.method == 'POST' and form.is_valid():
        alergia = form.save(commit=False)
        alergia.residente = residente
        services.registrar_alergia(alergia, request.user)
        _auditar(request, RegistroAuditoria.ALERGIA_REGISTRADA, f'Alergia registrada para el residente #{residente.pk}: {alergia.sustancia}')
        messages.success(request, f'Alergia a "{alergia.sustancia}" registrada.')
        return redirect('residente_antecedentes', pk=residente.pk)
    return render(request, 'antecedentes/alergia_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(),
    })


@login_required
@registro_requerido
def antecedente_crear(request, pk):
    residente = _residente(request, pk)
    form = AntecedenteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        antecedente = form.save(commit=False)
        antecedente.residente = residente
        antecedente.registrado_por = request.user
        antecedente.save()
        _auditar(request, RegistroAuditoria.ANTECEDENTE_REGISTRADO, f'Antecedente registrado para el residente #{residente.pk}: {antecedente.descripcion}')
        messages.success(request, 'Antecedente registrado.')
        return redirect('residente_antecedentes', pk=residente.pk)
    return render(request, 'antecedentes/antecedente_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(),
    })


@login_required
@registro_requerido
@require_POST
def declarar_sin_alergias(request, pk):
    residente = _residente(request, pk)
    try:
        services.declarar_sin_alergias(residente, request.user)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        _auditar(request, RegistroAuditoria.SIN_ALERGIAS, f'Declarado "sin alergias conocidas" para el residente #{residente.pk}')
        messages.success(request, 'Registrado: sin alergias conocidas.')
    return redirect('residente_antecedentes', pk=residente.pk)


def _inactivar(request, objeto, residente, accion, etiqueta):
    """`etiqueta` ya viene concordada: "Alergia inactivada", "Antecedente inactivado"."""
    form = InactivarForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Escriba el motivo.')
    elif not objeto.activo:
        messages.info(request, 'Ese registro ya estaba inactivo.')
    else:
        objeto.inactivar(request.user, form.cleaned_data['motivo'])
        _auditar(request, accion, f'{etiqueta} para el residente #{residente.pk}: {objeto} '
                                  f'(motivo: {form.cleaned_data["motivo"][:120]})')
        messages.success(request, f'{etiqueta}. Queda en el historial.')
    return redirect('residente_antecedentes', pk=residente.pk)


@login_required
@inactivacion_requerida
@require_POST
def alergia_inactivar(request, pk):
    alergia = get_object_or_404(Alergia, pk=pk, residente__hogar=request.user.hogar)
    return _inactivar(request, alergia, alergia.residente, RegistroAuditoria.ALERGIA_INACTIVADA, 'Alergia inactivada')


@login_required
@inactivacion_requerida
@require_POST
def antecedente_inactivar(request, pk):
    antecedente = get_object_or_404(Antecedente, pk=pk, residente__hogar=request.user.hogar)
    return _inactivar(request, antecedente, antecedente.residente, RegistroAuditoria.ANTECEDENTE_INACTIVADO, 'Antecedente inactivado')
