from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente

from . import services
from .forms import AnularForm, CerrarHeridaForm, CuidadoForm, HeridaForm, PlanCuidadosForm, SeguimientoForm
from .models import DETALLES, ICONOS, TIPOS_CUIDADO, Herida, PlanCuidados, RegistroCuidado, SeguimientoHerida
from .permisos import (cerrar_herida_requerido, cuidados_requerido, heridas_requerido, plan_requerido, puede_anular,
                       puede_cerrar_herida, puede_heridas, puede_plan, puede_registrar_cuidados, ver_requerido)

NOMBRES = dict(TIPOS_CUIDADO)


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(usuario=request.user, accion=accion, descripcion=descripcion,
                                     ip_address=get_client_ip(request))


def _residente(request, pk, activo=False):
    filtros = {'pk': pk, 'hogar': request.user.hogar}
    if activo:
        filtros['activo'] = True
    return get_object_or_404(Residente, **filtros)


def _volver(request, defecto):
    destino = request.POST.get('volver') or request.GET.get('volver')
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return defecto


# ── Planilla del turno ──────────────────────────────────────────────

@login_required
@ver_requerido
def planilla(request):
    codigo, nombre_turno, inicio, fin = services.turno_actual()
    filas = services.planilla(request.user.hogar)
    q = request.GET.get('q', '').strip().lower()
    if q:
        filas = [f for f in filas if q in f['nombre'].lower()
                 or (f['residente'].cama_actual and q in f'{f["residente"].cama_actual.habitacion.numero} {f["residente"].cama_actual.codigo}'.lower())]
    if request.GET.get('ver') == 'pendientes':
        filas = [f for f in filas if f['pendientes']]
    return render(request, 'cuidados/planilla.html', {
        'filas': filas, 'turno': nombre_turno, 'inicio': inicio, 'fin': fin, 'q': q,
        'ver': request.GET.get('ver', ''), 'nombres': NOMBRES, 'iconos': ICONOS,
        'puede_registrar': puede_registrar_cuidados(request.user),
        'total_pendientes': sum(f['pendientes'] for f in filas),
    })


@login_required
@require_POST
@cuidados_requerido
def registrar_rapido(request, pk):
    """Un toque desde la planilla: cuidado y opción, con la hora actual."""
    residente = _residente(request, pk, activo=True)
    tipo, detalle = request.POST.get('tipo', ''), request.POST.get('detalle', '')
    try:
        r = services.registrar(residente, tipo, detalle, request.user)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'{residente.get_nombre()}: {r.get_tipo_display().lower()} — '
                                  f'{r.detalle_texto.lower()} a las {timezone.localtime(r.fecha_hora):%H:%M}.')
    destino = _volver(request, reverse('cuidados_planilla'))
    if '#' not in destino:
        destino += f'#res-{residente.pk}'
    return redirect(destino)


# ── Residente ───────────────────────────────────────────────────────

@login_required
@ver_requerido
def residente(request, pk):
    residente = _residente(request, pk)
    try:
        dias = max(1, min(int(request.GET.get('dias', 2)), 31))
    except ValueError:
        dias = 2
    ahora = timezone.now()
    plan = services.plan_de(residente)
    _, _, inicio_turno, _ = services.turno_actual()
    celdas = [services.celda(residente, plan, t, inicio_turno) for t in plan.tipos()]
    registros = list(services.historial(residente, ahora - timedelta(days=dias), ahora + timedelta(minutes=5)))
    for r in registros:
        r.puede_anular = puede_anular(request.user, r)
    heridas = list(residente.heridas.all().prefetch_related('seguimientos'))
    norton = services.ultimo_norton(residente)
    return render(request, 'cuidados/residente.html', {
        'residente': residente, 'nombre': residente.get_nombre(), 'plan': plan, 'celdas': celdas,
        'registros': registros, 'dias': dias, 'heridas': heridas, 'norton': norton,
        'riesgo_norton': norton is not None and norton.puntaje <= services.NORTON_RIESGO,
        'nombres': NOMBRES, 'iconos': ICONOS, 'detalles_json': {k: v for k, v in DETALLES.items()},
        'form': CuidadoForm(), 'form_anular': AnularForm(),
        'puede_registrar': puede_registrar_cuidados(request.user) and residente.activo,
        'puede_plan': puede_plan(request.user) and residente.activo,
        'puede_heridas': puede_heridas(request.user) and residente.activo,
    })


@login_required
@require_POST
@cuidados_requerido
def registrar(request, pk):
    """Registro con hora y observación (por ejemplo, un cuidado que se hizo antes)."""
    residente = _residente(request, pk, activo=True)
    form = CuidadoForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        r = services.registrar(residente, d['tipo'], d['detalle'], request.user, d['fecha_hora'], d['observaciones'])
        messages.success(request, f'Se registró {r.get_tipo_display().lower()} ({r.detalle_texto.lower()}).')
    else:
        errores = '; '.join(e for lista in form.errors.values() for e in lista)
        messages.error(request, f'No se registró el cuidado: {errores}')
    return redirect('cuidados_residente', pk=residente.pk)


