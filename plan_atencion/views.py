from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente

from . import services
from .forms import ObjetivoForm, PlanForm, SeguimientoForm
from .models import ObjetivoPlan, PlanAtencion
from .permisos import (activar_requerido, elaborar_requerido, puede_activar, puede_elaborar, puede_seguimiento,
                       seguimiento_requerido, ver_requerido)
from .sugerencias import sugerencias


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=request.user, accion=accion, descripcion=descripcion, ip_address=get_client_ip(request),
    )


def _plan(request, pk):
    return get_object_or_404(PlanAtencion.objects.select_related('residente'), pk=pk,
                             residente__hogar=request.user.hogar)


@login_required
@ver_requerido
def tablero(request):
    filas = []
    for r in sorted(Residente.objects.filter(hogar=request.user.hogar, activo=True), key=lambda r: r.get_nombre()):
        v = services.vigente(r)
        filas.append({'residente': r, 'nombre': r.get_nombre(), 'vigente': v, 'borrador': services.borrador(r),
                      'avance': v.avance() if v else None, 'falta': services.falta_plan(r)})
    return render(request, 'plan_atencion/tablero.html', {'filas': filas})


@login_required
@ver_requerido
def residente(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    v = services.vigente(residente)
    if v and not request.GET.get('historial'):
        return redirect('plan_detalle', pk=v.pk)
    return render(request, 'plan_atencion/residente.html', {
        'residente': residente, 'nombre': residente.get_nombre(), 'vigente': v,
        'borrador': services.borrador(residente),
        'planes': residente.planes_atencion.select_related('creado_por', 'activado_por'),
        'puede_elaborar': puede_elaborar(request.user) and residente.activo,
    })


@login_required
@elaborar_requerido
@require_POST
def crear_borrador(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar, activo=True)
    try:
        plan = services.crear_borrador(residente, request.user)
    except ValidationError as e:
        messages.info(request, e.messages[0])
        b = services.borrador(residente)
        return redirect('plan_detalle', pk=b.pk) if b else redirect('plan_residente', pk=residente.pk)
    _auditar(request, RegistroAuditoria.PLAN_ATENCION, f'Borrador del plan de atención v{plan.version} creado (residente #{residente.pk})')
    messages.success(request, f'Borrador del plan v{plan.version} creado. '
                              + ('Se copiaron los objetivos que seguían en curso.' if plan.anterior else 'Agregue los objetivos de cada área.'))
    return redirect('plan_detalle', pk=plan.pk)


@login_required
@ver_requerido
def detalle(request, pk):
    plan = _plan(request, pk)
    objetivos = list(plan.objetivos.select_related('creado_por').prefetch_related('seguimientos__registrado_por'))
    areas = []
    for o in objetivos:
        if not areas or areas[-1][0] != o.get_area_display():
            areas.append((o.get_area_display(), []))
        areas[-1][1].append(o)
    ya = {o.origen for o in objetivos if o.origen}
    sug = [s for s in sugerencias(plan.residente) if s.origen not in ya] if plan.estado != PlanAtencion.REEMPLAZADO else []
    return render(request, 'plan_atencion/detalle.html', {
        'plan': plan, 'residente': plan.residente, 'nombre': plan.residente.get_nombre(), 'areas': areas,
        'sugerencias': sug, 'avance': plan.avance(),
        'puede_elaborar': puede_elaborar(request.user) and plan.residente.activo,
        'puede_activar': puede_activar(request.user),
        'puede_seguimiento': puede_seguimiento(request.user) and plan.estado == PlanAtencion.VIGENTE,
        'seguimiento_form': SeguimientoForm(),
        'borrador': services.borrador(plan.residente) if plan.estado == PlanAtencion.VIGENTE else None,
    })


@login_required
@elaborar_requerido
def editar(request, pk):
    plan = _plan(request, pk)
    if not plan.editable:
        messages.error(request, 'Solo se edita un plan en borrador. Para cambiar el vigente, use "Revisar plan".')
        return redirect('plan_detalle', pk=plan.pk)
    form = PlanForm(request.POST or None, instance=plan)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Datos del plan guardados.')
        return redirect('plan_detalle', pk=plan.pk)
    return render(request, 'plan_atencion/plan_form.html', {
        'form': form, 'plan': plan, 'residente': plan.residente, 'nombre': plan.residente.get_nombre(),
        'sugerencia_resumen': _resumen_sugerido(plan.residente),
    })


def _resumen_sugerido(residente):
    """Texto base con lo registrado: alergias, antecedentes, escalas y peso."""
    from antecedentes import services as ant
    from signos import services as sv
    from valoracion import services as vs
    partes = []
    alergias = ant.alergias_activas(residente)
    estado = ant.estado_alergias(residente)
    partes.append('Alergias: ' + (', '.join(a.sustancia for a in alergias) if alergias else
                                  ('sin alergias conocidas' if estado == 'sin_alergias' else 'sin registrar')) + '.')
    antecedentes = list(residente.antecedentes.filter(activo=True)[:8])
    if antecedentes:
        partes.append('Antecedentes: ' + ', '.join(a.descripcion for a in antecedentes) + '.')
    escalas = [f for f in vs.estado_por_escala(residente) if f['ultima']]
    if escalas:
        partes.append('Escalas: ' + '; '.join(f"{f['escala'].corto} {f['ultima'].puntaje} ({f['ultima'].interpretacion}, "
                                                f"{f['ultima'].fecha:%d/%m/%Y})" for f in escalas) + '.')
    ultimo = sv.ultimo_control(residente)
    peso = sv.vigentes(residente.controles_signos.filter(peso__isnull=False)).order_by('-fecha_hora').first()
    if peso:
        partes.append(f'Peso: {peso.peso} kg ({timezone.localtime(peso.fecha_hora):%d/%m/%Y}).')
    if ultimo and ultimo.presion:
        partes.append(f'Última presión arterial: {ultimo.presion} mmHg.')
    return '\n'.join(partes)


@login_required
@elaborar_requerido
def objetivo_crear(request, pk):
    plan = _plan(request, pk)
    if plan.estado == PlanAtencion.REEMPLAZADO:
        messages.error(request, 'Ese plan ya fue reemplazado.')
        return redirect('plan_detalle', pk=plan.pk)
    inicial = {'fecha_meta': timezone.localdate() + timedelta(days=90)}
    clave = request.GET.get('sugerencia')
    if clave:
        s = next((s for s in sugerencias(plan.residente) if s.clave == clave), None)
        if s:
            inicial.update(area=s.area, necesidad=s.necesidad, meta=s.meta, intervenciones=s.intervenciones,
                           responsable=s.responsable, frecuencia=s.frecuencia, origen=s.origen)
    form = ObjetivoForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        o = form.save(commit=False)
        o.plan = plan
        o.creado_por = request.user
        o.save()
        if plan.estado == PlanAtencion.VIGENTE:
            _auditar(request, RegistroAuditoria.PLAN_ATENCION,
                     f'Objetivo agregado al plan vigente v{plan.version} (residente #{plan.residente_id}): {o.meta[:120]}')
        messages.success(request, 'Objetivo agregado.')
        return redirect('plan_detalle', pk=plan.pk)
    return render(request, 'plan_atencion/objetivo_form.html', {
        'form': form, 'plan': plan, 'objetivo': None, 'residente': plan.residente, 'nombre': plan.residente.get_nombre(),
    })


@login_required
@elaborar_requerido
def objetivo_editar(request, pk):
    o = get_object_or_404(ObjetivoPlan.objects.select_related('plan__residente'), pk=pk,
                          plan__residente__hogar=request.user.hogar)
    if not o.plan.editable:
        messages.error(request, 'Los objetivos de un plan vigente no se editan: registre un seguimiento o revise el plan.')
        return redirect('plan_detalle', pk=o.plan_id)
    form = ObjetivoForm(request.POST or None, instance=o)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Objetivo corregido.')
        return redirect('plan_detalle', pk=o.plan_id)
    return render(request, 'plan_atencion/objetivo_form.html', {
        'form': form, 'plan': o.plan, 'objetivo': o, 'residente': o.plan.residente, 'nombre': o.plan.residente.get_nombre(),
    })


@login_required
@elaborar_requerido
@require_POST
def objetivo_quitar(request, pk):
    o = get_object_or_404(ObjetivoPlan.objects.select_related('plan'), pk=pk, plan__residente__hogar=request.user.hogar)
    if not o.plan.editable:
        messages.error(request, 'Solo se quitan objetivos de un plan en borrador. En el vigente, márquelo como suspendido con un seguimiento.')
    else:
        o.delete()
        messages.success(request, 'Objetivo quitado del borrador.')
    return redirect('plan_detalle', pk=o.plan_id)


@login_required
@activar_requerido
@require_POST
def activar(request, pk):
    plan = _plan(request, pk)
    try:
        services.activar(plan, request.user)
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect('plan_detalle', pk=plan.pk)
    _auditar(request, RegistroAuditoria.PLAN_ATENCION, f'Plan de atención v{plan.version} activado (residente #{plan.residente_id})')
    messages.success(request, f'Plan de atención v{plan.version} activado. Es el plan vigente.')
    return redirect('plan_detalle', pk=plan.pk)


@login_required
@elaborar_requerido
@require_POST
def descartar_borrador(request, pk):
    plan = _plan(request, pk)
    if plan.estado != PlanAtencion.BORRADOR:
        messages.error(request, 'Solo se descarta un borrador.')
        return redirect('plan_detalle', pk=plan.pk)
    residente_id = plan.residente_id
    plan.delete()
    messages.success(request, 'Borrador descartado.')
    return redirect('plan_residente', pk=residente_id)


@login_required
@seguimiento_requerido
@require_POST
def seguimiento(request, pk):
    o = get_object_or_404(ObjetivoPlan.objects.select_related('plan'), pk=pk, plan__residente__hogar=request.user.hogar)
    form = SeguimientoForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Elija el estado y escriba qué se observó.')
        return redirect('plan_detalle', pk=o.plan_id)
    try:
        services.registrar_seguimiento(o, request.user, form.cleaned_data['estado'], form.cleaned_data['nota'])
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect('plan_detalle', pk=o.plan_id)
    messages.success(request, 'Seguimiento registrado.')
    return redirect(f"{redirect('plan_detalle', pk=o.plan_id).url}#objetivo-{o.pk}")
