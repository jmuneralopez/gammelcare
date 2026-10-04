import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente

from . import services
from .forms import CierreForm, ConfiguracionForm, EventoForm, NotaForm, VigilanciaForm
from .models import (GRAVEDADES, TIPOS, ConfiguracionEventos, EventoAdverso, NotaEvento, VigilanciaEvento)
from .permisos import (analizar_requerido, configurar_requerido, puede_analizar, puede_reportar,
                       puede_supervisar, puede_vigilancia, reportar_requerido, supervision_requerido,
                       ve_quien_reporto, vigilancia_requerido)


def _auditar(request, accion, descripcion, anonimo=False):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=None if anonimo else request.user, accion=accion, descripcion=descripcion,
        ip_address=None if anonimo else get_client_ip(request),
    )


def _puede_ver_evento(usuario, evento):
    """Supervisión ve todo; el resto del personal clínico ve los eventos de
    los residentes (están en el expediente)."""
    return puede_supervisar(usuario) or usuario.es_clinico()


# ── Bandeja ─────────────────────────────────────────────────────────

@login_required
@reportar_requerido
def bandeja(request):
    """Supervisión: todos los eventos con filtros. Resto del personal: botón
    para reportar y los eventos que reportó con su nombre."""
    supervision = puede_supervisar(request.user)
    qs = EventoAdverso.objects.filter(hogar=request.user.hogar).select_related('residente')
    if not supervision:
        qs = qs.filter(reportado_por=request.user)
    estado = request.GET.get('estado', 'abiertos' if supervision else 'todos')
    tipo = request.GET.get('tipo', '')
    if estado == 'abiertos':
        qs = qs.filter(estado=EventoAdverso.ABIERTO)
    elif estado == 'cerrados':
        qs = qs.filter(estado=EventoAdverso.CERRADO)
    if tipo in dict(TIPOS):
        qs = qs.filter(tipo=tipo)
    eventos = list(qs[:300])
    vigilancias = list(services.vigilancias_pendientes(request.user.hogar, timezone.now() + timedelta(hours=2)))
    residentes = sorted(Residente.objects.filter(hogar=request.user.hogar, activo=True), key=lambda r: r.get_nombre())
    return render(request, 'eventos/bandeja.html', {
        'eventos': eventos, 'supervision': supervision, 'estado': estado, 'tipo': tipo, 'tipos': TIPOS,
        'vigilancias': vigilancias, 'puede_vigilancia': puede_vigilancia(request.user),
        'residentes': [(r.pk, r.get_nombre()) for r in residentes],
        'abiertos': EventoAdverso.objects.filter(hogar=request.user.hogar, estado=EventoAdverso.ABIERTO).count(),
        'config': ConfiguracionEventos.para_hogar(request.user.hogar),
    })


# ── Reporte ─────────────────────────────────────────────────────────