@login_required
@require_POST
@ver_requerido
def anular(request, pk):
    registro = get_object_or_404(RegistroCuidado, pk=pk, residente__hogar=request.user.hogar)
    if not puede_anular(request.user, registro):
        messages.error(request, 'No puede anular este registro.')
        return redirect('cuidados_residente', pk=registro.residente_id)
    form = AnularForm(request.POST)
    if form.is_valid():
        registro.anular(request.user, form.cleaned_data['motivo'])
        _auditar(request, RegistroAuditoria.CUIDADO_ANULADO,
                 f'Anulación de {registro.get_tipo_display().lower()} #{registro.pk} del residente #{registro.residente_id}')
        messages.success(request, 'El registro quedó anulado.')
    else:
        messages.error(request, 'Escriba el motivo de la anulación.')
    return redirect('cuidados_residente', pk=registro.residente_id)


@login_required
@plan_requerido
def plan(request, pk):
    residente = _residente(request, pk, activo=True)
    existente = PlanCuidados.objects.filter(residente=residente).first()
    instancia = existente or services.sugerencia_plan(residente)
    form = PlanCuidadosForm(request.POST or None, instance=instancia)
    if request.method == 'POST' and form.is_valid():
        p = form.save(commit=False)
        p.residente = residente
        p.actualizado_por = request.user
        p.fecha_actualizacion = timezone.now()
        p.save()
        _auditar(request, RegistroAuditoria.PLAN_CUIDADOS,
                 f'Plan de cuidados del residente #{residente.pk}: {", ".join(NOMBRES[t] for t in p.tipos()) or "sin cuidados"}')
        messages.success(request, 'Plan de cuidados guardado.')
        return redirect('cuidados_residente', pk=residente.pk)
    norton = services.ultimo_norton(residente)
    return render(request, 'cuidados/plan_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(), 'nuevo': existente is None,
        'norton': norton, 'riesgo_norton': norton is not None and norton.puntaje <= services.NORTON_RIESGO,
    })


# ── Heridas ─────────────────────────────────────────────────────────

@login_required
@ver_requerido
def heridas_tablero(request):
    heridas = (Herida.objects.filter(residente__hogar=request.user.hogar, residente__activo=True, estado=Herida.ACTIVA)
               .select_related('residente').prefetch_related('seguimientos')
               .order_by('residente__cama_actual__habitacion__departamento__nombre',
                         'residente__cama_actual__habitacion__numero', 'fecha_deteccion'))
    filas = []
    for h in heridas:
        dias, ultimo = services.dias_sin_seguimiento(h)
        filas.append({'herida': h, 'nombre': h.residente.get_nombre(), 'ultimo': ultimo, 'dias': dias,
                      'curacion_vencida': bool(ultimo and ultimo.proxima_curacion
                                               and ultimo.proxima_curacion < timezone.localdate())})
    return render(request, 'cuidados/heridas_tablero.html', {
        'filas': filas, 'lpp': sum(1 for f in filas if f['herida'].es_lpp),
        'lpp_hogar': sum(1 for f in filas if f['herida'].es_lpp and f['herida'].origen == 'hogar'),
        'infectadas': sum(1 for f in filas if f['ultimo'] and f['ultimo'].signos_infeccion),
    })


@login_required
@heridas_requerido
def herida_crear(request, pk):
    residente = _residente(request, pk, activo=True)
    form = HeridaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        h = form.save(commit=False)
        h.residente = residente
        h.registrado_por = request.user
        h.save()
        _auditar(request, RegistroAuditoria.HERIDA_REGISTRADA, f'{h.nombre} del residente #{residente.pk}')
        messages.success(request, 'Herida registrada. Registre ahora la primera valoración, con medidas y foto.')
        return redirect('cuidados_seguimiento_crear', pk=h.pk)
    return render(request, 'cuidados/herida_form.html', {'form': form, 'residente': residente,
                                                          'nombre': residente.get_nombre()})


