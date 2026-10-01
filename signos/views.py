import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente

from . import parametros as P
from . import services
from .forms import AnularForm, ControlForm, LiquidosForm, RangoResidenteForm, RangosHogarForm
from .models import ControlSignos, RangoResidente, RangosHogar, RegistroLiquidos
from .permisos import (liquidos_requerido, puede_anular, puede_rango_hogar, puede_rango_residente,
                       puede_registrar, puede_registrar_liquidos, rango_hogar_requerido,
                       rango_residente_requerido, registro_requerido, ver_requerido)


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=request.user, accion=accion, descripcion=descripcion, ip_address=get_client_ip(request),
    )


def _residente(request, pk, activo=False):
    filtros = {'pk': pk, 'hogar': request.user.hogar}
    if activo:
        filtros['activo'] = True
    return get_object_or_404(Residente, **filtros)


def _fmt(v, decimales):
    return None if v is None else float(round(v, decimales))


# ── Tablero del hogar ───────────────────────────────────────────────

@login_required
@ver_requerido
def tablero(request):
    """Último control de cada residente activo, con lo fuera de rango
    resaltado, horas desde la última toma y días sin deposición."""
    residentes = sorted(Residente.objects.filter(hogar=request.user.hogar, activo=True).select_related('cama_actual'),
                        key=lambda r: r.get_nombre())
    filas = []
    ahora = timezone.now()
    for r in residentes:
        control = services.ultimo_control(r)
        rangos = services.rangos_efectivos(r)
        celdas = {}
        if control:
            for codigo, d in services.interpretar_control(control, rangos).items():
                celdas[codigo] = d
        dias_dep, _ = services.dias_sin_deposicion(r)
        filas.append({
            'residente': r,
            'nombre': r.get_nombre(),
            'control': control,
            'celdas': celdas,
            'horas': int((ahora - control.fecha_hora).total_seconds() // 3600) if control else None,
            'dias_sin_deposicion': dias_dep,
        })
    return render(request, 'signos/tablero.html', {
        'filas': filas,
        'parametros': P.PARAMETROS,
        'puede_registrar': puede_registrar(request.user),
        'puede_rango_hogar': puede_rango_hogar(request.user),
    })


# ── Residente ───────────────────────────────────────────────────────

def _series(controles, rangos):
    """Datos para las gráficas: una por parámetro, presión junta."""
    graficas = []
    orden = list(reversed(controles))  # cronológico
    etiquetas = [timezone.localtime(c.fecha_hora).strftime('%d/%m %H:%M') for c in orden]

    def serie(codigo):
        return [_fmt(getattr(c, codigo), P.POR_CODIGO[codigo].decimales) if codigo in P.POR_CODIGO
                else _fmt(getattr(c, codigo), 1) for c in orden]

    if any(c.pas is not None for c in orden):
        graficas.append({'id': 'presion', 'titulo': 'Presión arterial (mmHg)', 'datos': json.dumps({
            'labels': etiquetas,
            'series': [{'label': 'Sistólica', 'data': serie('pas'), 'color': '#0B3D62'},
                       {'label': 'Diastólica', 'data': serie('pad'), 'color': '#4F9E86'}],
            'rango': None,
        })})
    for codigo in ['fc', 'fr', 'temperatura', 'spo2', 'glucometria', 'dolor']:
        if not any(getattr(c, codigo) is not None for c in orden):
            continue
        p = P.POR_CODIGO[codigo]
        r = rangos[codigo]['rango']
        graficas.append({'id': codigo, 'titulo': f'{p.nombre} ({p.unidad})', 'datos': json.dumps({
            'labels': etiquetas,
            'series': [{'label': p.corto, 'data': serie(codigo), 'color': '#0B3D62'}],
            'rango': {'min': _fmt(r['normal_min'], 1), 'max': _fmt(r['normal_max'], 1)},
        })})
    pesos = [c for c in orden if c.peso is not None]
    if pesos:
        graficas.append({'id': 'peso', 'titulo': 'Peso (kg)', 'datos': json.dumps({
            'labels': [timezone.localtime(c.fecha_hora).strftime('%d/%m') for c in pesos],
            'series': [{'label': 'Peso', 'data': [float(c.peso) for c in pesos], 'color': '#0B3D62'}],
            'rango': None, 'solo_puntos_con_dato': True,
        })})
    return graficas


@login_required
@ver_requerido
def residente(request, pk):
    residente = _residente(request, pk)
    dias = request.GET.get('dias', '7')
    dias = int(dias) if dias in ('1', '7', '30', '90') else 7
    desde = timezone.now() - timedelta(days=dias)
    rangos = services.rangos_efectivos(residente)
    todos = list(ControlSignos.objects.filter(residente=residente, fecha_hora__gte=desde)
                 .select_related('registrado_por', 'anulado_por').order_by('-fecha_hora'))
    vigentes = [c for c in todos if not c.anulado]
    for c in todos:
        c.lectura = services.interpretar_control(c, rangos)
        c.puede_anular = puede_anular(request.user, c)

    hoy = timezone.localdate()
    balances = []
    for i in range(min(dias, 14) - 1, -1, -1):
        fecha = hoy - timedelta(days=i)
        b = services.balance_del_dia(residente, fecha)
        if b['registros']:
            balances.append({'fecha': fecha, **b})
    liquidos_hoy = list(RegistroLiquidos.objects.filter(
        residente=residente, fecha_hora__date__gte=hoy - timedelta(days=1),
    ).select_related('registrado_por').order_by('-fecha_hora'))
    for l in liquidos_hoy:
        l.puede_anular = puede_anular(request.user, l)

    ultimo = vigentes[0] if vigentes else services.ultimo_control(residente)
    if ultimo is not None and not hasattr(ultimo, 'lectura'):
        ultimo.lectura = services.interpretar_control(ultimo, rangos)
    dias_dep, ref_dep = services.dias_sin_deposicion(residente)
    horas_diu, ref_diu = services.horas_sin_diuresis(residente)
    peso = services.cambio_de_peso(residente)

    return render(request, 'signos/residente.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'dias': dias,
        'controles': todos,
        'ultimo': ultimo,
        'graficas': _series(vigentes, rangos),
        'rangos': [{'parametro': P.POR_CODIGO[c], 'texto': P.texto_rango(d['rango'], P.POR_CODIGO[c].decimales),
                    **d} for c, d in rangos.items()],
        'parametros': P.PARAMETROS,
        'eliminacion': services.eliminacion_por_dia(residente, 14),
        'dias_sin_deposicion': dias_dep, 'ultima_deposicion': ref_dep,
        'horas_sin_diuresis': horas_diu, 'ultima_diuresis': ref_diu,
        'balance_hoy': services.balance_del_dia(residente),
        'balances': balances,
        'balances_json': json.dumps({'labels': [b['fecha'].strftime('%d/%m') for b in balances],
                                     'ingresos': [b['ingresos'] for b in balances],
                                     'egresos': [-b['egresos'] for b in balances],
                                     'balance': [b['balance'] for b in balances]}),
        'liquidos': liquidos_hoy,
        'cambio_peso': peso,
        'anular_form': AnularForm(),
        'puede_registrar': puede_registrar(request.user) and residente.activo,
        'puede_registrar_liquidos': puede_registrar_liquidos(request.user) and residente.activo,
        'puede_rango_residente': puede_rango_residente(request.user),
    })


