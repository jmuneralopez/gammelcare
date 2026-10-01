from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente

from . import services
from .forms import AtenderForm, AvisoForm, ConfiguracionForm, DescartarForm
from .models import Alerta, ConfiguracionAlertas
from .motor import evaluar_hogar, evaluar_si_toca
from .permisos import (configurar_requerido, personal_requerido, publicar_requerido, puede_atender,
                       puede_configurar, puede_descartar, puede_publicar, puede_ver_todas)


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=request.user, accion=accion, descripcion=descripcion, ip_address=get_client_ip(request),
    )


def _volver(request, defecto='alertas_bandeja'):
    siguiente = request.POST.get('next') or request.GET.get('next')
    if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        return redirect(siguiente)
    return redirect(defecto)


@login_required
@personal_requerido
def bandeja(request):
    evaluar_si_toca(request.user.hogar)
    ver = request.GET.get('ver', 'mias')
    todas = ver == 'todas' and puede_ver_todas(request.user)
    estado = request.GET.get('estado', 'activas')
    gravedad = request.GET.get('gravedad', '')
    residente_id = request.GET.get('residente', '')

    qs = services.alertas_para(request.user, todas=todas)
    if estado == 'activas':
        qs = qs.filter(estado__in=Alerta.ACTIVAS)
    elif estado in dict(Alerta.ESTADOS):
        qs = qs.filter(estado=estado)
    if gravedad in Alerta.ORDEN_GRAVEDAD:
        qs = qs.filter(gravedad=gravedad)
    if residente_id.isdigit():
        qs = qs.filter(residente_id=int(residente_id))
    alertas = list(qs[:300]) if estado == 'activas' else list(qs.order_by('-fecha_creacion')[:300])
    ya_vistas = services.marcar_vistas(request.user, alertas)
    for a in alertas:
        a.nueva_para_mi = a.pk not in ya_vistas
        a.puede_atender = puede_atender(request.user, a)
        a.puede_descartar = puede_descartar(request.user, a)

    residentes = sorted(Residente.objects.filter(hogar=request.user.hogar, activo=True), key=lambda r: r.get_nombre())
    activas = services.alertas_para(request.user, todas=todas).filter(estado__in=Alerta.ACTIVAS)
    return render(request, 'alertas/bandeja.html', {
        'alertas': alertas,
        'ver': 'todas' if todas else 'mias',
        'estado': estado,
        'gravedad': gravedad,
        'residente_id': residente_id,
        'residentes': [(r.pk, r.get_nombre()) for r in residentes],
        'puede_ver_todas': puede_ver_todas(request.user),
        'puede_publicar': puede_publicar(request.user),
        'puede_configurar': puede_configurar(request.user),
        'conteo': {g: activas.filter(gravedad=g).count() for g in Alerta.ORDEN_GRAVEDAD},
        'gravedades': Alerta.GRAVEDADES,
        'estados': Alerta.ESTADOS,
        'ultima_evaluacion': ConfiguracionAlertas.para_hogar(request.user.hogar).ultima_evaluacion,
    })


def _alerta(request, pk):
    return get_object_or_404(Alerta, pk=pk, hogar=request.user.hogar)


@login_required
@personal_requerido
@require_POST
def atender(request, pk):
    alerta = _alerta(request, pk)
    if not puede_atender(request.user, alerta):
        messages.error(request, 'Esta alerta no está dirigida a su rol.')
        return _volver(request)
    form = AtenderForm(request.POST)
    form.is_valid()
    try:
        services.atender(alerta, request.user, form.cleaned_data.get('nota', ''))
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return _volver(request)
    _auditar(request, RegistroAuditoria.ALERTA_ATENDIDA, f'Alerta #{alerta.pk} atendida: {alerta.titulo[:150]}')
    messages.success(request, 'Alerta marcada como atendida.')
    return _volver(request)


@login_required
@personal_requerido
@require_POST
def descartar(request, pk):
    alerta = _alerta(request, pk)
    if not puede_descartar(request.user, alerta):
        messages.error(request, 'No tiene permiso para descartar esta alerta.')
        return _volver(request)
    form = DescartarForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Escriba por qué no aplica.')
        return _volver(request)
    try:
        services.descartar(alerta, request.user, form.cleaned_data['motivo'])
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return _volver(request)
    _auditar(request, RegistroAuditoria.ALERTA_DESCARTADA,
             f'Alerta #{alerta.pk} descartada: {alerta.titulo[:120]} (motivo: {form.cleaned_data["motivo"][:120]})')
    messages.success(request, 'Alerta descartada.')
    return _volver(request)


@login_required
@publicar_requerido
def aviso_crear(request):
    inicial = {}
    if request.GET.get('residente', '').isdigit():
        inicial['residente'] = request.GET['residente']
    form = AvisoForm(request.POST or None, hogar=request.user.hogar, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        aviso = services.publicar_aviso(request.user, d['titulo'], d['mensaje'], d['gravedad'], d['roles'],
                                        d['horas'], residente=d['residente'])
        _auditar(request, RegistroAuditoria.AVISO_CREADO, f'Aviso #{aviso.pk} publicado para {", ".join(d["roles"])}: {aviso.titulo[:120]}')
        messages.success(request, 'Aviso publicado.')
        return redirect('alertas_bandeja')
    return render(request, 'alertas/aviso_form.html', {'form': form})


@login_required
@configurar_requerido
def configuracion(request):
    config = ConfiguracionAlertas.para_hogar(request.user.hogar)
    form = ConfiguracionForm(request.POST or None, config=config)
    if request.method == 'POST' and form.is_valid():
        form.guardar()
        evaluar_hogar(request.user.hogar)
        _auditar(request, RegistroAuditoria.CONFIGURACION_ALERTAS,
                 f'Configuración de alertas actualizada (reglas desactivadas: {", ".join(config.reglas_desactivadas) or "ninguna"})')
        messages.success(request, 'Configuración guardada y alertas reevaluadas.')
        return redirect('alertas_configuracion')
    return render(request, 'alertas/configuracion.html', {'form': form})
