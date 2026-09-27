from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from residentes.models import Residente
from usuarios.decorators import (
    clinico_requerido, registro_tratamiento_requerido,
    ingreso_medicamento_requerido, administracion_requerido,
    ajuste_inventario_requerido, rol_requerido,
)
from usuarios.models import Rol

from . import services
from .forms import (
    MedicamentoRapidoForm, PrescripcionForm, SuspensionForm,
    IngresoEncabezadoForm, IngresoFormSet,
    AdministrarForm, NoAdministrarForm, UsoBotiquinForm, AnulacionForm,
    DURACION_DIAS, DURACION_FECHA,
)
from .models import (
    Medicamento, Prescripcion, HorarioPrescripcion, IngresoMedicamento,
    Administracion, ConfiguracionMedicamentos,
)


def registrar_auditoria(usuario, accion, descripcion, request):
    from usuarios.views import get_client_ip
    RegistroAuditoria.objects.create(
        usuario=usuario,
        accion=accion,
        descripcion=descripcion,
        ip_address=get_client_ip(request)
    )


# Puede dar de alta un medicamento nuevo en el catálogo quien registra
# tratamientos o quien registra ingresos — es un acto clerical, no clínico.
puede_crear_medicamento = rol_requerido(
    Rol.ADMINISTRADOR, Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO
)


# ── Catálogo ─────────────────────────────────────────────────────

@login_required
def buscar_medicamento(request):
    term = request.GET.get('term', '').strip()
    if len(term) < 2:
        return JsonResponse({'results': []})

    hogar = request.user.hogar
    visibles = Q(hogar__isnull=True)
    if hogar:
        visibles |= Q(hogar=hogar)

    resultados = (
        Medicamento.objects
        .filter(visibles, activo=True)
        .filter(
            Q(nombre_generico__icontains=term) |
            Q(nombre_comercial__icontains=term) |
            Q(concentracion__icontains=term)
        )
        .order_by('nombre_generico')[:20]
    )
    return JsonResponse({'results': [
        {'id': m.pk, 'text': str(m)} for m in resultados
    ]})


