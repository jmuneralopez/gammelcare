"""Pantallas de consulta, impresión y configuración del módulo de
medicamentos: historial de suministros, Kardex mensual, hoja de
tratamiento, vencimientos, devolución a la familia con su acta, acta de
recepción y configuración del hogar.

Viven aparte de views.py para no seguir creciendo ese archivo.
"""
import calendar
import csv
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente
from usuarios.decorators import (ajuste_inventario_requerido, clinico_requerido, ingreso_medicamento_requerido,
                                 rol_requerido)
from usuarios.models import Rol

from . import services
from .forms_consultas import ConfiguracionForm, DevolucionForm
from .models import Administracion, ConfiguracionMedicamentos, IngresoMedicamento, MovimientoInventario, Prescripcion


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(usuario=request.user, accion=accion, descripcion=descripcion,
                                     ip_address=get_client_ip(request))


def _residente(request, pk):
    return get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)


def _rango(request, dias=30):
    hoy = timezone.localdate()
    hasta = parse_date(request.GET.get('hasta', '') or '') or hoy
    desde = parse_date(request.GET.get('desde', '') or '') or (hasta - timedelta(days=dias - 1))
    if desde > hasta:
        desde, hasta = hasta, desde
    return desde, hasta


def _dt(fecha, fin=False):
    base = datetime.combine(fecha + timedelta(days=1) if fin else fecha, datetime.min.time())
    return timezone.make_aware(base)


# ── Historial de suministros ───────────────────────────────────

def _historial_qs(hogar, desde, hasta, residente=None, medicamento=None, estado=''):
    qs = (Administracion.objects
          .filter(residente__hogar=hogar, fecha_administracion__gte=_dt(desde), fecha_administracion__lt=_dt(hasta, True))
          .select_related('residente', 'prescripcion__medicamento', 'administrada_por', 'ingreso_usado', 'anulada_por')
          .order_by('-fecha_administracion'))
    if residente is not None:
        qs = qs.filter(residente=residente)
    if medicamento:
        qs = qs.filter(prescripcion__medicamento_id=medicamento)
    if estado == 'suministrado':
        qs = qs.filter(estado=Administracion.ADMINISTRADO, anulada=False)
    elif estado == 'no_suministrado':
        qs = qs.filter(estado=Administracion.NO_ADMINISTRADO, anulada=False)
    elif estado == 'anulado':
        qs = qs.filter(anulada=True)
    elif estado == 'botiquin':
        qs = qs.exclude(motivo_uso_botiquin='').filter(anulada=False)
    return qs


def _csv(request, nombre, filas, encabezado):
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
    respuesta.write('﻿')  # para que Excel reconozca las tildes
    w = csv.writer(respuesta, delimiter=';')
    w.writerow(encabezado)
    for f in filas:
        w.writerow(f)
    return respuesta


def _fila_csv(a, con_residente):
    estado = 'Anulado' if a.anulada else a.get_estado_display()
    fila = [timezone.localtime(a.fecha_administracion).strftime('%d/%m/%Y %H:%M'),
            timezone.localtime(a.fecha_programada).strftime('%d/%m/%Y %H:%M') if a.fecha_programada else 'Si es necesario']
    if con_residente:
        fila.append(a.residente.get_nombre())
    fila += [str(a.prescripcion.medicamento), estado,
             f'{a.cantidad_administrada}' if a.cantidad_administrada is not None else '',
             a.get_motivo_no_administracion_display() if a.motivo_no_administracion else '',
             'Sí (' + a.get_motivo_uso_botiquin_display() + ')' if a.motivo_uso_botiquin else '',
             a.ingreso_usado.lote if a.ingreso_usado_id else '',
             a.observacion, a.administrada_por.get_full_name() or a.administrada_por.username]
    return fila


