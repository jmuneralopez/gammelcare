from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from usuarios.decorators import clinico_requerido
from auditoria.models import RegistroAuditoria
from residentes.models import Residente
from .models import NotaClinica, NotaAclaratoria
from .forms import NotaClinicaForm, NotaAclaratoriaForm


def registrar_auditoria(usuario, accion, descripcion, request):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=usuario,
        accion=accion,
        descripcion=descripcion,
        ip_address=get_client_ip(request)
    )


@login_required
@clinico_requerido
def nota_crear(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    form = NotaClinicaForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        nota = form.save(commit=False)
        nota.residente = residente
        nota.autor = request.user
        nota.save()

        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.CREACION_NOTA,
            descripcion=f'Nota clínica #{nota.pk} creada para residente #{residente.pk}',
            request=request
        )

        messages.success(request, 'Nota clínica registrada correctamente.')
        return redirect('residente_detalle', pk=residente.pk)

    return render(request, 'notas_clinicas/nota_form.html', {
        'form': form,
        'residente': residente,
        'nombre': residente.get_nombre(),
    })


@login_required
@clinico_requerido
def nota_detalle(request, pk):
    nota = get_object_or_404(
        NotaClinica,
        pk=pk,
        residente__hogar=request.user.hogar
    )
    aclaraciones = nota.aclaraciones.all().order_by('fecha_creacion')

    return render(request, 'notas_clinicas/nota_detalle.html', {
        'nota': nota,
        'aclaraciones': aclaraciones,
        'nombre': nota.residente.get_nombre(),
    })


@login_required
@clinico_requerido
def aclaratoria_crear(request, pk):
    nota = get_object_or_404(
        NotaClinica,
        pk=pk,
        residente__hogar=request.user.hogar
    )
    form = NotaAclaratoriaForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        aclaratoria = form.save(commit=False)
        aclaratoria.nota_original = nota
        aclaratoria.autor = request.user
        aclaratoria.save()

        messages.success(request, 'Nota aclaratoria registrada correctamente.')
        return redirect('nota_detalle', pk=nota.pk)

    return render(request, 'notas_clinicas/aclaratoria_form.html', {
        'form': form,
        'nota': nota,
        'nombre': nota.residente.get_nombre(),
    })