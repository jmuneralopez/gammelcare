from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from usuarios.decorators import administrador_requerido
from .models import CodigoCIE10, EPS, ServicioAmbulancia


# ── Búsquedas Select2 ──────────────────────────────────────────

@login_required
def buscar_cie10(request):
    term = request.GET.get('term', '').strip()
    if len(term) < 2:
        return JsonResponse({'results': []})
    resultados = (
        CodigoCIE10.objects.filter(codigo__icontains=term) |
        CodigoCIE10.objects.filter(descripcion__icontains=term)
    ).order_by('codigo')[:20]
    return JsonResponse({'results': [
        {'id': r.pk, 'text': f'{r.codigo} — {r.descripcion}'}
        for r in resultados
    ]})


@login_required
def buscar_eps(request):
    term = request.GET.get('term', '').strip()
    qs = EPS.objects.filter(activo=True)
    if term:
        qs = qs.filter(nombre__icontains=term)
    return JsonResponse({'results': [
        {'id': r.pk, 'text': r.nombre}
        for r in qs.order_by('nombre')[:20]
    ]})


@login_required
def buscar_ambulancia(request):
    term = request.GET.get('term', '').strip()
    qs = ServicioAmbulancia.objects.filter(activo=True)
    if term:
        qs = qs.filter(nombre__icontains=term)
    return JsonResponse({'results': [
        {'id': r.pk, 'text': r.nombre}
        for r in qs.order_by('nombre')[:20]
    ]})


# ── CRUD EPS ───────────────────────────────────────────────────

@login_required
@administrador_requerido
def eps_lista(request):
    eps_list = EPS.objects.all().order_by('nombre')
    return render(request, 'catalogos/eps_lista.html', {'eps_list': eps_list})


@login_required
@administrador_requerido
def eps_crear(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        codigo = request.POST.get('codigo', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        if nombre:
            EPS.objects.create(nombre=nombre, codigo=codigo, telefono=telefono)
            messages.success(request, 'EPS creada correctamente.')
            return redirect('eps_lista')
        messages.error(request, 'El nombre es obligatorio.')
    return render(request, 'catalogos/eps_form.html', {
        'titulo': 'Nueva EPS', 'accion': 'Crear', 'obj': None
    })


@login_required
@administrador_requerido
def eps_editar(request, pk):
    eps = get_object_or_404(EPS, pk=pk)
    if request.method == 'POST':
        eps.nombre = request.POST.get('nombre', '').strip()
        eps.codigo = request.POST.get('codigo', '').strip()
        eps.telefono = request.POST.get('telefono', '').strip()
        eps.activo = 'activo' in request.POST
        eps.save()
        messages.success(request, 'EPS actualizada correctamente.')
        return redirect('eps_lista')
    return render(request, 'catalogos/eps_form.html', {
        'titulo': 'Editar EPS', 'accion': 'Guardar cambios', 'obj': eps
    })


# ── CRUD Ambulancia ────────────────────────────────────────────

@login_required
@administrador_requerido
def ambulancia_lista(request):
    ambulancias = ServicioAmbulancia.objects.all().order_by('nombre')
    return render(request, 'catalogos/ambulancia_lista.html', {'ambulancias': ambulancias})


@login_required
@administrador_requerido
def ambulancia_crear(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        if nombre:
            ServicioAmbulancia.objects.create(nombre=nombre, telefono=telefono)
            messages.success(request, 'Servicio de ambulancia creado correctamente.')
            return redirect('ambulancia_lista')
        messages.error(request, 'El nombre es obligatorio.')
    return render(request, 'catalogos/ambulancia_form.html', {
        'titulo': 'Nuevo Servicio de Ambulancia', 'accion': 'Crear', 'obj': None
    })


@login_required
@administrador_requerido
def ambulancia_editar(request, pk):
    ambulancia = get_object_or_404(ServicioAmbulancia, pk=pk)
    if request.method == 'POST':
        ambulancia.nombre = request.POST.get('nombre', '').strip()
        ambulancia.telefono = request.POST.get('telefono', '').strip()
        ambulancia.activo = 'activo' in request.POST
        ambulancia.save()
        messages.success(request, 'Servicio actualizado correctamente.')
        return redirect('ambulancia_lista')
    return render(request, 'catalogos/ambulancia_form.html', {
        'titulo': 'Editar Servicio', 'accion': 'Guardar cambios', 'obj': ambulancia
    })