def _historial(request, residente=None):
    desde, hasta = _rango(request)
    medicamento = request.GET.get('medicamento', '')
    medicamento = int(medicamento) if medicamento.isdigit() else None
    estado = request.GET.get('estado', '')
    qs = _historial_qs(request.user.hogar, desde, hasta, residente, medicamento, estado)
    if request.GET.get('formato') == 'csv':
        if not request.user.tiene_rol(*Rol.ROLES_EXPORTACION):
            messages.error(request, 'Su rol no exporta el historial.')
            return redirect(request.path)
        _auditar(request, RegistroAuditoria.EXPORTACION,
                 f'Exportación del historial de suministros {desde:%d/%m/%Y}–{hasta:%d/%m/%Y}'
                 + (f' del residente #{residente.pk}' if residente else ' del hogar'))
        encabezado = ['Registrado', 'Programado'] + (['Residente'] if residente is None else []) + [
            'Medicamento', 'Estado', 'Cantidad', 'Motivo (no suministrado)', 'Del botiquín', 'Lote', 'Observación',
            'Registró']
        return _csv(request, f'suministros_{desde:%Y%m%d}_{hasta:%Y%m%d}.csv',
                    (_fila_csv(a, residente is None) for a in qs), encabezado)
    base = Prescripcion.objects.filter(residente__hogar=request.user.hogar)
    if residente is not None:
        base = base.filter(residente=residente)
    medicamentos = sorted({p.medicamento for p in base.select_related('medicamento')}, key=str)
    registros = list(qs[:500])
    return render(request, 'medicamentos/historial.html', {
        'residente': residente, 'nombre': residente.get_nombre() if residente else None,
        'registros': registros, 'recortado': qs.count() > 500,
        'desde': desde, 'hasta': hasta, 'medicamento': medicamento, 'estado': estado,
        'medicamentos': medicamentos,
        'puede_exportar': request.user.tiene_rol(*Rol.ROLES_EXPORTACION),
        'query_csv': request.GET.urlencode(),
        'totales': {
            'suministrados': sum(1 for r in registros if r.estado == Administracion.ADMINISTRADO and not r.anulada),
            'no_suministrados': sum(1 for r in registros if r.estado == Administracion.NO_ADMINISTRADO and not r.anulada),
            'anulados': sum(1 for r in registros if r.anulada),
        },
    })


@login_required
@clinico_requerido
def historial_residente(request, pk):
    return _historial(request, _residente(request, pk))


@login_required
@clinico_requerido
def historial_hogar(request):
    return _historial(request)


# ── Kardex mensual ─────────────────────────────────────────────

@login_required
@clinico_requerido
def kardex(request, pk):
    residente = _residente(request, pk)
    hoy = timezone.localdate()
    try:
        anio, mes = (int(x) for x in request.GET.get('mes', '').split('-'))
        date(anio, mes, 1)
    except (ValueError, TypeError):
        anio, mes = hoy.year, hoy.month
    ndias = calendar.monthrange(anio, mes)[1]
    dias = [date(anio, mes, d) for d in range(1, ndias + 1)]
    inicio, fin = _dt(dias[0]), _dt(dias[-1], True)
    tz = timezone.get_current_timezone()

    admins = (Administracion.objects.filter(residente=residente, anulada=False, fecha_administracion__gte=inicio - timedelta(days=1),
                                            fecha_administracion__lt=fin + timedelta(days=1))
              .select_related('administrada_por'))
    por_programada = {}
    prn_por_dia = {}
    for a in admins:
        if a.fecha_programada and a.horario_id:
            por_programada[(a.prescripcion_id, timezone.localtime(a.fecha_programada).replace(second=0, microsecond=0))] = a
        elif a.estado == Administracion.ADMINISTRADO:
            d = timezone.localdate(a.fecha_administracion)
            prn_por_dia.setdefault((a.prescripcion_id, d), []).append(a)

    prescripciones = (Prescripcion.objects.filter(residente=residente, fecha_inicio__lte=dias[-1])
                      .exclude(fecha_fin__lt=dias[0]).select_related('medicamento').prefetch_related('horarios')
                      .order_by('medicamento__nombre_generico'))
    filas = []
    ahora = timezone.localtime()
    for p in prescripciones:
        if p.es_prn():
            celdas = []
            for d in dias:
                lista = prn_por_dia.get((p.pk, d), [])
                celdas.append({'tipo': 'prn', 'n': len(lista)} if lista else {'tipo': 'vacio'})
            filas.append({'p': p, 'hora': 'Si es necesario', 'celdas': celdas})
            continue
        for h in p.horarios.all():
            celdas = []
            for d in dias:
                activa = (p.fecha_inicio <= d and (not p.fecha_fin or d <= p.fecha_fin)
                          and 'LMXJVSD'[d.weekday()] in p.dias_semana
                          and not (p.estado == Prescripcion.SUSPENDIDA and p.fecha_suspension
                                   and timezone.localdate(p.fecha_suspension) < d))
                if not activa:
                    celdas.append({'tipo': 'vacio'})
                    continue
                programada = timezone.make_aware(datetime.combine(d, h.hora), tz)
                a = por_programada.get((p.pk, timezone.localtime(programada).replace(second=0, microsecond=0)))
                if a is None:
                    celdas.append({'tipo': 'sin_registro' if programada < ahora else 'futuro'})
                elif a.estado == Administracion.ADMINISTRADO:
                    u = a.administrada_por
                    iniciales = ''.join(x[0] for x in (u.get_full_name() or u.username).split()[:2]).upper()
                    celdas.append({'tipo': 'ok', 'iniciales': iniciales, 'titulo': f'{a.cantidad_administrada} · {u}'})
                else:
                    celdas.append({'tipo': 'no', 'titulo': a.get_motivo_no_administracion_display()})
            filas.append({'p': p, 'hora': h.hora.strftime('%H:%M'), 'celdas': celdas})
    mes_anterior = (dias[0] - timedelta(days=1)).strftime('%Y-%m')
    mes_siguiente = (dias[-1] + timedelta(days=1)).strftime('%Y-%m')
    _auditar(request, RegistroAuditoria.CONSULTA_EXPEDIENTE, f'Consulta del Kardex {anio}-{mes:02d} del residente #{residente.pk}')
    return render(request, 'medicamentos/kardex.html', {
        'residente': residente, 'nombre': residente.get_nombre(), 'dias': dias, 'filas': filas,
        'mes_titulo': dias[0], 'mes_anterior': mes_anterior, 'mes_siguiente': mes_siguiente, 'hoy': hoy,
    })


