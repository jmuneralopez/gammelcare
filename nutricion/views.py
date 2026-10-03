from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente

from . import services
from .forms import ConfiguracionForm, DietaForm
from .models import NOMBRE_COMIDA, ConfiguracionNutricion, RegistroIngesta, TipoDieta
from .permisos import (configuracion_requerido, dieta_requerido, ingesta_requerido, liquidos_requerido,
                       puede_configurar, puede_corregir, puede_dieta, puede_ingesta, puede_liquidos,
                       ver_requerido)


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(usuario=request.user, accion=accion, descripcion=descripcion,
                                     ip_address=get_client_ip(request))


def _residente(request, pk, activo=False):
    filtros = {'pk': pk, 'hogar': request.user.hogar}
    if activo:
        filtros['activo'] = True
    return get_object_or_404(Residente, **filtros)


def _volver(request, defecto, ancla=''):
    destino = request.POST.get('volver') or ''
    if not (destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()})):
        destino = defecto
    if ancla and '#' not in destino:
        destino += ancla
    return destino


# ── Planilla de comidas ─────────────────────────────────────────────

@login_required
@ver_requerido
def planilla(request):
    config = ConfiguracionNutricion.para_hogar(request.user.hogar)
    hoy = timezone.localdate()
    fecha = parse_date(request.GET.get('fecha', '') or '') or hoy
    if fecha > hoy:
        fecha = hoy
    codigos = [c for c, _, _ in config.comidas()]
    comida = request.GET.get('comida')
    if comida not in codigos:
        comida = services.comida_actual(config) if fecha == hoy else (codigos[0] if codigos else None)
    filas = services.planilla(request.user.hogar, fecha, comida, config) if comida else []
    return render(request, 'nutricion/planilla.html', {
        'filas': filas, 'fecha': fecha, 'hoy': hoy, 'comida': comida, 'nombre_comida': NOMBRE_COMIDA.get(comida, ''),
        'comidas': config.comidas(), 'config': config, 'consumos': RegistroIngesta.CONSUMOS,
        'dia_anterior': fecha - timedelta(days=1), 'dia_siguiente': fecha + timedelta(days=1) if fecha < hoy else None,
        'puede_ingesta': puede_ingesta(request.user), 'puede_liquidos': puede_liquidos(request.user),
        'puede_configurar': puede_configurar(request.user),
        'registradas': sum(1 for f in filas if f['registro']),
    })


@login_required
@require_POST
@ingesta_requerido
def registrar_ingesta(request, pk):
    residente = _residente(request, pk, activo=True)
    fecha = parse_date(request.POST.get('fecha', '') or '') or timezone.localdate()
    comida, consumo = request.POST.get('comida', ''), request.POST.get('consumo', '')
    anterior = RegistroIngesta.objects.filter(residente=residente, fecha=fecha, comida=comida, anulado=False).first()
    if anterior and not puede_corregir(request.user, anterior):
        messages.error(request, 'Ese registro ya existe y no puede corregirlo: pídaselo al jefe de enfermería.')
    else:
        try:
            r = services.registrar_ingesta(residente, fecha, comida, consumo, request.user,
                                           observaciones=request.POST.get('observaciones', '').strip())
        except ValueError as e:
            messages.error(request, str(e))
        else:
            if anterior:
                _auditar(request, RegistroAuditoria.INGESTA_CORREGIDA,
                         f'{NOMBRE_COMIDA[comida]} del {fecha:%d/%m/%Y} del residente #{residente.pk}: '
                         f'"{anterior.get_consumo_display()}" → "{r.get_consumo_display()}"')
            messages.success(request, f'{residente.get_nombre()}: {NOMBRE_COMIDA[comida].lower()} — '
                                      f'{r.get_consumo_display().lower()}.')
    return redirect(_volver(request, reverse('nutricion_planilla'), f'#res-{residente.pk}'))


@login_required
@require_POST
@liquidos_requerido
def vaso(request, pk):
    residente = _residente(request, pk, activo=True)
    config = ConfiguracionNutricion.para_hogar(request.user.hogar)
    try:
        cantidad = int(request.POST.get('cantidad') or config.vaso_ml)
    except ValueError:
        cantidad = config.vaso_ml
    cantidad = max(20, min(cantidad, 1000))
    services.registrar_vaso(residente, request.user, cantidad)
    total = services.liquidos_del_dia(residente)
    messages.success(request, f'{residente.get_nombre()}: +{cantidad} mL (hoy {total} mL).')
    return redirect(_volver(request, reverse('nutricion_planilla'), f'#res-{residente.pk}'))