@login_required
@puede_crear_medicamento
def medicamento_crear_rapido(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    form = MedicamentoRapidoForm(request.POST)
    if form.is_valid():
        medicamento = form.save(commit=False)
        medicamento.hogar = request.user.hogar
        medicamento.save()
        return JsonResponse({'id': medicamento.pk, 'text': str(medicamento)})
    return JsonResponse({'errors': form.errors}, status=400)


# ── Tratamientos formulados (Prescripcion) ───────────────────────

@login_required
@clinico_requerido
def tratamiento_lista(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    prescripciones = residente.prescripciones.select_related('medicamento').order_by('-fecha_registro')
    return render(request, 'medicamentos/tratamiento_lista.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'prescripciones': prescripciones,
    })


@login_required
@registro_tratamiento_requerido
def tratamiento_crear(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    form = PrescripcionForm(request.POST or None, request.FILES or None, residente=residente)

    if request.method == 'POST' and form.is_valid():
        prescripcion = form.save(commit=False)
        prescripcion.residente = residente
        prescripcion.registrada_por = request.user
        prescripcion.dias_semana = form.dias_semana_str() or 'LMXJVSD'

        duracion_tipo = form.cleaned_data['duracion_tipo']
        if duracion_tipo == DURACION_DIAS:
            dias = form.cleaned_data['duracion_dias']
            prescripcion.fecha_fin = prescripcion.fecha_inicio + timedelta(days=dias)
        elif duracion_tipo == DURACION_FECHA:
            prescripcion.fecha_fin = form.cleaned_data['duracion_fecha']
        else:
            prescripcion.fecha_fin = None

        prescripcion.save()

        if prescripcion.tipo_pauta == Prescripcion.HORARIOS_FIJOS:
            for hora_str in form.horas_lista():
                try:
                    hora = datetime.strptime(hora_str, '%H:%M').time()
                except ValueError:
                    continue
                HorarioPrescripcion.objects.get_or_create(prescripcion=prescripcion, hora=hora)

        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.PRESCRIPCION_CREADA,
            descripcion=f'Tratamiento formulado #{prescripcion.pk} ({prescripcion.medicamento}) '
                        f'registrado para residente #{residente.pk}',
            request=request
        )
        messages.success(request, 'Tratamiento registrado correctamente.')
        return redirect('tratamiento_detalle', pk=prescripcion.pk)

    return render(request, 'medicamentos/tratamiento_form.html', {
        'form': form,
        'residente': residente,
        'nombre': residente.get_nombre(),
    })


@login_required
@clinico_requerido
def tratamiento_detalle(request, pk):
    prescripcion = get_object_or_404(
        Prescripcion, pk=pk, residente__hogar=request.user.hogar
    )
    return render(request, 'medicamentos/tratamiento_detalle.html', {
        'prescripcion': prescripcion,
        'residente': prescripcion.residente,
        'nombre': prescripcion.residente.get_nombre(),
        'horarios': prescripcion.horarios.all(),
        'puede_suspender': (
            prescripcion.estado == Prescripcion.ACTIVA and
            request.user.tiene_rol(*Rol.ROLES_REGISTRO_TRATAMIENTO)
        ),
    })


@login_required
@registro_tratamiento_requerido
def tratamiento_suspender(request, pk):
    prescripcion = get_object_or_404(
        Prescripcion, pk=pk, residente__hogar=request.user.hogar
    )
    if prescripcion.estado != Prescripcion.ACTIVA:
        messages.error(request, 'Este tratamiento ya no está activo.')
        return redirect('tratamiento_detalle', pk=prescripcion.pk)

    form = SuspensionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        prescripcion.estado = Prescripcion.SUSPENDIDA
        prescripcion.motivo_suspension = form.cleaned_data['motivo_suspension']
        prescripcion.fecha_suspension = timezone.now()
        prescripcion.suspendida_por = request.user
        prescripcion.save()

        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.PRESCRIPCION_SUSPENDIDA,
            descripcion=f'Tratamiento #{prescripcion.pk} ({prescripcion.medicamento}) suspendido',
            request=request
        )
        messages.success(request, 'Tratamiento suspendido correctamente.')
        return redirect('tratamiento_detalle', pk=prescripcion.pk)

    return render(request, 'medicamentos/tratamiento_suspender.html', {
        'form': form,
        'prescripcion': prescripcion,
        'residente': prescripcion.residente,
        'nombre': prescripcion.residente.get_nombre(),
    })


# ── Ingreso de medicamentos ───────────────────────────────────────

def _guardar_filas_ingreso(formset, *, residente, hogar, encabezado, usuario):
    creados, sumados = 0, 0
    for fila in formset.cleaned_data:
        if not fila or not fila.get('medicamento'):
            continue
        medicamento = fila['medicamento']
        lote = fila['lote']

        existente = IngresoMedicamento.objects.filter(
            residente=residente, hogar=hogar if residente is None else None,
            medicamento=medicamento, lote=lote
        ).first()

        if existente:
            existente.cantidad_ingresada += fila['cantidad_ingresada']
            existente.cantidad_disponible += fila['cantidad_ingresada']
            if existente.estado == IngresoMedicamento.AGOTADO:
                existente.estado = IngresoMedicamento.DISPONIBLE
            existente.save(update_fields=['cantidad_ingresada', 'cantidad_disponible', 'estado'])
            sumados += 1
        else:
            IngresoMedicamento.objects.create(
                residente=residente,
                hogar=hogar if residente is None else None,
                medicamento=medicamento,
                lote=lote,
                fecha_vencimiento=fila['fecha_vencimiento'],
                cantidad_ingresada=fila['cantidad_ingresada'],
                cantidad_disponible=fila['cantidad_ingresada'],
                unidad=fila['unidad'] or 'tabletas',
                fecha_ingreso=encabezado['fecha_ingreso'],
                entregado_por=encabezado.get('entregado_por', ''),
                recibido_por=usuario,
                observaciones=encabezado.get('observaciones', ''),
            )
            creados += 1
    return creados, sumados


