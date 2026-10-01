import json
from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from residentes.models import Residente
from usuarios.decorators import clinico_requerido

from . import services
from .forms import (
    AdendaForm, AnalitoRapidoForm, CancelarForm, CorreccionValorForm, ExamenForm, ResultadoForm,
    RevisionForm, ValorFormSet,
)
from .models import AnalitoCatalogo, ArchivoResultado, Examen, ValorResultado
from .permisos import (
    puede_registrar_examenes, puede_revisar_examenes, registro_examen_requerido,
    revision_examen_requerido,
)


def _auditar(request, accion, descripcion):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=request.user, accion=accion, descripcion=descripcion,
        ip_address=get_client_ip(request),
    )


def _residente(request, pk):
    return get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)


def _examen(request, pk):
    return get_object_or_404(
        Examen.objects.select_related('residente', 'registrado_por', 'resultado_cargado_por'),
        pk=pk, residente__hogar=request.user.hogar,
    )


def _permisos(request):
    return {
        'puede_registrar': puede_registrar_examenes(request.user),
        'puede_revisar': puede_revisar_examenes(request.user),
    }


def _catalogo_json(hogar):
    return json.dumps({
        str(a.pk): {
            'unidad': a.unidad,
            'ref_min': None if a.ref_min is None else float(a.ref_min),
            'ref_max': None if a.ref_max is None else float(a.ref_max),
            'nota': a.nota,
        }
        for a in AnalitoCatalogo.disponibles_para(hogar)
    })


def _valores_validos(formset):
    return [f.cleaned_data for f in formset.forms if f.cleaned_data]


@login_required
@registro_examen_requerido
@require_POST
def analito_crear_rapido(request):
    """Agrega un analito al catálogo del hogar desde el formulario de
    resultados (ventana emergente) y lo devuelve para seleccionarlo."""
    form = AnalitoRapidoForm(request.POST, hogar=request.user.hogar)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    import uuid
    from django.utils.text import slugify
    analito = form.save(commit=False)
    analito.hogar = request.user.hogar
    analito.creado_por = request.user
    analito.codigo = f'{slugify(analito.nombre)[:24]}-{uuid.uuid4().hex[:8]}'
    analito.orden = 10000
    analito.save()
    return JsonResponse({
        'id': analito.pk,
        'text': str(analito),
        'unidad': analito.unidad,
        'ref_min': None if analito.ref_min is None else float(analito.ref_min),
        'ref_max': None if analito.ref_max is None else float(analito.ref_max),
        'nota': '',
    })


# ── Bandeja del hogar ───────────────────────────────────────────────

@login_required
@clinico_requerido
def bandeja(request):
    """Exámenes del hogar que requieren acción: órdenes sin resultado y
    resultados sin revisión médica (lo crítico primero)."""
    base = (
        Examen.objects
        .filter(residente__hogar=request.user.hogar, residente__activo=True)
        .select_related('residente')
    )
    por_revisar = list(base.filter(estado=Examen.RESULTADO).order_by('fecha_resultado'))
    por_revisar.sort(key=lambda e: (not e.tiene_criticos(), not e.tiene_fuera_de_rango()))
    pendientes = list(base.filter(estado=Examen.PENDIENTE).order_by('fecha_orden', 'fecha_registro'))
    recientes = list(base.filter(estado=Examen.REVISADO).order_by('-fecha_resultado')[:20])

    nombres = {}
    for e in por_revisar + pendientes + recientes:
        if e.residente_id not in nombres:
            nombres[e.residente_id] = e.residente.get_nombre()
    for e in por_revisar + pendientes + recientes:
        e.nombre_residente = nombres[e.residente_id]

    return render(request, 'examenes/bandeja.html', {
        'por_revisar': por_revisar,
        'pendientes': pendientes,
        'recientes': recientes,
        **_permisos(request),
    })


# ── Por residente ───────────────────────────────────────────────────