# ── Hoja de tratamiento (imprimible) ───────────────────────────

@login_required
@clinico_requerido
def hoja_tratamiento(request, pk):
    residente = _residente(request, pk)
    hoy = timezone.localdate()
    ordenes = [p for p in (Prescripcion.objects.filter(residente=residente, estado=Prescripcion.ACTIVA)
                           .select_related('medicamento', 'diagnostico').prefetch_related('horarios')
                           .order_by('tipo_pauta', 'medicamento__nombre_generico'))
               if not p.fecha_fin or p.fecha_fin >= hoy]
    _auditar(request, RegistroAuditoria.CONSULTA_EXPEDIENTE, f'Hoja de tratamiento del residente #{residente.pk}')
    return render(request, 'medicamentos/hoja_tratamiento.html', {
        'residente': residente, 'nombre': residente.get_nombre(), 'ordenes': ordenes, 'hoy': timezone.localtime(),
    })


# ── Vencimientos ───────────────────────────────────────────────

@login_required
@ingreso_medicamento_requerido
def vencimientos(request):
    hogar = request.user.hogar
    config = ConfiguracionMedicamentos.para_hogar(hogar)
    from django.db.models import Q
    lotes = (IngresoMedicamento.objects
             .filter(Q(hogar=hogar, residente__isnull=True) | Q(residente__hogar=hogar, residente__activo=True))
             .filter(cantidad_disponible__gt=0)
             .exclude(estado__in=[IngresoMedicamento.DESCARTADO, IngresoMedicamento.DEVUELTO])
             .select_related('residente', 'medicamento').order_by('fecha_vencimiento'))
    filtro = request.GET.get('ver', 'proximos')
    filas = []
    conteo = {'vencido': 0, 'rojo': 0, 'amarillo': 0, 'verde': 0}
    for l in lotes:
        s = l.semaforo(config.dias_semaforo_verde, config.dias_semaforo_amarillo)
        conteo[s] += 1
        if filtro == 'todos' or (filtro == 'proximos' and s != 'verde') or filtro == s:
            filas.append({'lote': l, 'semaforo': s, 'dias': l.dias_para_vencer(),
                          'nombre': l.residente.get_nombre() if l.residente_id else None})
    return render(request, 'medicamentos/vencimientos.html', {
        'filas': filas, 'filtro': filtro, 'conteo': conteo, 'config': config,
        'puede_descartar': request.user.tiene_rol(*Rol.ROLES_AJUSTE_INVENTARIO),
    })


# ── Devolución a la familia y actas ────────────────────────────