@login_required
@registro_requerido
def control_crear(request, pk):
    residente = _residente(request, pk, activo=True)
    form = ControlForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        control = form.save(commit=False)
        control.residente = residente
        control.registrado_por = request.user
        control.save()
        criticos, fuera = services.hallazgos(control)
        _auditar(request, RegistroAuditoria.SIGNOS_REGISTRADOS,
                 f'Signos vitales registrados para el residente #{residente.pk} (control #{control.pk})')
        if criticos:
            messages.error(request, 'Valores críticos: ' + '; '.join(criticos) +
                           '. Se generó una alerta para el médico y el jefe de enfermería. Informe de inmediato.')
        elif fuera:
            messages.warning(request, 'Signos guardados. Fuera de rango: ' + '; '.join(fuera) + '.')
        else:
            messages.success(request, 'Signos vitales guardados.')
        siguiente = request.POST.get('siguiente')
        if siguiente == 'tablero':
            return redirect('signos_tablero')
        return redirect('signos_residente', pk=residente.pk)
    return render(request, 'signos/control_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(),
        'rangos_json': {c: {k: (None if v is None else float(v)) for k, v in d['rango'].items()}
                        for c, d in services.rangos_efectivos(residente).items()},
        'siguiente': request.GET.get('siguiente', ''),
    })


@login_required
@liquidos_requerido
def liquidos_crear(request, pk):
    residente = _residente(request, pk, activo=True)
    form = LiquidosForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        registro = form.save(commit=False)
        registro.residente = residente
        registro.registrado_por = request.user
        registro.save()
        _auditar(request, RegistroAuditoria.LIQUIDOS_REGISTRADOS,
                 f'{registro.get_tipo_display()} de {registro.cantidad_ml} mL para el residente #{residente.pk}')
        messages.success(request, f'Registrado: {registro.get_via_display().lower()}, {registro.cantidad_ml} mL.')
        if request.POST.get('otro'):
            return redirect('signos_liquidos_crear', pk=residente.pk)
        return redirect(f"{redirect('signos_residente', pk=residente.pk).url}#liquidos")
    return render(request, 'signos/liquidos_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(),
        'balance_hoy': services.balance_del_dia(residente),
    })