@login_required
@clinico_requerido
def residente_examenes(request, pk):
    residente = _residente(request, pk)
    examenes = residente.examenes.select_related('registrado_por').prefetch_related('valores')
    return render(request, 'examenes/residente_examenes.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'examenes': examenes,
        **_permisos(request),
    })


@login_required
@registro_examen_requerido
def examen_crear(request, pk):
    residente = _residente(request, pk)
    if not residente.activo:
        messages.error(request, 'El residente está dado de alta; no se registran exámenes nuevos.')
        return redirect('examenes_residente', pk=residente.pk)
    form = ExamenForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        examen = form.save(commit=False)
        examen.residente = residente
        examen.registrado_por = request.user
        examen.save()
        _auditar(request, RegistroAuditoria.EXAMEN_REGISTRADO,
                 f'Orden de examen #{examen.pk} ({examen.nombre}) para el residente #{residente.pk}')
        if request.POST.get('con_resultado'):
            messages.success(request, 'Examen registrado. Ahora cargue el resultado.')
            return redirect('examen_resultado', pk=examen.pk)
        messages.success(request, 'Orden de examen registrada. Queda pendiente de resultado.')
        return redirect('examen_detalle', pk=examen.pk)
    return render(request, 'examenes/examen_form.html', {
        'form': form, 'residente': residente, 'nombre': residente.get_nombre(), 'creando': True,
    })


@login_required
@registro_examen_requerido
def examen_editar(request, pk):
    examen = _examen(request, pk)
    if not examen.editable:
        messages.error(request, 'La orden ya tiene resultado o fue cancelada: no se edita.')
        return redirect('examen_detalle', pk=examen.pk)
    form = ExamenForm(request.POST or None, instance=examen)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Orden corregida.')
        return redirect('examen_detalle', pk=examen.pk)
    return render(request, 'examenes/examen_form.html', {
        'form': form, 'residente': examen.residente, 'nombre': examen.residente.get_nombre(),
        'examen': examen, 'creando': False,
    })


@login_required
@clinico_requerido
def examen_detalle(request, pk):
    examen = _examen(request, pk)
    valores = examen.valores.select_related('analito', 'registrado_por', 'reemplaza')
    vigentes = [v for v in valores if not hasattr(v, 'corregido_por')]
    corregidos = [v for v in valores if hasattr(v, 'corregido_por')]
    _auditar(request, RegistroAuditoria.CONSULTA_EXPEDIENTE,
             f'Consulta del examen #{examen.pk} del residente #{examen.residente_id}')
    return render(request, 'examenes/examen_detalle.html', {
        'examen': examen,
        'residente': examen.residente,
        'nombre': examen.residente.get_nombre(),
        'vigentes': vigentes,
        'corregidos': corregidos,
        'archivos': examen.archivos.select_related('subido_por'),
        'revisiones': examen.revisiones.select_related('medico'),
        'cancelar_form': CancelarForm(),
        **_permisos(request),
    })


@login_required
@registro_examen_requerido
def examen_resultado(request, pk):
    examen = _examen(request, pk)
    if examen.estado != Examen.PENDIENTE:
        messages.info(request, 'Este examen ya tiene resultado. Use "Agregar información al resultado".')
        return redirect('examen_detalle', pk=examen.pk)

    form = ResultadoForm(request.POST or None, request.FILES or None, initial={'fecha_toma': timezone.localdate()})
    formset = ValorFormSet(request.POST or None, prefix='valores', form_kwargs={'hogar': request.user.hogar})
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        try:
            services.cargar_resultado(
                examen, request.user,
                fecha_toma=form.cleaned_data['fecha_toma'],
                conclusion=form.cleaned_data['conclusion'],
                archivos=form.cleaned_data['archivos'],
                valores=_valores_validos(formset),
            )
        except ValidationError as e:
            form.add_error(None, e.messages[0])
        else:
            _auditar(request, RegistroAuditoria.RESULTADO_EXAMEN,
                     f'Resultado del examen #{examen.pk} del residente #{examen.residente_id}')
            examen.refresh_from_db()
            if examen.tiene_criticos():
                messages.warning(request, 'Resultado guardado con VALORES CRÍTICOS: avise al médico de inmediato.')
            else:
                messages.success(request, 'Resultado guardado. Queda pendiente de revisión médica.')
            return redirect('examen_detalle', pk=examen.pk)

    return render(request, 'examenes/resultado_form.html', {
        'examen': examen, 'residente': examen.residente, 'nombre': examen.residente.get_nombre(),
        'form': form, 'formset': formset, 'catalogo_json': _catalogo_json(request.user.hogar), 'es_adenda': False,
        'analito_form': AnalitoRapidoForm(),
    })


