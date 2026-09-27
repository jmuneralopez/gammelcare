"""Lógica del módulo de medicamentos que no pertenece a una vista
concreta: elección FEFO del lote, armado en memoria de la hoja del día y
el registro de administración/no-administración con su movimiento de
inventario. Ver plan-modulo-medicamentos.md, secciones 2.3 a 2.5.
"""
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    IngresoMedicamento, Administracion, MovimientoInventario, Prescripcion,
)


class SinExistenciasError(Exception):
    """No hay un lote propio del residente con saldo disponible."""


def elegir_lote_fefo(residente, medicamento):
    """El lote que vence primero, con saldo, que NO esté vencido — un
    lote vencido nunca se elige automáticamente (ver plan 2.3)."""
    hoy = timezone.localdate()
    return (
        IngresoMedicamento.objects
        .filter(residente=residente, medicamento=medicamento,
                cantidad_disponible__gt=0, fecha_vencimiento__gte=hoy)
        .order_by('fecha_vencimiento')
        .first()
    )


def elegir_lote_botiquin_fefo(hogar, medicamento):
    hoy = timezone.localdate()
    return (
        IngresoMedicamento.objects
        .filter(hogar=hogar, residente__isnull=True, medicamento=medicamento,
                cantidad_disponible__gt=0, fecha_vencimiento__gte=hoy)
        .order_by('fecha_vencimiento')
        .first()
    )


def _descontar_lote(lote, cantidad, usuario, administracion):
    lote.cantidad_disponible = lote.cantidad_disponible - cantidad
    if lote.cantidad_disponible <= 0:
        lote.cantidad_disponible = 0
        lote.estado = IngresoMedicamento.AGOTADO
    lote.save(update_fields=['cantidad_disponible', 'estado'])
    MovimientoInventario.objects.create(
        ingreso=lote,
        tipo=MovimientoInventario.SALIDA_ADMINISTRACION,
        cantidad=-cantidad,
        administracion=administracion,
        usuario=usuario,
    )


@transaction.atomic
def registrar_administracion(
    *, prescripcion, fecha_programada, horario, cantidad, observacion,
    usuario, nota_clinica=None,
    usar_botiquin=False, motivo_uso_botiquin='', hogar=None,
):
    """Registra una administración exitosa, descontando el lote FEFO del
    residente. Si no hay saldo propio y `usar_botiquin` no viene marcado,
    levanta SinExistenciasError para que la vista pida confirmación
    explícita — nunca se completa solo desde el botiquín (ver plan 2.3)."""
    residente = prescripcion.residente
    medicamento = prescripcion.medicamento

    lote = elegir_lote_fefo(residente, medicamento)

    if not lote and not usar_botiquin:
        raise SinExistenciasError()

    if not lote and usar_botiquin:
        lote = elegir_lote_botiquin_fefo(hogar or residente.hogar, medicamento)
        if not lote:
            raise SinExistenciasError()

    administracion = Administracion.objects.create(
        prescripcion=prescripcion,
        residente=residente,
        fecha_programada=fecha_programada,
        horario=horario,
        estado=Administracion.ADMINISTRADO,
        cantidad_administrada=cantidad,
        ingreso_usado=lote,
        observacion=observacion,
        motivo_uso_botiquin=motivo_uso_botiquin if (usar_botiquin and lote.es_botiquin()) else '',
        administrada_por=usuario,
        nota_clinica=nota_clinica,
    )
    _descontar_lote(lote, cantidad, usuario, administracion)
    return administracion


def registrar_no_administracion(
    *, prescripcion, fecha_programada, horario, motivo, observacion, usuario,
    nota_clinica=None,
):
    return Administracion.objects.create(
        prescripcion=prescripcion,
        residente=prescripcion.residente,
        fecha_programada=fecha_programada,
        horario=horario,
        estado=Administracion.NO_ADMINISTRADO,
        motivo_no_administracion=motivo,
        observacion=observacion,
        administrada_por=usuario,
        nota_clinica=nota_clinica,
    )