@login_required
@ingreso_medicamento_requerido
def ingreso_crear(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)

    initial = None
    if request.GET.get('precargar') == '1' and request.method != 'POST':
        activas = residente.prescripciones.filter(estado=Prescripcion.ACTIVA).select_related('medicamento')
        initial = [{'medicamento': p.medicamento_id} for p in activas]

    encabezado_form = IngresoEncabezadoForm(
        request.POST or None,
        initial={'fecha_ingreso': timezone.localdate()} if request.method != 'POST' else None
    )
    if initial:
        formset = IngresoFormSet(request.POST or None, initial=initial, prefix='filas')
    else:
        formset = IngresoFormSet(request.POST or None, prefix='filas')

    if request.method == 'POST' and encabezado_form.is_valid() and formset.is_valid():
        creados, sumados = _guardar_filas_ingreso(
            formset, residente=residente, hogar=None,
            encabezado=encabezado_form.cleaned_data, usuario=request.user
        )
        if creados or sumados:
            registrar_auditoria(
                usuario=request.user,
                accion=RegistroAuditoria.INGRESO_MEDICAMENTO,
                descripcion=f'Ingreso de medicamentos para residente #{residente.pk}: '
                            f'{creados} lote(s) nuevo(s), {sumados} sumado(s) a saldo existente',
                request=request
            )
            messages.success(request, f'Ingreso registrado: {creados + sumados} medicamento(s).')
            return redirect('ingreso_lista', pk=residente.pk)
        messages.error(request, 'Agregue al menos un medicamento con lote, cantidad y vencimiento.')

    return render(request, 'medicamentos/ingreso_form.html', {
        'encabezado_form': encabezado_form,
        'formset': formset,
        'residente': residente,
        'nombre': residente.get_nombre(),
        'es_botiquin': False,
    })


@login_required
@ingreso_medicamento_requerido
def ingreso_botiquin_crear(request):
    hogar = request.user.hogar
    encabezado_form = IngresoEncabezadoForm(
        request.POST or None,
        initial={'fecha_ingreso': timezone.localdate()} if request.method != 'POST' else None
    )
    formset = IngresoFormSet(request.POST or None, prefix='filas')

    if request.method == 'POST' and encabezado_form.is_valid() and formset.is_valid():
        creados, sumados = _guardar_filas_ingreso(
            formset, residente=None, hogar=hogar,
            encabezado=encabezado_form.cleaned_data, usuario=request.user
        )
        if creados or sumados:
            registrar_auditoria(
                usuario=request.user,
                accion=RegistroAuditoria.INGRESO_MEDICAMENTO,
                descripcion=f'Ingreso al botiquín del hogar: {creados} lote(s) nuevo(s), '
                            f'{sumados} sumado(s) a saldo existente',
                request=request
            )
            messages.success(request, f'Ingreso al botiquín registrado: {creados + sumados} medicamento(s).')
            return redirect('botiquin_lista')
        messages.error(request, 'Agregue al menos un medicamento con lote, cantidad y vencimiento.')

    return render(request, 'medicamentos/ingreso_form.html', {
        'encabezado_form': encabezado_form,
        'formset': formset,
        'residente': None,
        'nombre': None,
        'es_botiquin': True,
    })


@login_required
@clinico_requerido
def ingreso_lista(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)
    ingresos = residente.ingresos_medicamento.select_related('medicamento').order_by('fecha_vencimiento')
    return render(request, 'medicamentos/ingreso_lista.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'ingresos': ingresos,
        'es_botiquin': False,
    })


@login_required
@ajuste_inventario_requerido
def botiquin_lista(request):
    hogar = request.user.hogar
    ingresos = (
        IngresoMedicamento.objects
        .filter(hogar=hogar, residente__isnull=True)
        .select_related('medicamento')
        .order_by('fecha_vencimiento')
    )
    return render(request, 'medicamentos/ingreso_lista.html', {
        'residente': None,
        'nombre': None,
        'ingresos': ingresos,
        'es_botiquin': True,
    })


# ── Hoja del día y administración ────────────────────────────────

