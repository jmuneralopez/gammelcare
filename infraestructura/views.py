from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from usuarios.decorators import administrador_requerido
from .models import Departamento, Habitacion, Cama
from .forms import DepartamentoForm, HabitacionForm, CamaForm


# ── DEPARTAMENTOS ──────────────────────────────────────────────

@login_required
@administrador_requerido
def departamento_lista(request):
    hogar = request.user.hogar
    departamentos = Departamento.objects.filter(hogar=hogar).order_by('nombre')
    return render(request, 'infraestructura/departamento_lista.html', {
        'departamentos': departamentos
    })


@login_required
@administrador_requerido
def departamento_crear(request):
    form = DepartamentoForm(request.POST or None)
    if form.is_valid():
        departamento = form.save(commit=False)
        departamento.hogar = request.user.hogar
        departamento.save()
        messages.success(request, 'Departamento creado correctamente.')
        return redirect('departamento_lista')
    return render(request, 'infraestructura/departamento_form.html', {
        'form': form, 'titulo': 'Nuevo Departamento', 'accion': 'Crear'
    })


@login_required
@administrador_requerido
def departamento_editar(request, pk):
    departamento = get_object_or_404(Departamento, pk=pk, hogar=request.user.hogar)
    form = DepartamentoForm(request.POST or None, instance=departamento)
    if form.is_valid():
        form.save()
        messages.success(request, 'Departamento actualizado correctamente.')
        return redirect('departamento_lista')
    return render(request, 'infraestructura/departamento_form.html', {
        'form': form, 'titulo': 'Editar Departamento', 'accion': 'Guardar cambios'
    })


@login_required
@administrador_requerido
def departamento_desactivar(request, pk):
    departamento = get_object_or_404(Departamento, pk=pk, hogar=request.user.hogar)
    departamento.activo = not departamento.activo
    departamento.save()
    estado = 'activado' if departamento.activo else 'desactivado'
    messages.success(request, f'Departamento {estado} correctamente.')
    return redirect('departamento_lista')


# ── HABITACIONES ───────────────────────────────────────────────

@login_required
@administrador_requerido
def habitacion_lista(request):
    hogar = request.user.hogar
    habitaciones = Habitacion.objects.filter(
        departamento__hogar=hogar
    ).order_by('departamento__nombre', 'numero')
    return render(request, 'infraestructura/habitacion_lista.html', {
        'habitaciones': habitaciones
    })


@login_required
@administrador_requerido
def habitacion_crear(request):
    form = HabitacionForm(request.POST or None)
    form.fields['departamento'].queryset = Departamento.objects.filter(
        hogar=request.user.hogar, activo=True
    )
    if form.is_valid():
        form.save()
        messages.success(request, 'Habitación creada correctamente.')
        return redirect('habitacion_lista')
    return render(request, 'infraestructura/habitacion_form.html', {
        'form': form, 'titulo': 'Nueva Habitación', 'accion': 'Crear'
    })


@login_required
@administrador_requerido
def habitacion_editar(request, pk):
    habitacion = get_object_or_404(Habitacion, pk=pk, departamento__hogar=request.user.hogar)
    form = HabitacionForm(request.POST or None, instance=habitacion)
    form.fields['departamento'].queryset = Departamento.objects.filter(
        hogar=request.user.hogar, activo=True
    )
    if form.is_valid():
        form.save()
        messages.success(request, 'Habitación actualizada correctamente.')
        return redirect('habitacion_lista')
    return render(request, 'infraestructura/habitacion_form.html', {
        'form': form, 'titulo': 'Editar Habitación', 'accion': 'Guardar cambios'
    })


@login_required
@administrador_requerido
def habitacion_desactivar(request, pk):
    habitacion = get_object_or_404(Habitacion, pk=pk, departamento__hogar=request.user.hogar)
    habitacion.activo = not habitacion.activo
    habitacion.save()
    estado = 'activada' if habitacion.activo else 'desactivada'
    messages.success(request, f'Habitación {estado} correctamente.')
    return redirect('habitacion_lista')


