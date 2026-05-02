from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from usuarios.decorators import superadmin_requerido
from .models import Hogar
from .forms import HogarForm


@login_required
@superadmin_requerido
def hogar_lista(request):
    hogares = Hogar.objects.all().order_by('nombre')
    return render(request, 'hogares/hogar_lista.html', {
        'hogares': hogares
    })


@login_required
@superadmin_requerido
def hogar_crear(request):
    form = HogarForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Hogar creado correctamente.')
        return redirect('hogar_lista')
    return render(request, 'hogares/hogar_form.html', {
        'form': form,
        'titulo': 'Nuevo Hogar',
        'accion': 'Crear'
    })


@login_required
@superadmin_requerido
def hogar_editar(request, pk):
    hogar = get_object_or_404(Hogar, pk=pk)
    form = HogarForm(request.POST or None, instance=hogar)
    if form.is_valid():
        form.save()
        messages.success(request, 'Hogar actualizado correctamente.')
        return redirect('hogar_lista')
    return render(request, 'hogares/hogar_form.html', {
        'form': form,
        'titulo': 'Editar Hogar',
        'accion': 'Guardar cambios',
        'hogar': hogar
    })


@login_required
@superadmin_requerido
def hogar_toggle(request, pk):
    hogar = get_object_or_404(Hogar, pk=pk)
    hogar.activo = not hogar.activo
    hogar.save()
    estado = 'activado' if hogar.activo else 'desactivado'
    messages.success(request, f'Hogar {estado} correctamente.')
    return redirect('hogar_lista')