# ── Residente ───────────────────────────────────────────────────────

@login_required
@ver_requerido
def residente(request, pk):
    residente = _residente(request, pk)
    config = ConfiguracionNutricion.para_hogar(request.user.hogar)
    dieta = services.dieta_vigente(residente)
    from signos import services as sv
    pesos = list(residente.controles_signos.filter(anulado=False, peso__isnull=False).order_by('-fecha_hora')[:6])
    cambio = sv.cambio_de_peso(residente, dias=30)
    cuadricula = services.cuadricula(residente, config, dias=7)
    return render(request, 'nutricion/residente.html', {
        'residente': residente, 'nombre': residente.get_nombre(), 'dieta': dieta,
        'historial': residente.dietas.select_related('tipo', 'registrado_por').exclude(pk=getattr(dieta, 'pk', None))[:10],
        'alergias': services.alergias_alimentarias(residente), 'comidas': config.comidas(),
        'cuadricula': cuadricula, 'meta': services.meta_liquidos(residente, dieta, config),
        'promedio_semana': services.promedio([c for f in cuadricula for c in f['celdas'] if c]),
        'pesos': pesos, 'cambio_peso': cambio,
        'puede_dieta': puede_dieta(request.user) and residente.activo,
    })


@login_required
@dieta_requerido
def dieta(request, pk):
    residente = _residente(request, pk, activo=True)
    actual = services.dieta_vigente(residente)
    form = DietaForm(request.POST or None, instance=actual, hogar=request.user.hogar)
    if request.method == 'POST' and form.is_valid():
        nueva = services.cambiar_dieta(residente, form.save(commit=False), request.user)
        _auditar(request, RegistroAuditoria.DIETA_INDICADA, f'Dieta del residente #{residente.pk}: {nueva.resumen}')
        messages.success(request, 'Dieta guardada. La lista para cocina ya la muestra.')
        return redirect('nutricion_residente', pk=residente.pk)
    return render(request, 'nutricion/dieta_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(), 'actual': actual,
        'alergias': services.alergias_alimentarias(residente),
    })


@login_required
@require_POST
@dieta_requerido
def tipo_dieta_crear_rapido(request):
    nombre = request.POST.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'errors': {'nombre': ['Escriba el nombre de la dieta.']}}, status=400)
    if TipoDieta.disponibles(request.user.hogar).filter(nombre__iexact=nombre).exists():
        return JsonResponse({'errors': {'nombre': [f'Ya existe la dieta "{nombre}".']}}, status=400)
    t = TipoDieta.objects.create(hogar=request.user.hogar, nombre=nombre[:80], creado_por=request.user,
                                 descripcion=request.POST.get('descripcion', '').strip()[:255])
    _auditar(request, RegistroAuditoria.TIPO_DIETA_CREADO, f'Tipo de dieta "{t.nombre}"')
    return JsonResponse({'id': t.pk, 'text': t.nombre})


# ── Cocina y configuración ──────────────────────────────────────────

@login_required
@ver_requerido
def cocina(request):
    grupos, sin_dieta = services.lista_cocina(request.user.hogar)
    return render(request, 'nutricion/cocina.html', {
        'grupos': grupos, 'sin_dieta': sin_dieta, 'hoy': timezone.localtime(),
        'total': sum(len(g['residentes']) for g in grupos) + len(sin_dieta),
        'comidas': ConfiguracionNutricion.para_hogar(request.user.hogar).comidas(),
    })


@login_required
@configuracion_requerido
def configuracion(request):
    config = ConfiguracionNutricion.para_hogar(request.user.hogar)
    form = ConfiguracionForm(request.POST or None, instance=config)
    if request.method == 'POST' and form.is_valid():
        c = form.save(commit=False)
        c.actualizado_por = request.user
        c.save()
        _auditar(request, RegistroAuditoria.CONFIGURACION_NUTRICION,
                 f'Comidas: {", ".join(n for _, n, _ in c.comidas())}; vaso {c.vaso_ml} mL; meta {c.meta_liquidos_ml} mL')
        messages.success(request, 'Configuración de nutrición guardada.')
        return redirect('nutricion_planilla')
    return render(request, 'nutricion/configuracion.html', {'form': form})