@login_required
@registro_examen_requerido
def examen_adenda(request, pk):
    examen = _examen(request, pk)
    if examen.estado not in (Examen.RESULTADO, Examen.REVISADO):
        messages.error(request, 'Solo se agrega información a exámenes que ya tienen resultado.')
        return redirect('examen_detalle', pk=examen.pk)

    form = AdendaForm(request.POST or None, request.FILES or None)
    formset = ValorFormSet(request.POST or None, prefix='valores', form_kwargs={'hogar': request.user.hogar})
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        estaba_revisado = examen.estado == Examen.REVISADO
        try:
            services.agregar_adenda(
                examen, request.user, motivo=form.cleaned_data['motivo'],
                archivos=form.cleaned_data['archivos'], valores=_valores_validos(formset),
            )
        except ValidationError as e:
            form.add_error(None, e.messages[0])
        else:
            _auditar(request, RegistroAuditoria.ADENDA_EXAMEN,
                     f'Información adicional en el examen #{examen.pk}: {form.cleaned_data["motivo"][:150]}')
            msg = 'Información adicional guardada.'
            if estaba_revisado:
                msg += ' El examen vuelve a quedar pendiente de revisión médica.'
            messages.success(request, msg)
            return redirect('examen_detalle', pk=examen.pk)

    return render(request, 'examenes/resultado_form.html', {
        'examen': examen, 'residente': examen.residente, 'nombre': examen.residente.get_nombre(),
        'form': form, 'formset': formset, 'catalogo_json': _catalogo_json(request.user.hogar), 'es_adenda': True,
        'analito_form': AnalitoRapidoForm(),
    })


@login_required
@registro_examen_requerido
def valor_corregir(request, pk):
    valor = get_object_or_404(
        ValorResultado.objects.select_related('examen__residente'),
        pk=pk, examen__residente__hogar=request.user.hogar,
    )
    examen = valor.examen
    if hasattr(valor, 'corregido_por'):
        messages.error(request, 'Ese valor ya fue corregido; corrija la versión vigente.')
        return redirect('examen_detalle', pk=examen.pk)

    form = CorreccionValorForm(request.POST or None, initial={
        'valor': valor.valor, 'unidad': valor.unidad, 'ref_min': valor.ref_min, 'ref_max': valor.ref_max,
    })
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            services.corregir_valor(valor, request.user, d['valor'], d['unidad'], d['ref_min'], d['ref_max'], d['motivo'])
        except ValidationError as e:
            form.add_error(None, e.messages[0])
        else:
            _auditar(request, RegistroAuditoria.CORRECCION_RESULTADO,
                     f'Corrección de {valor.nombre} en el examen #{examen.pk}: '
                     f'{valor.valor_formateado} → {d["valor"]} ({d["motivo"][:120]})')
            messages.success(request, 'Valor corregido. El valor anterior queda en el historial.')
            return redirect('examen_detalle', pk=examen.pk)

    return render(request, 'examenes/valor_corregir.html', {
        'valor': valor, 'examen': examen, 'nombre': examen.residente.get_nombre(), 'form': form,
    })


