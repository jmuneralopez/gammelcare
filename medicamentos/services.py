"""Lógica del módulo de medicamentos que no pertenece a una vista
concreta: elección FEFO del lote, armado en memoria de la hoja del día y
el registro de administración/no-administración con su movimiento de
inventario. Ver plan-modulo-medicamentos.md, secciones 2.3 a 2.5.
"""
from datetime import datetime, timedelta

from django.db import transaction, IntegrityError
from django.utils import timezone

from .models import (
    IngresoMedicamento, Administracion, MovimientoInventario, Prescripcion,
    HorarioPrescripcion,
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
# ── Ronda por franja horaria (3.1) ───────────────────────────────
# Vista de todo el hogar agrupada por franja horaria, en vez de residente
# por residente. Reusa la misma lógica de la hoja del día (FEFO, botiquín,
# no-administración) — lo único distinto es que agrupa por franja y cruza
# todos los residentes del hogar en vez de uno solo.

def franjas_del_dia(hogar, fecha):
    """Horas distintas en que hay al menos una toma de horario fijo vigente
    ese día en todo el hogar — son las pestañas de la ronda (3.1). No sale
    de `ConfiguracionMedicamentos.horas_estandar` (esas son solo sugerencias
    al crear un tratamiento) sino de los horarios reales ya formulados."""
    horarios = (
        HorarioPrescripcion.objects
        .filter(
            prescripcion__residente__hogar=hogar,
            prescripcion__estado=Prescripcion.ACTIVA,
            prescripcion__tipo_pauta=Prescripcion.HORARIOS_FIJOS,
        )
        .select_related('prescripcion')
    )
    return sorted({h.hora for h in horarios if h.prescripcion.vigente_en(fecha)})


def franja_mas_cercana(franjas, ahora_hora):
    """La franja cuya hora programada está más cerca de la hora actual —
    para posicionar la ronda sola al abrirla (ver 3.1: 'al abrir a las
    07:10 se posiciona sola en la ronda de las 07:00'). No aplica la
    ventana aquí: eso lo decide la vista con `ConfiguracionMedicamentos`,
    esta función solo encuentra la más próxima."""
    if not franjas:
        return None

    def distancia_en_minutos(hora):
        minutos_hora = hora.hour * 60 + hora.minute
        minutos_ahora = ahora_hora.hour * 60 + ahora_hora.minute
        return abs(minutos_hora - minutos_ahora)

    return min(franjas, key=distancia_en_minutos)


def ronda_por_franja(hogar, fecha, hora):
    """Arma en memoria los bloques de la ronda para una franja horaria:
    un bloque por residente (en el mismo orden pasillo/habitación/cama que
    ya usa `atencion_lista`), con las tomas de esa hora exacta. Un
    residente sin tomas en esta franja no aparece — igual que la hoja del
    día, nunca se pre-generan casilleros vacíos (ver plan 2.5)."""
    from residentes.models import Residente

    tz = timezone.get_current_timezone()
    fecha_programada = timezone.make_aware(datetime.combine(fecha, hora), tz)

    residentes = (
        Residente.objects
        .filter(hogar=hogar, activo=True, cama_actual__isnull=False)
        .select_related('cama_actual__habitacion__departamento')
        .order_by(
            'cama_actual__habitacion__departamento__nombre',
            'cama_actual__habitacion__numero',
            'cama_actual__codigo',
        )
    )

    bloques = []
    for residente in residentes:
        horarios = (
            HorarioPrescripcion.objects
            .filter(
                hora=hora,
                prescripcion__residente=residente,
                prescripcion__estado=Prescripcion.ACTIVA,
                prescripcion__tipo_pauta=Prescripcion.HORARIOS_FIJOS,
            )
            .select_related('prescripcion__medicamento')
        )
        filas = []
        for horario in horarios:
            prescripcion = horario.prescripcion
            if not prescripcion.vigente_en(fecha):
                continue
            administracion = (
                Administracion.objects
                .filter(prescripcion=prescripcion, fecha_programada=fecha_programada, anulada=False)
                .select_related('administrada_por')
                .first()
            )
            lote_disponible = elegir_lote_fefo(residente, prescripcion.medicamento)
            filas.append({
                'prescripcion': prescripcion,
                'horario': horario,
                'administracion': administracion,
                'pendiente': administracion is None,
                'sin_existencias': administracion is None and lote_disponible is None,
            })
        if filas:
            bloques.append({'residente': residente, 'filas': filas})

    return bloques


def procesar_marcas_ronda(marcas, usuario):
    """Aplica de una vez la lista de marcas que llegó del guardado único de
    la ronda (3.1: 'un solo POST con todo lo marcado'). Cada marca se
    procesa por separado — un error en una fila (sin existencias, doble
    registro por un reintento) nunca debe tumbar las demás filas ya
    marcadas correctamente. Devuelve (exitosas, fallidas); cada elemento de
    `fallidas` es (marca, mensaje) para que la vista informe exactamente
    qué residente/medicamento quedó pendiente de resolver a mano."""
    exitosas = []
    fallidas = []
    for marca in marcas:
        prescripcion = marca['prescripcion']
        try:
            if marca['accion'] == 'no_administrar':
                administracion = registrar_no_administracion(
                    prescripcion=prescripcion,
                    fecha_programada=marca['fecha_programada'],
                    horario=marca['horario'],
                    motivo=marca['motivo'],
                    observacion=marca.get('observacion', ''),
                    usuario=usuario,
                )
            else:
                usar_botiquin = marca['accion'] == 'usar_botiquin'
                administracion = registrar_administracion(
                    prescripcion=prescripcion,
                    fecha_programada=marca['fecha_programada'],
                    horario=marca['horario'],
                    cantidad=marca.get('cantidad') or prescripcion.dosis_cantidad,
                    observacion=marca.get('observacion', ''),
                    usuario=usuario,
                    usar_botiquin=usar_botiquin,
                    motivo_uso_botiquin=marca.get('motivo_uso_botiquin', ''),
                    hogar=prescripcion.residente.hogar,
                )
            exitosas.append((marca, administracion))
        except SinExistenciasError:
            fallidas.append((marca, 'Sin existencias (ni del residente ni del botiquín).'))
        except IntegrityError:
            fallidas.append((marca, 'Ya había un registro para esta toma (¿doble guardado?).'))
        except ValueError as exc:
            fallidas.append((marca, str(exc)))
    return exitosas, fallidas


@transaction.atomic
def descartar_lote(lote, usuario, motivo):
    """Saca de circulación todo el saldo de un lote (vencido o dañado),
    con su movimiento en el libro de inventario. El lote no se borra."""
    lote = IngresoMedicamento.objects.select_for_update().get(pk=lote.pk)
    if lote.estado in (IngresoMedicamento.DESCARTADO, IngresoMedicamento.DEVUELTO):
        raise ValueError('Este lote ya fue descartado o devuelto.')
    if not motivo.strip():
        raise ValueError('El descarte necesita un motivo.')
    saldo = lote.cantidad_disponible
    lote.cantidad_disponible = 0
    lote.estado = IngresoMedicamento.DESCARTADO
    lote.save(update_fields=['cantidad_disponible', 'estado'])
    MovimientoInventario.objects.create(
        ingreso=lote,
        tipo=MovimientoInventario.DESCARTE_VENCIDO,
        cantidad=-saldo,
        motivo=motivo.strip(),
        usuario=usuario,
    )
    return lote


def marcar_prestamo_repuesto(administracion, usuario):
    administracion.repuesto = True
    administracion.fecha_reposicion = timezone.localdate()
    administracion.repuesto_marcado_por = usuario
    administracion.save(update_fields=['repuesto', 'fecha_reposicion', 'repuesto_marcado_por'])
    return administracion


@transaction.atomic
def devolver_lote(lote, usuario, entregado_a, motivo=''):
    """Devuelve a la familia todo el saldo de un lote del cajón de un
    residente (egreso, orden suspendida, cambio de presentación). Queda el
    movimiento en el libro y el lote en estado DEVUELTO; no se borra."""
    lote = IngresoMedicamento.objects.select_for_update().get(pk=lote.pk)
    if lote.residente_id is None:
        raise ValueError('Los lotes del botiquín no se devuelven a una familia.')
    if lote.estado in (IngresoMedicamento.DESCARTADO, IngresoMedicamento.DEVUELTO) or lote.cantidad_disponible <= 0:
        raise ValueError(f'El lote {lote.lote} no tiene saldo para devolver.')
    if not entregado_a.strip():
        raise ValueError('Escriba a quién se le entrega.')
    saldo = lote.cantidad_disponible
    lote.cantidad_disponible = 0
    lote.estado = IngresoMedicamento.DEVUELTO
    lote.save(update_fields=['cantidad_disponible', 'estado'])
    MovimientoInventario.objects.create(
        ingreso=lote, tipo=MovimientoInventario.DEVOLUCION_FAMILIA, cantidad=-saldo,
        motivo=f'Entregado a: {entregado_a.strip()}' + (f'. {motivo.strip()}' if motivo.strip() else ''),
        usuario=usuario,
    )
    return lote, saldo


def tomas_de_hoy(residente):
    """Resumen de 'Medicamentos de hoy' para tarjetas e indicadores:
    pendientes, atrasadas (la hora ya pasó), suministradas y no suministradas."""
    filas, _prn = hoja_del_dia(residente)
    ahora = timezone.now()
    resumen = {'pendientes': 0, 'atrasadas': 0, 'suministradas': 0, 'no_suministradas': 0, 'total': len(filas)}
    for f in filas:
        if f['pendiente']:
            resumen['pendientes'] += 1
            if f['fecha_programada'] < ahora:
                resumen['atrasadas'] += 1
        elif f['administracion'].estado == Administracion.ADMINISTRADO:
            resumen['suministradas'] += 1
        else:
            resumen['no_suministradas'] += 1
    return resumen


def suministros_recientes(residente, horas=12):
    """Suministros y no suministros registrados en las últimas horas (para la
    nota de enfermería del turno), sin anulados."""
    desde = timezone.now() - timedelta(hours=horas)
    return (Administracion.objects
            .filter(residente=residente, anulada=False, fecha_administracion__gte=desde)
            .select_related('prescripcion__medicamento', 'administrada_por')
            .order_by('fecha_administracion'))