@login_required
@ajuste_inventario_requerido
def devolver(request, pk):
    """Devolver a la familia uno, varios o todos los lotes con saldo del cajón."""
    residente = _residente(request, pk)
    lotes = list(IngresoMedicamento.objects.filter(residente=residente, cantidad_disponible__gt=0)
                 .exclude(estado__in=[IngresoMedicamento.DESCARTADO, IngresoMedicamento.DEVUELTO])
                 .select_related('medicamento').order_by('medicamento__nombre_generico', 'fecha_vencimiento'))
    form = DevolucionForm(request.POST or None, lotes=lotes,
                          initial={'lotes': [str(l.pk) for l in lotes if str(l.pk) == request.GET.get('lote')]})
    if request.method == 'POST' and form.is_valid():
        devueltos = []
        for l in form.cleaned_data['lotes']:
            try:
                lote, saldo = services.devolver_lote(l, request.user, form.cleaned_data['entregado_a'],
                                                     form.cleaned_data['motivo'])
                devueltos.append(lote)
            except ValueError as e:
                messages.error(request, str(e))
        if devueltos:
            _auditar(request, RegistroAuditoria.DEVOLUCION_MEDICAMENTOS,
                     f'Devolución a la familia de {len(devueltos)} lote(s) del residente #{residente.pk} '
                     f'(entregado a {form.cleaned_data["entregado_a"][:80]})')
            messages.success(request, f'Devueltos {len(devueltos)} lote(s). Imprima el acta para la firma de quien recibe.')
            return redirect(f"{redirect('acta_devolucion', pk=residente.pk).url}?fecha={timezone.localdate():%Y-%m-%d}")
    return render(request, 'medicamentos/devolver.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(), 'lotes': lotes,
    })


@login_required
@clinico_requerido
def acta_devolucion(request, pk):
    residente = _residente(request, pk)
    fecha = parse_date(request.GET.get('fecha', '') or '') or timezone.localdate()
    movimientos = (MovimientoInventario.objects
                   .filter(ingreso__residente=residente, tipo=MovimientoInventario.DEVOLUCION_FAMILIA,
                           fecha__gte=_dt(fecha), fecha__lt=_dt(fecha, True))
                   .select_related('ingreso__medicamento', 'usuario').order_by('fecha'))
    return render(request, 'medicamentos/acta.html', {
        'tipo': 'devolucion', 'residente': residente, 'nombre': residente.get_nombre(), 'fecha': fecha,
        'filas': [{'medicamento': m.ingreso.medicamento, 'lote': m.ingreso.lote, 'vence': m.ingreso.fecha_vencimiento,
                   'cantidad': -m.cantidad, 'unidad': m.ingreso.get_unidad_display(), 'detalle': m.motivo,
                   'usuario': m.usuario} for m in movimientos],
    })


@login_required
@clinico_requerido
def acta_recepcion(request, pk):
    residente = _residente(request, pk)
    fecha = parse_date(request.GET.get('fecha', '') or '') or timezone.localdate()
    ingresos = (IngresoMedicamento.objects.filter(residente=residente, fecha_registro__gte=_dt(fecha),
                                                  fecha_registro__lt=_dt(fecha, True))
                .select_related('medicamento', 'recibido_por').order_by('fecha_registro'))
    return render(request, 'medicamentos/acta.html', {
        'tipo': 'recepcion', 'residente': residente, 'nombre': residente.get_nombre(), 'fecha': fecha,
        'filas': [{'medicamento': i.medicamento, 'lote': i.lote, 'vence': i.fecha_vencimiento,
                   'cantidad': i.cantidad_ingresada, 'unidad': i.get_unidad_display(),
                   'detalle': f'Entregó: {i.entregado_por}' if i.entregado_por else '', 'usuario': i.recibido_por}
                  for i in ingresos],
    })


# ── Configuración ──────────────────────────────────────────────

@login_required
@rol_requerido(Rol.ADMINISTRADOR, Rol.JEFE_ENFERMERIA)
def configuracion(request):
    config = ConfiguracionMedicamentos.para_hogar(request.user.hogar)
    form = ConfiguracionForm(request.POST or None, instance=config)
    if request.method == 'POST' and form.is_valid():
        form.save()
        _auditar(request, RegistroAuditoria.CONFIGURACION_MEDICAMENTOS, 'Configuración de medicamentos actualizada')
        messages.success(request, 'Configuración de medicamentos guardada.')
        return redirect('medicamentos_configuracion')
    return render(request, 'medicamentos/configuracion.html', {'form': form})