def _anular(request, registro, etiqueta):
    if not puede_anular(request.user, registro):
        messages.error(request, 'No puede anular este registro (solo quien lo hizo, en las primeras 24 horas, '
                                'o el médico o el jefe de enfermería).')
    else:
        form = AnularForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Escriba el motivo de la anulación.')
        else:
            try:
                services.anular(registro, request.user, form.cleaned_data['motivo'])
            except ValueError as e:
                messages.error(request, str(e))
            else:
                _auditar(request, RegistroAuditoria.SIGNOS_ANULADOS,
                         f'{etiqueta} #{registro.pk} anulado (residente #{registro.residente_id}): '
                         f'{form.cleaned_data["motivo"][:150]}')
                messages.success(request, f'{etiqueta} anulado. Queda visible en el historial.')
    return redirect('signos_residente', pk=registro.residente_id)


@login_required
@ver_requerido
@require_POST
def control_anular(request, pk):
    control = get_object_or_404(ControlSignos, pk=pk, residente__hogar=request.user.hogar)
    return _anular(request, control, 'Control de signos')


@login_required
@ver_requerido
@require_POST
def liquidos_anular(request, pk):
    registro = get_object_or_404(RegistroLiquidos, pk=pk, residente__hogar=request.user.hogar)
    return _anular(request, registro, 'Registro de líquidos')


# ── Rangos ──────────────────────────────────────────────────────────

@login_required
@rango_residente_requerido
def rango_residente(request, pk):
    residente = _residente(request, pk)
    inicial = {}
    codigo = request.GET.get('parametro')
    if codigo in P.POR_CODIGO:
        inicial = {'parametro': codigo, **services.rangos_efectivos(residente)[codigo]['rango']}
    form = RangoResidenteForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        nuevo = form.save(commit=False)
        anterior = RangoResidente.objects.filter(residente=residente, parametro=nuevo.parametro, activo=True).first()
        if anterior:
            anterior.activo = False
            anterior.inactivado_por = request.user
            anterior.fecha_inactivacion = timezone.now()
            anterior.save(update_fields=['activo', 'inactivado_por', 'fecha_inactivacion'])
        nuevo.residente = residente
        nuevo.definido_por = request.user
        nuevo.save()
        p = P.POR_CODIGO[nuevo.parametro]
        _auditar(request, RegistroAuditoria.RANGO_SIGNOS,
                 f'Rango de {p.nombre.lower()} del residente #{residente.pk}: '
                 f'{P.texto_rango(nuevo.como_dict(), p.decimales)} (motivo: {nuevo.motivo[:120]})')
        messages.success(request, f'Rango de {p.nombre.lower()} guardado para {residente.get_nombre()}.')
        return redirect(f"{redirect('signos_residente', pk=residente.pk).url}#rangos")
    return render(request, 'signos/rango_residente_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(),
        'historial': RangoResidente.objects.filter(residente=residente).select_related('definido_por', 'inactivado_por'),
    })


@login_required
@rango_residente_requerido
@require_POST
def rango_residente_quitar(request, pk):
    regla = get_object_or_404(RangoResidente, pk=pk, residente__hogar=request.user.hogar, activo=True)
    regla.activo = False
    regla.inactivado_por = request.user
    regla.fecha_inactivacion = timezone.now()
    regla.save(update_fields=['activo', 'inactivado_por', 'fecha_inactivacion'])
    _auditar(request, RegistroAuditoria.RANGO_SIGNOS,
             f'Rango propio de {regla.parametro_obj.nombre.lower()} retirado del residente #{regla.residente_id}; '
             f'vuelve al rango del hogar')
    messages.success(request, 'Listo: este signo vuelve a usar el rango del hogar.')
    return redirect(f"{redirect('signos_residente', pk=regla.residente_id).url}#rangos")


@login_required
@rango_hogar_requerido
def rangos_hogar(request):
    obj = RangosHogar.para_hogar(request.user.hogar)
    form = RangosHogarForm(request.POST or None, rangos=obj)
    if request.method == 'POST' and form.is_valid():
        obj.rangos = form.como_json()
        obj.actualizado_por = request.user
        obj.save()
        _auditar(request, RegistroAuditoria.RANGO_SIGNOS,
                 f'Rangos de signos vitales del hogar actualizados ({", ".join(obj.rangos) or "valores por defecto"})')
        messages.success(request, 'Rangos del hogar guardados.')
        return redirect('signos_rangos_hogar')
    return render(request, 'signos/rangos_hogar.html', {'form': form, 'rangos': obj})