@login_required
@ver_requerido
def herida_detalle(request, pk):
    h = get_object_or_404(Herida.objects.select_related('residente'), pk=pk, residente__hogar=request.user.hogar)
    seguimientos = list(h.seguimientos.select_related('registrado_por', 'anulado_por').order_by('-fecha_hora'))
    for s in seguimientos:
        s.puede_anular = puede_anular(request.user, s)
    vigentes = [s for s in reversed(seguimientos) if not s.anulado and s.area_cm2 is not None]
    evolucion = None
    if len(vigentes) >= 2:
        primero, ultimo = vigentes[0].area_cm2, vigentes[-1].area_cm2
        evolucion = {'primero': primero, 'ultimo': ultimo,
                     'porcentaje': round(100 * (ultimo - primero) / primero) if primero else None}
    return render(request, 'cuidados/herida_detalle.html', {
        'herida': h, 'residente': h.residente, 'nombre': h.residente.get_nombre(), 'seguimientos': seguimientos,
        'evolucion': evolucion,
        'proponer_evento': h.es_lpp and h.origen == 'hogar' and not h.eventos_adversos.exists(), 'grafica': [{'x': timezone.localtime(s.fecha_hora).strftime('%d/%m'),
                                             'y': float(s.area_cm2)} for s in vigentes],
        'form_cerrar': CerrarHeridaForm(), 'form_anular': AnularForm(),
        'puede_heridas': puede_heridas(request.user) and h.activa,
        'puede_cerrar': puede_cerrar_herida(request.user) and h.activa,
    })


@login_required
@heridas_requerido
def seguimiento_crear(request, pk):
    h = get_object_or_404(Herida.objects.select_related('residente'), pk=pk, residente__hogar=request.user.hogar,
                          estado=Herida.ACTIVA)
    form = SeguimientoForm(request.POST or None, request.FILES or None, herida=h)
    if request.method == 'POST' and form.is_valid():
        s = form.save(commit=False)
        s.herida = h
        s.registrado_por = request.user
        foto = form.cleaned_data.get('foto_archivo')
        if foto:
            s.foto = foto
            s.foto_tipo = foto.tipo_detectado
        s.save()
        _auditar(request, RegistroAuditoria.HERIDA_SEGUIMIENTO,
                 f'Seguimiento #{s.pk} de {h.nombre} (residente #{h.residente_id})')
        if s.signos_infeccion:
            messages.warning(request, 'Se registraron signos de infección: informe al médico. Se generó una alerta.')
        messages.success(request, 'Seguimiento de la herida registrado.')
        return redirect('cuidados_herida_detalle', pk=h.pk)
    ultimo = h.ultimo_seguimiento()
    return render(request, 'cuidados/seguimiento_form.html', {
        'form': form, 'herida': h, 'residente': h.residente, 'nombre': h.residente.get_nombre(), 'ultimo': ultimo,
    })


@login_required
@require_POST
@cerrar_herida_requerido
def herida_cerrar(request, pk):
    h = get_object_or_404(Herida, pk=pk, residente__hogar=request.user.hogar, estado=Herida.ACTIVA)
    form = CerrarHeridaForm(request.POST)
    if form.is_valid():
        h.estado = Herida.CERRADA
        h.motivo_cierre = form.cleaned_data['motivo']
        h.nota_cierre = form.cleaned_data['nota']
        h.cerrada_por = request.user
        h.fecha_cierre = timezone.now()
        h.save()
        _auditar(request, RegistroAuditoria.HERIDA_CERRADA,
                 f'{h.nombre} del residente #{h.residente_id}: {h.get_motivo_cierre_display()}')
        messages.success(request, 'La herida quedó cerrada.')
    else:
        messages.error(request, 'No se cerró la herida: ' + '; '.join(e for l in form.errors.values() for e in l))
    return redirect('cuidados_herida_detalle', pk=h.pk)


@login_required
@require_POST
@ver_requerido
def seguimiento_anular(request, pk):
    s = get_object_or_404(SeguimientoHerida, pk=pk, herida__residente__hogar=request.user.hogar)
    if not puede_anular(request.user, s):
        messages.error(request, 'No puede anular este seguimiento.')
        return redirect('cuidados_herida_detalle', pk=s.herida_id)
    form = AnularForm(request.POST)
    if form.is_valid():
        s.anular(request.user, form.cleaned_data['motivo'])
        _auditar(request, RegistroAuditoria.CUIDADO_ANULADO,
                 f'Anulación del seguimiento #{s.pk} de la herida #{s.herida_id}')
        messages.success(request, 'El seguimiento quedó anulado.')
    else:
        messages.error(request, 'Escriba el motivo de la anulación.')
    return redirect('cuidados_herida_detalle', pk=s.herida_id)


@login_required
@ver_requerido
def foto(request, pk):
    s = get_object_or_404(SeguimientoHerida.objects.select_related('herida'), pk=pk,
                          herida__residente__hogar=request.user.hogar)
    if not s.foto:
        raise Http404('Este seguimiento no tiene foto.')
    try:
        handle = s.foto.open('rb')
    except FileNotFoundError:
        raise Http404('La foto no se encuentra en el almacenamiento.')
    _auditar(request, RegistroAuditoria.CONSULTA_FOTO_HERIDA,
             f'Foto del seguimiento #{s.pk} de la herida #{s.herida_id} (residente #{s.herida.residente_id})')
    respuesta = FileResponse(handle, content_type=s.foto_tipo or 'image/jpeg')
    respuesta['X-Content-Type-Options'] = 'nosniff'
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta
