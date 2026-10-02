import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente

from . import escalas as E
from . import services
from .forms import AnularForm, ConfiguracionForm, ItemsForm, PuntajeForm
from .models import ConfiguracionValoracion, Valoracion
from .permisos import (aplicar_requerido, configurar_requerido, puede_anular,
                       puede_aplicar, puede_configurar, ver_requerido)


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=request.user, accion=accion, descripcion=descripcion, ip_address=get_client_ip(request),
    )


@login_required
@ver_requerido
def tablero(request):
    """Matriz residentes × escalas exigidas: último puntaje y vencimientos."""
    config = ConfiguracionValoracion.para_hogar(request.user.hogar)
    exigidas = config.exigidas()
    residentes = sorted(Residente.objects.filter(hogar=request.user.hogar, activo=True), key=lambda r: r.get_nombre())
    filas = []
    for r in residentes:
        estado = {f['escala'].codigo: f for f in services.estado_por_escala(r, config)}
        filas.append({'residente': r, 'nombre': r.get_nombre(),
                      'celdas': [estado[e.codigo] for e in exigidas],
                      'vencidas': sum(1 for e in exigidas if estado[e.codigo]['vencida'])})
    return render(request, 'valoracion/tablero.html', {
        'filas': filas, 'exigidas': exigidas, 'puede_configurar': puede_configurar(request.user),
    })


@login_required
@ver_requerido
def residente(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    filas = services.estado_por_escala(residente)
    for f in filas:
        f['puede_aplicar'] = puede_aplicar(request.user, f['escala']) and residente.activo
    return render(request, 'valoracion/residente.html', {
        'residente': residente, 'nombre': residente.get_nombre(), 'filas': filas,
        'vencidas': [f for f in filas if f['vencida']],
    })


@login_required
@aplicar_requerido
def aplicar(request, pk, codigo):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar, activo=True)
    escala = E.POR_CODIGO.get(codigo)
    if escala is None:
        raise Http404('Escala desconocida.')
    if not puede_aplicar(request.user, escala):
        messages.error(request, f'Su rol no aplica la escala {escala.corto}.')
        return redirect('valoracion_residente', pk=residente.pk)
    Form = ItemsForm if escala.modo == 'items' else PuntajeForm
    form = Form(request.POST or None, escala=escala)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        if escala.modo == 'items':
            v = services.registrar(residente, escala, request.user, d['fecha'], respuestas=form.respuestas(),
                                   educacion=d.get('educacion', ''), observaciones=d['observaciones'])
        else:
            v = services.registrar(residente, escala, request.user, d['fecha'], puntaje=d['puntaje'],
                                   observaciones=d['observaciones'], cuidador=d.get('cuidador', ''))
        _auditar(request, RegistroAuditoria.VALORACION_REGISTRADA,
                 f'{escala.corto} aplicada al residente #{residente.pk}: {v.puntaje} ({v.interpretacion})')
        nivel = messages.warning if v.nivel in (E.MODERADO, E.GRAVE) else messages.success
        nivel(request, f'{escala.corto}: {v.puntaje} puntos — {v.interpretacion}.')
        return redirect('valoracion_detalle', pk=v.pk)
    anterior = services.vigentes(residente, escala.codigo).order_by('-fecha', '-fecha_registro').first()
    return render(request, 'valoracion/aplicar.html', {
        'form': form, 'escala': escala, 'residente': residente, 'nombre': residente.get_nombre(),
        'anterior': anterior,
        'bandas_json': [{'min': b.minimo, 'max': b.maximo, 'texto': b.texto, 'nivel': b.nivel} for b in escala.bandas],
        'puntos_json': {f'i_{i.codigo}': [p for p, _t in i.opciones] for i in escala.items},
        'ajustes_json': {c: a for c, _t, a in escala.extra.get('educacion', ())},
    })


@login_required
@ver_requerido
def detalle(request, pk):
    v = get_object_or_404(Valoracion.objects.select_related('residente', 'registrado_por', 'anulada_por'),
                          pk=pk, residente__hogar=request.user.hogar)
    historial = services.vigentes(v.residente, v.escala).order_by('fecha', 'fecha_registro')
    return render(request, 'valoracion/detalle.html', {
        'v': v, 'escala': v.definicion, 'residente': v.residente, 'nombre': v.residente.get_nombre(),
        'puede_anular': puede_anular(request.user, v),
        'puede_aplicar': puede_aplicar(request.user, v.definicion) and v.residente.activo,
        'grafica': json.dumps({'labels': [h.fecha.strftime('%d/%m/%Y') for h in historial],
                               'valores': [h.puntaje for h in historial],
                               'min': v.definicion.minimo, 'max': v.definicion.maximo}) if historial.count() > 1 else '',
        'anular_form': AnularForm(),
    })


@login_required
@ver_requerido
@require_POST
def anular(request, pk):
    v = get_object_or_404(Valoracion, pk=pk, residente__hogar=request.user.hogar)
    if not puede_anular(request.user, v):
        messages.error(request, 'Solo quien la aplicó (el mismo día) o el médico o el jefe de enfermería pueden anularla.')
        return redirect('valoracion_detalle', pk=v.pk)
    form = AnularForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Escriba el motivo de la anulación.')
        return redirect('valoracion_detalle', pk=v.pk)
    try:
        services.anular(v, request.user, form.cleaned_data['motivo'])
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('valoracion_detalle', pk=v.pk)
    _auditar(request, RegistroAuditoria.VALORACION_ANULADA,
             f'{v.definicion.corto} #{v.pk} anulada (residente #{v.residente_id}): {form.cleaned_data["motivo"][:150]}')
    messages.success(request, 'Valoración anulada. Queda en el historial.')
    return redirect('valoracion_residente', pk=v.residente_id)


@login_required
@configurar_requerido
def configuracion(request):
    config = ConfiguracionValoracion.para_hogar(request.user.hogar)
    form = ConfiguracionForm(request.POST or None, config=config)
    if request.method == 'POST' and form.is_valid():
        form.guardar(request.user)
        _auditar(request, RegistroAuditoria.CONFIGURACION_VALORACION,
                 'Periodicidad de escalas: ' + ', '.join(f'{k} {v}m' for k, v in config.periodicidad.items()))
        messages.success(request, 'Periodicidad guardada.')
        return redirect('valoracion_configuracion')
    return render(request, 'valoracion/configuracion.html', {'form': form})