# ── CAMAS ──────────────────────────────────────────────────────

@login_required
@administrador_requerido
def cama_lista(request):
    hogar = request.user.hogar
    from .models import Departamento, Habitacion, Cama

    departamentos = Departamento.objects.filter(
        hogar=hogar, activo=True
    ).order_by('nombre')

    data = []
    total_camas = 0
    total_ocupadas = 0

    for dep in departamentos:
        habitaciones_data = []
        dep_camas = 0
        dep_ocupadas = 0

        habitaciones = Habitacion.objects.filter(
            departamento=dep, activo=True
        ).order_by('numero')

        for hab in habitaciones:
            camas = Cama.objects.filter(
                habitacion=hab, activo=True
            ).order_by('codigo')

            ocupadas = camas.filter(estado='ocupada').count()
            disponibles = camas.filter(estado='disponible').count()
            mantenimiento = camas.filter(estado='mantenimiento').count()
            total = camas.count()
            pct = round((ocupadas / total * 100)) if total > 0 else 0
            color = 'danger' if pct >= 80 else 'warning' if pct >= 50 else 'success'

            dep_camas += total
            dep_ocupadas += ocupadas

            habitaciones_data.append({
                'hab': hab,
                'camas': camas,
                'ocupadas': ocupadas,
                'disponibles': disponibles,
                'mantenimiento': mantenimiento,
                'total': total,
                'pct': pct,
                'color': color,
            })

        total_camas += dep_camas
        total_ocupadas += dep_ocupadas
        dep_pct = round((dep_ocupadas / dep_camas * 100)) if dep_camas > 0 else 0

        data.append({
            'dep': dep,
            'habitaciones': habitaciones_data,
            'total_camas': dep_camas,
            'ocupadas': dep_ocupadas,
            'pct': dep_pct,
        })

    ocupacion_general = round((total_ocupadas / total_camas * 100)) if total_camas > 0 else 0
    color_general = 'danger' if ocupacion_general >= 80 else 'warning' if ocupacion_general >= 50 else 'success'

    return render(request, 'infraestructura/cama_lista.html', {
        'data': data,
        'total_camas': total_camas,
        'total_ocupadas': total_ocupadas,
        'ocupacion_general': ocupacion_general,
        'color_general': color_general,
    })


@login_required
@administrador_requerido
def cama_crear(request):
    form = CamaForm(request.POST or None)
    form.fields['habitacion'].queryset = Habitacion.objects.filter(
        departamento__hogar=request.user.hogar, activo=True
    )
    if form.is_valid():
        form.save()
        messages.success(request, 'Cama creada correctamente.')
        return redirect('cama_lista')
    return render(request, 'infraestructura/cama_form.html', {
        'form': form, 'titulo': 'Nueva Cama', 'accion': 'Crear'
    })


@login_required
@administrador_requerido
def cama_editar(request, pk):
    cama = get_object_or_404(Cama, pk=pk, habitacion__departamento__hogar=request.user.hogar)
    form = CamaForm(request.POST or None, instance=cama)
    form.fields['habitacion'].queryset = Habitacion.objects.filter(
        departamento__hogar=request.user.hogar, activo=True
    )
    if form.is_valid():
        form.save()
        messages.success(request, 'Cama actualizada correctamente.')
        return redirect('cama_lista')
    return render(request, 'infraestructura/cama_form.html', {
        'form': form, 'titulo': 'Editar Cama', 'accion': 'Guardar cambios'
    })


@login_required
@administrador_requerido
def cama_desactivar(request, pk):
    cama = get_object_or_404(Cama, pk=pk, habitacion__departamento__hogar=request.user.hogar)
    cama.activo = not cama.activo
    cama.save()
    estado = 'activada' if cama.activo else 'desactivada'
    messages.success(request, f'Cama {estado} correctamente.')
    return redirect('cama_lista')