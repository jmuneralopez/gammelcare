"""Institución: departamentos, habitaciones y camas del hogar en una sola
sección.

- Ver: todos los roles del hogar (administrador y roles clínicos). Cada cama
  muestra al residente que la ocupa, con enlace a su expediente: es otra
  forma de recorrer a los residentes, ordenados por lugar.
- Crear, editar, desactivar y reactivar: solo el administrador del hogar.
- Las pantallas de lista anteriores (departamentos, habitaciones, camas)
  redirigen a Institución.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from residentes.models import Residente
from usuarios.decorators import administrador_hogar_requerido, clinico_requerido

from .forms import CamaForm, DepartamentoForm, HabitacionForm
from .models import Cama, Departamento, Habitacion


def _puede_editar(usuario):
    return usuario.es_administrador_hogar()


def _volver(request, ancla=''):
    siguiente = request.POST.get('next') or request.GET.get('next')
    if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        return redirect(siguiente)
    return redirect(reverse('institucion') + (f'#{ancla}' if ancla else ''))


def _color(pct):
    return 'danger' if pct >= 80 else 'warning' if pct >= 50 else 'success'


# ── Vista única ────────────────────────────────────────────────

@login_required
@clinico_requerido
def institucion(request):
    hogar = request.user.hogar
    editar = _puede_editar(request.user)
    ver_inactivos = editar and request.GET.get('inactivos') == '1'

    camas_qs = Cama.objects.order_by('codigo').select_related('residente_actual')
    habs_qs = Habitacion.objects.order_by('numero')
    if not ver_inactivos:
        camas_qs = camas_qs.filter(activo=True)
        habs_qs = habs_qs.filter(activo=True)
    habs_qs = habs_qs.prefetch_related(Prefetch('camas', queryset=camas_qs))
    deps = Departamento.objects.filter(hogar=hogar).order_by('nombre').prefetch_related(
        Prefetch('habitaciones', queryset=habs_qs))
    if not ver_inactivos:
        deps = deps.filter(activo=True)

    data, total, ocupadas_total = [], 0, 0
    for dep in deps:
        habitaciones, dep_total, dep_ocupadas = [], 0, 0
        for hab in dep.habitaciones.all():
            camas = []
            for cama in hab.camas.all():
                residente = getattr(cama, 'residente_actual', None)
                if residente is not None and not residente.activo:
                    residente = None
                camas.append({'cama': cama, 'residente': residente,
                              'nombre': residente.get_nombre() if residente else ''})
            activas = [c for c in camas if c['cama'].activo]
            n_ocupadas = sum(1 for c in activas if c['residente'])
            pct = round(n_ocupadas * 100 / len(activas)) if activas else 0
            habitaciones.append({'hab': hab, 'camas': camas, 'total': len(activas), 'ocupadas': n_ocupadas,
                                 'pct': pct, 'color': _color(pct)})
            dep_total += len(activas)
            dep_ocupadas += n_ocupadas
        total += dep_total
        ocupadas_total += dep_ocupadas
        pct = round(dep_ocupadas * 100 / dep_total) if dep_total else 0
        data.append({'dep': dep, 'habitaciones': habitaciones, 'total': dep_total, 'ocupadas': dep_ocupadas,
                     'pct': pct})

    sin_cama = Residente.objects.filter(hogar=hogar, activo=True, cama_actual__isnull=True)
    ocupacion = round(ocupadas_total * 100 / total) if total else 0
    return render(request, 'infraestructura/institucion.html', {
        'data': data, 'total_camas': total, 'ocupadas': ocupadas_total, 'disponibles': total - ocupadas_total,
        'ocupacion': ocupacion, 'color_general': _color(ocupacion),
        'sin_cama': sorted(sin_cama, key=lambda r: r.get_nombre()),
        'puede_editar': editar, 'ver_inactivos': ver_inactivos,
    })


def lista_anterior(request, *args, **kwargs):
    """Las listas por separado se unificaron en Institución."""
    return redirect('institucion')


# ── Formularios ────────────────────────────────────────────────

def _render_form(request, form, titulo, accion, tipo, objeto=None):
    return render(request, f'infraestructura/{tipo}_form.html', {
        'form': form, 'titulo': titulo, 'accion': accion, 'objeto': objeto,
        'next': request.GET.get('next') or request.POST.get('next', ''),
        'departamentos': Departamento.objects.filter(hogar=request.user.hogar, activo=True).order_by('nombre'),
    })


@login_required
@administrador_hogar_requerido
def departamento_crear(request):
    form = DepartamentoForm(request.POST or None)
    if form.is_valid():
        dep = form.save(commit=False)
        dep.hogar = request.user.hogar
        dep.save()
        messages.success(request, f'Departamento "{dep.nombre}" creado.')
        return _volver(request, f'dep-{dep.pk}')
    return _render_form(request, form, 'Nuevo departamento', 'Crear departamento', 'departamento')


@login_required
@administrador_hogar_requerido
def departamento_editar(request, pk):
    dep = get_object_or_404(Departamento, pk=pk, hogar=request.user.hogar)
    form = DepartamentoForm(request.POST or None, instance=dep)
    if form.is_valid():
        form.save()
        messages.success(request, 'Departamento actualizado.')
        return _volver(request, f'dep-{dep.pk}')
    return _render_form(request, form, 'Editar departamento', 'Guardar cambios', 'departamento', dep)


def _habitaciones_qs(request):
    return Departamento.objects.filter(hogar=request.user.hogar, activo=True)


@login_required
@administrador_hogar_requerido
def habitacion_crear(request):
    inicial = {}
    if request.GET.get('departamento', '').isdigit():
        inicial['departamento'] = request.GET['departamento']
    form = HabitacionForm(request.POST or None, initial=inicial)
    form.fields['departamento'].queryset = _habitaciones_qs(request)
    if form.is_valid():
        hab = form.save()
        messages.success(request, f'Habitación {hab.numero} creada.')
        return _volver(request, f'hab-{hab.pk}')
    return _render_form(request, form, 'Nueva habitación', 'Crear habitación', 'habitacion')


@login_required
@administrador_hogar_requerido
def habitacion_editar(request, pk):
    hab = get_object_or_404(Habitacion, pk=pk, departamento__hogar=request.user.hogar)
    form = HabitacionForm(request.POST or None, instance=hab)
    form.fields['departamento'].queryset = _habitaciones_qs(request)
    if form.is_valid():
        form.save()
        messages.success(request, 'Habitación actualizada.')
        return _volver(request, f'hab-{hab.pk}')
    return _render_form(request, form, 'Editar habitación', 'Guardar cambios', 'habitacion', hab)


def _camas_habitaciones(request):
    return Habitacion.objects.filter(departamento__hogar=request.user.hogar, departamento__activo=True,
                                     activo=True).select_related('departamento').order_by('departamento__nombre', 'numero')


@login_required
@administrador_hogar_requerido
def cama_crear(request):
    inicial = {}
    if request.GET.get('habitacion', '').isdigit():
        inicial['habitacion'] = request.GET['habitacion']
    form = CamaForm(request.POST or None, initial=inicial)
    form.fields['habitacion'].queryset = _camas_habitaciones(request)
    if form.is_valid():
        cama = form.save()
        messages.success(request, f'Cama {cama.codigo} creada.')
        return _volver(request, f'hab-{cama.habitacion_id}')
    return _render_form(request, form, 'Nueva cama', 'Crear cama', 'cama')


@login_required
@administrador_hogar_requerido
def cama_editar(request, pk):
    cama = get_object_or_404(Cama, pk=pk, habitacion__departamento__hogar=request.user.hogar)
    form = CamaForm(request.POST or None, instance=cama)
    form.fields['habitacion'].queryset = _camas_habitaciones(request)
    if form.is_valid():
        form.save()
        messages.success(request, 'Cama actualizada.')
        return _volver(request, f'hab-{cama.habitacion_id}')
    return _render_form(request, form, 'Editar cama', 'Guardar cambios', 'cama', cama)


# ── Desactivar / reactivar (siempre por POST) ──────────────────

@login_required
@administrador_hogar_requerido
@require_POST
def departamento_desactivar(request, pk):
    dep = get_object_or_404(Departamento, pk=pk, hogar=request.user.hogar)
    if dep.activo and Residente.objects.filter(cama_actual__habitacion__departamento=dep, activo=True).exists():
        messages.error(request, f'No se puede desactivar "{dep.nombre}": tiene camas ocupadas por residentes activos.')
        return _volver(request, f'dep-{dep.pk}')
    dep.activo = not dep.activo
    dep.save(update_fields=['activo'])
    messages.success(request, f'Departamento {"reactivado" if dep.activo else "desactivado"}.')
    return _volver(request, f'dep-{dep.pk}')


@login_required
@administrador_hogar_requerido
@require_POST
def habitacion_desactivar(request, pk):
    hab = get_object_or_404(Habitacion, pk=pk, departamento__hogar=request.user.hogar)
    if hab.activo and Residente.objects.filter(cama_actual__habitacion=hab, activo=True).exists():
        messages.error(request, f'No se puede desactivar la habitación {hab.numero}: tiene camas ocupadas por residentes activos.')
        return _volver(request, f'hab-{hab.pk}')
    hab.activo = not hab.activo
    hab.save(update_fields=['activo'])
    messages.success(request, f'Habitación {"reactivada" if hab.activo else "desactivada"}.')
    return _volver(request, f'hab-{hab.pk}')


@login_required
@administrador_hogar_requerido
@require_POST
def cama_desactivar(request, pk):
    cama = get_object_or_404(Cama, pk=pk, habitacion__departamento__hogar=request.user.hogar)
    if cama.activo:
        residente = Residente.objects.filter(cama_actual=cama, activo=True).first()
        if residente:
            messages.error(request, f'No se puede desactivar la cama {cama.codigo}: está ocupada por {residente.get_nombre()}.')
            return _volver(request, f'hab-{cama.habitacion_id}')
    cama.activo = not cama.activo
    cama.save(update_fields=['activo'])
    messages.success(request, f'Cama {"reactivada" if cama.activo else "desactivada"}.')
    return _volver(request, f'hab-{cama.habitacion_id}')


# ── Alta rápida desde los formularios (catálogos en contexto) ──

@login_required
@administrador_hogar_requerido
@require_POST
def departamento_crear_rapido(request):
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'errors': {'nombre': ['Escriba el nombre del departamento.']}}, status=400)
    if Departamento.objects.filter(hogar=request.user.hogar, nombre__iexact=nombre).exists():
        return JsonResponse({'errors': {'nombre': [f'Ya existe un departamento llamado "{nombre}".']}}, status=400)
    dep = Departamento.objects.create(hogar=request.user.hogar, nombre=nombre,
                                      descripcion=request.POST.get('descripcion', '').strip())
    return JsonResponse({'id': dep.pk, 'text': dep.nombre})


@login_required
@administrador_hogar_requerido
@require_POST
def habitacion_crear_rapido(request):
    numero = request.POST.get('numero', '').strip()
    dep_id = request.POST.get('departamento', '')
    dep = Departamento.objects.filter(pk=dep_id, hogar=request.user.hogar, activo=True).first() if dep_id.isdigit() else None
    errores = {}
    if not dep:
        errores['departamento'] = ['Elija el departamento.']
    if not numero:
        errores['numero'] = ['Escriba el número de la habitación.']
    if dep and numero and Habitacion.objects.filter(departamento=dep, numero__iexact=numero).exists():
        errores['numero'] = [f'Ya existe la habitación {numero} en {dep.nombre}.']
    if errores:
        return JsonResponse({'errors': errores}, status=400)
    hab = Habitacion.objects.create(departamento=dep, numero=numero)
    return JsonResponse({'id': hab.pk, 'text': str(hab)})