@login_required
@clinico_requerido
def hoja_dia(request, pk):
    residente = get_object_or_404(Residente, pk=pk, hogar=request.user.hogar)

    fecha_str = request.GET.get('fecha')
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else timezone.localdate()
    except ValueError:
        fecha = timezone.localdate()

    filas, prn = services.hoja_del_dia(residente, fecha)
    config = ConfiguracionMedicamentos.para_hogar(residente.hogar)

    for fila in filas:
        administracion = fila.get('administracion')
        fila['puede_anular'] = bool(
            administracion and not administracion.anulada and
            administracion.puede_anularse_por(request.user, config.minutos_anulacion)
        )

    return render(request, 'medicamentos/hoja_dia.html', {
        'residente': residente,
        'nombre': residente.get_nombre(),
        'fecha': fecha,
        'fecha_anterior': fecha - timedelta(days=1),
        'fecha_siguiente': fecha + timedelta(days=1),
        'hoy': timezone.localdate(),
        'filas': filas,
        'prn': prn,
        'config': config,
        'puede_administrar': request.user.tiene_rol(*Rol.ROLES_ADMINISTRACION),
        'motivos_no_administracion': Administracion.MOTIVOS_NO_ADMINISTRACION,
        'motivos_uso_botiquin': Administracion.MOTIVOS_USO_BOTIQUIN,
    })


@login_required
@administracion_requerido
def administracion_registrar(request, prescripcion_pk, horario_pk):
    prescripcion = get_object_or_404(
        Prescripcion, pk=prescripcion_pk, residente__hogar=request.user.hogar
    )
    horario = get_object_or_404(HorarioPrescripcion, pk=horario_pk, prescripcion=prescripcion)
    residente = prescripcion.residente

    fecha_str = request.POST.get('fecha')
    tz = timezone.get_current_timezone()
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        fecha = timezone.localdate()
    fecha_programada = timezone.make_aware(datetime.combine(fecha, horario.hora), tz)

    usar_botiquin = request.POST.get('usar_botiquin') == '1'

    if usar_botiquin:
        form = UsoBotiquinForm(request.POST)
        cantidad = prescripcion.dosis_cantidad
        observacion = form.data.get('observacion', '')
    else:
        form = AdministrarForm(request.POST)
        cantidad = None
        observacion = form.data.get('observacion', '')

    if not form.is_valid():
        messages.error(request, 'Revise los datos: ' + '; '.join(
            f'{campo}: {", ".join(errores)}' for campo, errores in form.errors.items()
        ))
        return redirect('hoja_dia', pk=residente.pk)

    if not usar_botiquin:
        cantidad = form.cleaned_data['cantidad_administrada']
        observacion = form.cleaned_data['observacion']

    if cantidad != prescripcion.dosis_cantidad and not observacion:
        messages.error(request, 'La dosis administrada es distinta de la formulada: la observación es obligatoria.')
        return redirect('hoja_dia', pk=residente.pk)

    try:
        administracion = services.registrar_administracion(
            prescripcion=prescripcion,
            fecha_programada=fecha_programada,
            horario=horario,
            cantidad=cantidad,
            observacion=observacion,
            usuario=request.user,
            usar_botiquin=usar_botiquin,
            motivo_uso_botiquin=form.cleaned_data.get('motivo_uso_botiquin', '') if usar_botiquin else '',
            hogar=residente.hogar,
        )
    except services.SinExistenciasError:
        if usar_botiquin:
            messages.error(request, 'No hay existencias ni en el residente ni en el botiquín del hogar.')
        else:
            messages.warning(request, 'El residente no tiene saldo propio de este medicamento. '
                                       'Use la opción "Usar del botiquín del hogar" si corresponde.')
        return redirect('hoja_dia', pk=residente.pk)

    if usar_botiquin:
        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.USO_BOTIQUIN,
            descripcion=f'Uso del botiquín para {prescripcion.medicamento} — residente #{residente.pk} '
                        f'— motivo: {administracion.get_motivo_uso_botiquin_display()}',
            request=request
        )

    messages.success(request, 'Administración registrada.')
    return redirect('hoja_dia', pk=residente.pk)