@login_required
@revision_examen_requerido
def examen_revisar(request, pk):
    examen = _examen(request, pk)
    if examen.estado != Examen.RESULTADO:
        messages.info(request, 'Este examen no está pendiente de revisión.')
        return redirect('examen_detalle', pk=examen.pk)
    form = RevisionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            services.revisar(examen, request.user, form.cleaned_data['conducta'], form.cleaned_data['interpretacion'])
        except ValidationError as e:
            form.add_error(None, e.messages[0])
        else:
            _auditar(request, RegistroAuditoria.REVISION_EXAMEN,
                     f'Revisión médica del examen #{examen.pk} del residente #{examen.residente_id}')
            messages.success(request, 'Revisión registrada.')
            return redirect('examen_detalle', pk=examen.pk)
    return render(request, 'examenes/revisar.html', {
        'examen': examen, 'residente': examen.residente, 'nombre': examen.residente.get_nombre(),
        'vigentes': list(examen.valores_vigentes()),
        'archivos': examen.archivos.all(),
        'form': form,
    })


@login_required
@registro_examen_requerido
@require_POST
def examen_cancelar(request, pk):
    examen = _examen(request, pk)
    form = CancelarForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Escriba el motivo de la cancelación.')
        return redirect('examen_detalle', pk=examen.pk)
    try:
        services.cancelar(examen, request.user, form.cleaned_data['motivo'])
    except ValidationError as e:
        messages.error(request, e.messages[0])
    else:
        _auditar(request, RegistroAuditoria.CANCELACION_EXAMEN,
                 f'Cancelación de la orden #{examen.pk}: {form.cleaned_data["motivo"][:150]}')
        messages.success(request, 'Orden cancelada.')
    return redirect('examen_detalle', pk=examen.pk)


@login_required
@clinico_requerido
def archivo_ver(request, pk):
    archivo = get_object_or_404(
        ArchivoResultado.objects.select_related('examen__residente'),
        pk=pk, examen__residente__hogar=request.user.hogar,
    )
    try:
        handle = archivo.archivo.open('rb')
    except FileNotFoundError:
        raise Http404('El archivo no se encuentra en el almacenamiento.')
    _auditar(request, RegistroAuditoria.CONSULTA_RESULTADO,
             f'Consulta del archivo "{archivo.nombre_original}" del examen #{archivo.examen_id} '
             f'(residente #{archivo.examen.residente_id})')
    descargar = request.GET.get('descargar') == '1'
    respuesta = FileResponse(
        handle, content_type=archivo.content_type,
        as_attachment=descargar, filename=archivo.nombre_original,
    )
    respuesta['X-Content-Type-Options'] = 'nosniff'
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta


@login_required
@clinico_requerido
def tendencias(request, pk):
    """Evolución de cada analito del residente a lo largo del tiempo."""
    residente = _residente(request, pk)
    valores = (
        ValorResultado.objects
        .filter(examen__residente=residente, corregido_por__isnull=True)
        .exclude(examen__estado=Examen.CANCELADO)
        .select_related('examen', 'analito')
        .order_by('examen__fecha_toma', 'fecha_registro')
    )
    series = OrderedDict()
    for v in valores:
        clave = v.analito_id and f'a{v.analito_id}' or f'n{v.nombre.lower()}'
        serie = series.setdefault(clave, {
            'nombre': v.nombre, 'unidad': v.unidad, 'puntos': [],
            'ref_min': v.ref_min, 'ref_max': v.ref_max,
        })
        fecha = v.examen.fecha_toma or v.fecha_registro.date()
        serie['puntos'].append({'fecha': fecha, 'valor': v, 'examen_id': v.examen_id})
    graficas = [
        {
            'id': i,
            'nombre': s['nombre'],
            'unidad': s['unidad'],
            'puntos': s['puntos'],
            'datos': json.dumps({
                'labels': [p['fecha'].strftime('%d/%m/%Y') for p in s['puntos']],
                'valores': [float(p['valor'].valor) for p in s['puntos']],
                'ref_min': None if s['ref_min'] is None else float(s['ref_min']),
                'ref_max': None if s['ref_max'] is None else float(s['ref_max']),
            }),
        }
        for i, s in enumerate(series.values())
    ]
    return render(request, 'examenes/tendencias.html', {
        'residente': residente, 'nombre': residente.get_nombre(), 'graficas': graficas,
    })