@transaction.atomic
def anular_administracion(administracion, usuario, motivo):
    """Devuelve el stock con un movimiento de AJUSTE y marca la fila como
    anulada — nunca se borra (ver plan 4.6)."""
    if administracion.estado == Administracion.ADMINISTRADO and administracion.ingreso_usado_id:
        lote = administracion.ingreso_usado
        lote.cantidad_disponible = lote.cantidad_disponible + administracion.cantidad_administrada
        if lote.estado == IngresoMedicamento.AGOTADO and lote.cantidad_disponible > 0:
            lote.estado = IngresoMedicamento.DISPONIBLE
        lote.save(update_fields=['cantidad_disponible', 'estado'])
        MovimientoInventario.objects.create(
            ingreso=lote,
            tipo=MovimientoInventario.AJUSTE,
            cantidad=administracion.cantidad_administrada,
            administracion=administracion,
            motivo=f'Reverso por anulación — {motivo}',
            usuario=usuario,
        )
    administracion.anulada = True
    administracion.motivo_anulacion = motivo
    administracion.anulada_por = usuario
    administracion.fecha_anulacion = timezone.now()
    administracion.save(update_fields=['anulada', 'motivo_anulacion', 'anulada_por', 'fecha_anulacion'])


def prescripciones_horarios_activas(residente, fecha):
    return (
        Prescripcion.objects
        .filter(residente=residente, estado=Prescripcion.ACTIVA,
                tipo_pauta=Prescripcion.HORARIOS_FIJOS)
        .select_related('medicamento')
        .prefetch_related('horarios')
    )


def prescripciones_prn_activas(residente):
    return (
        Prescripcion.objects
        .filter(residente=residente, estado=Prescripcion.ACTIVA,
                tipo_pauta=Prescripcion.PRN)
        .select_related('medicamento')
    )


def hoja_del_dia(residente, fecha=None):
    """Arma en memoria las franjas del día para un residente, cruzando
    los horarios de cada prescripción activa con las administraciones ya
    registradas. Nunca se pre-generan filas — lo que no tiene
    Administracion está pendiente (ver plan 2.5, decisión técnica
    central del módulo)."""
    fecha = fecha or timezone.localdate()
    tz = timezone.get_current_timezone()

    filas = []
    for prescripcion in prescripciones_horarios_activas(residente, fecha):
        if not prescripcion.vigente_en(fecha):
            continue
        for horario in prescripcion.horarios.all():
            fecha_programada = timezone.make_aware(
                datetime.combine(fecha, horario.hora), tz
            )
            administracion = (
                Administracion.objects
                .filter(prescripcion=prescripcion, fecha_programada=fecha_programada, anulada=False)
                .select_related('ingreso_usado', 'administrada_por')
                .first()
            )
            lote_disponible = elegir_lote_fefo(residente, prescripcion.medicamento)
            filas.append({
                'prescripcion': prescripcion,
                'horario': horario,
                'fecha_programada': fecha_programada,
                'administracion': administracion,
                'pendiente': administracion is None,
                'sin_existencias': administracion is None and lote_disponible is None,
            })

    filas.sort(key=lambda f: f['fecha_programada'])

    prn = []
    for prescripcion in prescripciones_prn_activas(residente):
        if not prescripcion.vigente_en(fecha):
            continue
        ultima = (
            Administracion.objects
            .filter(prescripcion=prescripcion, estado=Administracion.ADMINISTRADO, anulada=False)
            .order_by('-fecha_administracion')
            .first()
        )
        aviso_intervalo = False
        if ultima and prescripcion.frecuencia_minima_horas:
            limite = ultima.fecha_administracion + timedelta(hours=prescripcion.frecuencia_minima_horas)
            aviso_intervalo = timezone.now() < limite
        lote_disponible = elegir_lote_fefo(residente, prescripcion.medicamento)
        prn.append({
            'prescripcion': prescripcion,
            'ultima_administracion': ultima,
            'aviso_intervalo': aviso_intervalo,
            'sin_existencias': lote_disponible is None,
        })

    return filas, prn