@login_required
@reportar_requerido
def reportar(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    config = ConfiguracionEventos.para_hogar(request.user.hogar)
    inicial = {}
    origen = 'manual'
    tipo = request.GET.get('tipo')
    if tipo in dict(TIPOS):
        inicial['tipo'] = tipo
    administracion = None
    if request.GET.get('administracion', '').isdigit():
        from medicamentos.models import Administracion
        administracion = Administracion.objects.filter(pk=request.GET['administracion'], residente=residente).first()
        if administracion:
            inicial.update(tipo='medicacion', prescripcion=administracion.prescripcion_id,
                           fecha_hora=timezone.localtime(administracion.fecha_administracion).replace(second=0, microsecond=0),
                           descripcion=f'Suministro corregido: {administracion.prescripcion.medicamento}. '
                                       f'Motivo de la anulación: {administracion.motivo_anulacion}')
            origen = 'medicamento'
    herida = None
    if request.GET.get('herida', '').isdigit():
        from cuidados.models import Herida
        herida = Herida.objects.filter(pk=request.GET['herida'], residente=residente).first()
        if herida:
            inicial.update(tipo='lpp', herida=herida.pk, lugar='habitacion',
                           descripcion=f'{herida.nombre}, {herida.get_estadio_inicial_display().lower()}, '
                                       f'detectada el {herida.fecha_deteccion:%d/%m/%Y}. {herida.descripcion}'.strip())
            origen = 'herida'
    form = EventoForm(request.POST or None, residente=residente, config=config, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        evento = form.save(commit=False)
        evento.residente = residente
        evento.origen = request.POST.get('origen') if request.POST.get('origen') in ('herida', 'medicamento') else 'manual'
        if administracion:
            evento.administracion = administracion
        anonimo = form.cleaned_data.get('anonimo', False)
        services.registrar(evento, request.user, anonimo=anonimo)
        _auditar(request, RegistroAuditoria.EVENTO_REPORTADO,
                 f'{evento.get_tipo_display()} del residente #{residente.pk} ({evento.get_gravedad_display().split(" (")[0].lower()})'
                 + (' — reporte anónimo' if evento.anonimo else ''), anonimo=evento.anonimo)
        messages.success(request, 'Evento reportado. Gracias: reportar ayuda a que no se repita.')
        if evento.vigilancias.exists():
            messages.info(request, 'Quedó programada la vigilancia después de la caída; aparecerá en Inicio y en la Agenda.')
        if puede_supervisar(request.user) or not evento.anonimo:
            return redirect('eventos_detalle', pk=evento.pk)
        return redirect('residente_detalle', pk=residente.pk)
    return render(request, 'eventos/reportar.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(), 'config': config, 'origen': origen,
    })


# ── Detalle, notas, cierre y vigilancia ─────────────────────────────

@login_required
@reportar_requerido
def detalle(request, pk):
    evento = get_object_or_404(EventoAdverso.objects.select_related('residente', 'prescripcion__medicamento', 'herida',
                                                                    'cerrado_por', 'reportado_por'),
                               pk=pk, hogar=request.user.hogar)
    if not _puede_ver_evento(request.user, evento) and evento.reportado_por_id != request.user.pk:
        return HttpResponseForbidden('No puede ver este evento.')
    config = ConfiguracionEventos.para_hogar(evento.hogar)
    return render(request, 'eventos/detalle.html', {
        'evento': evento, 'residente': evento.residente, 'nombre': evento.residente.get_nombre(),
        'notas': evento.notas.select_related('autor'), 'vigilancias': evento.vigilancias.select_related('realizada_por'),
        've_quien': ve_quien_reporto(request.user, evento, config),
        'puede_analizar': puede_analizar(request.user) and evento.abierto,
        'puede_nota': puede_supervisar(request.user) or evento.reportado_por_id == request.user.pk,
        'puede_vigilancia': puede_vigilancia(request.user),
        'form_cierre': CierreForm(), 'form_nota': NotaForm(), 'form_vigilancia': VigilanciaForm(),
    })


@login_required
@require_POST
@reportar_requerido
def nota(request, pk):
    evento = get_object_or_404(EventoAdverso, pk=pk, hogar=request.user.hogar)
    if not (puede_supervisar(request.user) or evento.reportado_por_id == request.user.pk):
        return HttpResponseForbidden('No puede agregar notas a este evento.')
    form = NotaForm(request.POST)
    if form.is_valid():
        NotaEvento.objects.create(evento=evento, texto=form.cleaned_data['texto'], autor=request.user)
        _auditar(request, RegistroAuditoria.EVENTO_NOTA, f'Nota en el evento #{evento.pk}')
        messages.success(request, 'Nota agregada.')
    return redirect('eventos_detalle', pk=evento.pk)


@login_required
@require_POST
@analizar_requerido
def cerrar(request, pk):
    evento = get_object_or_404(EventoAdverso, pk=pk, hogar=request.user.hogar)
    form = CierreForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        try:
            services.cerrar(evento, request.user, d['causas'], d['acciones'], d['responsable'], d['fecha_limite'])
        except ValueError as e:
            messages.error(request, str(e))
        else:
            _auditar(request, RegistroAuditoria.EVENTO_CERRADO, f'Evento #{evento.pk} analizado y cerrado')
            messages.success(request, 'Evento analizado y cerrado.')
    else:
        messages.error(request, 'Escriba las causas y las acciones de mejora.')
    return redirect('eventos_detalle', pk=evento.pk)


@login_required
@require_POST
@vigilancia_requerido
def vigilancia(request, pk):
    v = get_object_or_404(VigilanciaEvento.objects.select_related('evento'), pk=pk, evento__hogar=request.user.hogar)
    form = VigilanciaForm(request.POST, instance=v)
    if form.is_valid():
        d = form.cleaned_data
        try:
            services.registrar_vigilancia(v, request.user, d['conciencia'], d['dolor'], d['hallazgos'], d['requiere_medico'])
        except ValueError as e:
            messages.error(request, str(e))
        else:
            _auditar(request, RegistroAuditoria.VIGILANCIA_REGISTRADA,
                     f'Vigilancia #{v.pk} del evento #{v.evento_id} (residente #{v.evento.residente_id})')
            if v.preocupante:
                messages.warning(request, 'Revisión registrada con hallazgos de alarma: avise al médico de inmediato.')
            else:
                messages.success(request, 'Revisión registrada.')
    else:
        messages.error(request, 'Indique el estado de conciencia.')
    volver = request.POST.get('volver', '')
    if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
        volver = reverse('eventos_detalle', args=[v.evento_id])
    return redirect(volver)


# ── Indicadores y configuración ─────────────────────────────────────

@login_required
@supervision_requerido
def indicadores(request):
    filas = services.indicadores(request.user.hogar, meses=12)
    tipos = [(t, n) for t, n in TIPOS if any(f['por_tipo'][t] for f in filas)]
    actual = filas[-1]
    return render(request, 'eventos/indicadores.html', {
        'filas': filas, 'actual': actual, 'tipos': tipos,
        'grafica': json.dumps({
            'labels': [f['mes'].strftime('%m/%Y') for f in filas],
            'series': [{'label': n, 'data': [f['por_tipo'][t] for f in filas]} for t, n in tipos],
            'tasa': [f['tasa_caidas'] for f in filas],
        }),
    })


@login_required
@configurar_requerido
def configuracion(request):
    config = ConfiguracionEventos.para_hogar(request.user.hogar)
    form = ConfiguracionForm(request.POST or None, instance=config)
    if request.method == 'POST' and form.is_valid():
        c = form.save(commit=False)
        c.actualizado_por = request.user
        c.save()
        _auditar(request, RegistroAuditoria.CONFIGURACION_EVENTOS,
                 f'Modo de reporte: {c.get_modo_reporte_display().split(":")[0]}; vigilancia {c.horas_vigilancia_caida} h '
                 f'cada {c.intervalo_vigilancia_horas} h')
        messages.success(request, 'Configuración de eventos adversos guardada.')
        return redirect('eventos_bandeja')
    return render(request, 'eventos/configuracion.html', {'form': form})