@login_required
@administracion_requerido
def administracion_no_registrar(request, prescripcion_pk, horario_pk):
    prescripcion = get_object_or_404(
        Prescripcion, pk=prescripcion_pk, residente__hogar=request.user.hogar
    )
    horario = get_object_or_404(HorarioPrescripcion, pk=horario_pk, prescripcion=prescripcion)
    residente = prescripcion.residente

    fecha_str = request.POST.get('fecha')
    tz = timezone.get_current_timezone()
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        fecha = timezone.localdate()
    fecha_programada = timezone.make_aware(datetime.combine(fecha, horario.hora), tz)

    form = NoAdministrarForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Seleccione un motivo válido.')
        return redirect('hoja_dia', pk=residente.pk)

    services.registrar_no_administracion(
        prescripcion=prescripcion,
        fecha_programada=fecha_programada,
        horario=horario,
        motivo=form.cleaned_data['motivo_no_administracion'],
        observacion=form.cleaned_data['observacion'],
        usuario=request.user,
    )

    registrar_auditoria(
        usuario=request.user,
        accion=RegistroAuditoria.NO_ADMINISTRACION,
        descripcion=f'No administración de {prescripcion.medicamento} — residente #{residente.pk} '
                    f'— motivo: {dict(Administracion.MOTIVOS_NO_ADMINISTRACION).get(form.cleaned_data["motivo_no_administracion"])}',
        request=request
    )
    messages.success(request, 'Registrado como no administrado.')
    return redirect('hoja_dia', pk=residente.pk)


@login_required
@administracion_requerido
def administracion_prn_registrar(request, prescripcion_pk):
    prescripcion = get_object_or_404(
        Prescripcion, pk=prescripcion_pk, residente__hogar=request.user.hogar,
        tipo_pauta=Prescripcion.PRN
    )
    residente = prescripcion.residente

    cantidad_raw = request.POST.get('cantidad_administrada')
    observacion = request.POST.get('observacion', '').strip()
    usar_botiquin = request.POST.get('usar_botiquin') == '1'
    motivo_uso_botiquin = request.POST.get('motivo_uso_botiquin', '')

    if not observacion:
        messages.error(request, 'En una toma PRN la observación (por qué se dio esta vez) es obligatoria.')
        return redirect('hoja_dia', pk=residente.pk)
    if usar_botiquin and not motivo_uso_botiquin:
        messages.error(request, 'Indique el motivo de uso del botiquín.')
        return redirect('hoja_dia', pk=residente.pk)

    try:
        cantidad = Decimal(cantidad_raw) if cantidad_raw else prescripcion.dosis_cantidad
    except InvalidOperation:
        messages.error(request, 'La cantidad administrada no es un número válido.')
        return redirect('hoja_dia', pk=residente.pk)

    try:
        administracion = services.registrar_administracion(
            prescripcion=prescripcion,
            fecha_programada=None,
            horario=None,
            cantidad=cantidad,
            observacion=observacion,
            usuario=request.user,
            usar_botiquin=usar_botiquin,
            motivo_uso_botiquin=motivo_uso_botiquin,
            hogar=residente.hogar,
        )
    except services.SinExistenciasError:
        messages.error(request, 'No hay existencias de este medicamento (ni en el residente ni en el botiquín).')
        return redirect('hoja_dia', pk=residente.pk)

    if usar_botiquin:
        registrar_auditoria(
            usuario=request.user,
            accion=RegistroAuditoria.USO_BOTIQUIN,
            descripcion=f'Uso del botiquín (PRN) para {prescripcion.medicamento} — residente #{residente.pk}',
            request=request
        )

    messages.success(request, 'Toma PRN registrada.')
    return redirect('hoja_dia', pk=residente.pk)


@login_required
@administracion_requerido
def administracion_anular(request, pk):
    administracion = get_object_or_404(
        Administracion, pk=pk, residente__hogar=request.user.hogar
    )
    residente = administracion.residente
    config = ConfiguracionMedicamentos.para_hogar(residente.hogar)

    if not administracion.puede_anularse_por(request.user, config.minutos_anulacion):
        messages.error(request, 'Ya no está dentro de la ventana permitida para anular este registro.')
        return redirect('hoja_dia', pk=residente.pk)

    form = AnulacionForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Indique el motivo de la anulación.')
        return redirect('hoja_dia', pk=residente.pk)

    services.anular_administracion(administracion, request.user, form.cleaned_data['motivo_anulacion'])

    registrar_auditoria(
        usuario=request.user,
        accion=RegistroAuditoria.ANULACION_ADMINISTRACION,
        descripcion=f'Anulación de administración #{administracion.pk} '
                    f'({administracion.prescripcion.medicamento}) — residente #{residente.pk}',
        request=request
    )
    messages.success(request, 'Administración anulada. El stock fue devuelto.')
    return redirect('hoja_dia', pk=residente.pk)
