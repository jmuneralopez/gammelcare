"""Reglas del motor de alertas.

Cada regla es una función `(hogar, config, residente=None) -> [Candidato]`
que mira los datos y devuelve las condiciones que existen AHORA. El motor
compara con las alertas vigentes: crea las nuevas, actualiza las que
cambiaron y marca como resueltas las que ya no aparecen.

Si se pasa `residente`, la regla solo mira a ese residente (para reevaluar
de inmediato después de un registro, sin recorrer todo el hogar).
"""
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from usuarios.models import Rol

CRITICA, ALTA, MEDIA, INFORMATIVA = 'critica', 'alta', 'media', 'informativa'

UMBRALES = {
    'horas_examen_por_revisar': {'defecto': 48, 'etiqueta': 'Horas para avisar que un resultado sigue sin revisión médica'},
    'dias_examen_sin_resultado': {'defecto': 15, 'etiqueta': 'Días para avisar que una orden de examen sigue sin resultado'},
    'dias_lote_por_vencer': {'defecto': 180, 'etiqueta': 'Días antes del vencimiento para avisar que un lote está por vencer'},
    'dias_stock_bajo': {'defecto': 5, 'etiqueta': 'Avisar cuando el cajón alcance para menos de N días'},
    'dias_prestamo_sin_reponer': {'defecto': 3, 'etiqueta': 'Días para avisar que un préstamo del botiquín no se ha repuesto'},
    'dias_orden_por_terminar': {'defecto': 3, 'etiqueta': 'Días antes del fin de una orden médica para avisar'},
    'minutos_gracia_toma': {'defecto': 60, 'etiqueta': 'Minutos de gracia antes de avisar que una toma no se registró'},
    'horas_cita_sin_cierre': {'defecto': 12, 'etiqueta': 'Horas después de una cita para avisar que no se registró qué pasó'},
    'horas_signo_fuera_rango': {'defecto': 24, 'etiqueta': 'Horas que se mantiene el aviso de un signo fuera de rango (no crítico)'},
    'horas_sin_control_signos': {'defecto': 24, 'etiqueta': 'Horas sin tomar signos vitales para avisar'},
    'dias_sin_deposicion': {'defecto': 3, 'etiqueta': 'Días sin deposición para avisar (según notas de enfermería)'},
    'horas_sin_diuresis': {'defecto': 24, 'etiqueta': 'Horas sin diuresis para avisar (según notas de enfermería)'},
    'porcentaje_perdida_peso': {'defecto': 5, 'etiqueta': 'Pérdida de peso (%) en 30 días para avisar'},
    'ml_balance_negativo': {'defecto': 500, 'etiqueta': 'Balance de líquidos negativo (mL en 24 horas) para avisar'},
}


@dataclass
class Candidato:
    clave: str
    gravedad: str
    titulo: str
    roles: list
    mensaje: str = ''
    url: str = ''
    texto_accion: str = ''
    residente: object = None
    extra: dict = field(default_factory=dict)


def _residentes(hogar, residente):
    from residentes.models import Residente
    if residente is not None:
        return [residente] if residente.activo else []
    return list(Residente.objects.filter(hogar=hogar, activo=True))


def _hora(dt):
    return timezone.localtime(dt).strftime('%H:%M')


def _fecha(dt):
    return timezone.localtime(dt).strftime('%d/%m/%Y')


# ── Exámenes ────────────────────────────────────────────────────────

def _examenes(hogar, residente):
    from examenes.models import Examen
    qs = Examen.objects.filter(residente__hogar=hogar, residente__activo=True).select_related('residente')
    if residente is not None:
        qs = qs.filter(residente=residente)
    return qs, Examen


def examen_critico(hogar, config, residente=None):
    qs, Examen = _examenes(hogar, residente)
    for e in qs.filter(estado=Examen.RESULTADO).prefetch_related('valores'):
        if e.tiene_criticos():
            criticos = [v for v in e.valores_vigentes() if v.es_critico()]
            detalle = ', '.join(f'{v.nombre} {v.valor_formateado} {v.unidad}'.strip() for v in criticos[:4])
            yield Candidato(
                clave=f'examen_critico:{e.pk}', gravedad=CRITICA, residente=e.residente,
                titulo=f'Valores críticos en {e.nombre} de {e.residente.get_nombre()}',
                mensaje=(f'{detalle}. ' if detalle else '') + 'Requiere revisión médica inmediata.',
                url=reverse('examen_revisar', args=[e.pk]), texto_accion='Revisar y dar conducta',
                roles=[Rol.MEDICO, Rol.JEFE_ENFERMERIA],
            )


def examen_por_revisar(hogar, config, residente=None):
    qs, Examen = _examenes(hogar, residente)
    limite = timezone.now() - timedelta(hours=config.umbral('horas_examen_por_revisar'))
    for e in qs.filter(estado=Examen.RESULTADO, fecha_resultado__lt=limite).prefetch_related('valores'):
        if e.tiene_criticos():
            continue  # ya la cubre la alerta crítica
        horas = int((timezone.now() - e.fecha_resultado).total_seconds() // 3600)
        yield Candidato(
            clave=f'examen_por_revisar:{e.pk}', gravedad=MEDIA, residente=e.residente,
            titulo=f'{e.nombre} de {e.residente.get_nombre()} lleva {horas} horas sin revisión médica',
            url=reverse('examen_revisar', args=[e.pk]), texto_accion='Revisar y dar conducta',
            roles=[Rol.MEDICO],
        )


def examen_sin_resultado(hogar, config, residente=None):
    qs, Examen = _examenes(hogar, residente)
    dias = config.umbral('dias_examen_sin_resultado')
    for e in qs.filter(estado=Examen.PENDIENTE):
        if e.dias_pendiente() > dias:
            yield Candidato(
                clave=f'examen_sin_resultado:{e.pk}', gravedad=MEDIA, residente=e.residente,
                titulo=f'La orden de {e.nombre} de {e.residente.get_nombre()} lleva {e.dias_pendiente()} días sin resultado',
                mensaje='Verifique si ya se tomó la muestra o si hay que gestionar la cita.',
                url=reverse('examen_detalle', args=[e.pk]), texto_accion='Ver la orden',
                roles=[Rol.JEFE_ENFERMERIA, Rol.ADMINISTRADOR],
            )


# ── Medicamentos: lotes ─────────────────────────────────────────────

def _lotes_con_saldo(hogar, residente):
    from django.db.models import Q
    from medicamentos.models import IngresoMedicamento
    qs = IngresoMedicamento.objects.filter(cantidad_disponible__gt=0).exclude(
        estado__in=[IngresoMedicamento.DESCARTADO, IngresoMedicamento.DEVUELTO],
    ).select_related('residente', 'medicamento')
    if residente is not None:
        return qs.filter(residente=residente)
    return qs.filter(Q(hogar=hogar, residente__isnull=True) | Q(residente__hogar=hogar, residente__activo=True))


def _destino_lote(lote):
    if lote.residente_id:
        return reverse('ingreso_lista', args=[lote.residente_id]), f'el cajón de {lote.residente.get_nombre()}'
    return reverse('botiquin_lista'), 'el botiquín'


def lote_vencido(hogar, config, residente=None):
    hoy = timezone.localdate()
    for lote in _lotes_con_saldo(hogar, residente).filter(fecha_vencimiento__lt=hoy):
        url, donde = _destino_lote(lote)
        yield Candidato(
            clave=f'lote_vencido:{lote.pk}', gravedad=ALTA, residente=lote.residente,
            titulo=f'El lote {lote.lote} de {lote.medicamento} se encuentra vencido. Por favor descártelo completamente.',
            mensaje=f'Está en {donde}; venció el {lote.fecha_vencimiento:%d/%m/%Y} y le quedan {lote.cantidad_disponible.normalize()} {lote.get_unidad_display().lower()}.',
            url=url, texto_accion='Descartar lote',
            roles=[Rol.JEFE_ENFERMERIA, Rol.ADMINISTRADOR],
        )


def lote_por_vencer(hogar, config, residente=None):
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=config.umbral('dias_lote_por_vencer'))
    for lote in _lotes_con_saldo(hogar, residente).filter(fecha_vencimiento__gte=hoy, fecha_vencimiento__lt=limite):
        url, donde = _destino_lote(lote)
        dias = (lote.fecha_vencimiento - hoy).days
        yield Candidato(
            clave=f'lote_por_vencer:{lote.pk}', gravedad=INFORMATIVA, residente=lote.residente,
            titulo=f'El lote {lote.lote} de {lote.medicamento} vence en {dias} días ({lote.fecha_vencimiento:%d/%m/%Y})',
            mensaje=f'Está en {donde}. El sistema lo suministra primero (vence primero, sale primero).',
            url=url, texto_accion='Ver lotes',
            roles=[Rol.JEFE_ENFERMERIA, Rol.ADMINISTRADOR],
        )


# ── Medicamentos: existencias y órdenes ─────────────────────────────

def stock_bajo(hogar, config, residente=None):
    from medicamentos.models import IngresoMedicamento, Prescripcion
    hoy = timezone.localdate()
    umbral = config.umbral('dias_stock_bajo')
    for r in _residentes(hogar, residente):
        consumo = {}
        fin = {}
        for p in (Prescripcion.objects.filter(residente=r, estado=Prescripcion.ACTIVA,
                                              tipo_pauta=Prescripcion.HORARIOS_FIJOS)
                  .select_related('medicamento').prefetch_related('horarios')):
            if p.fecha_fin and p.fecha_fin < hoy:
                continue
            tomas = len(p.horarios.all()) * Decimal(len(p.dias_semana or 'LMXJVSD')) / 7
            if not tomas:
                continue
            consumo.setdefault(p.medicamento, Decimal(0))
            consumo[p.medicamento] += p.dosis_cantidad * tomas
            # Fecha en que termina el tratamiento con ese medicamento; None si alguna orden es indefinida.
            if p.fecha_fin is None or (p.medicamento in fin and fin[p.medicamento] is None):
                fin[p.medicamento] = None
            else:
                fin[p.medicamento] = max(fin.get(p.medicamento, p.fecha_fin), p.fecha_fin)
        for medicamento, por_dia in consumo.items():
            saldo = (IngresoMedicamento.objects
                     .filter(residente=r, medicamento=medicamento, cantidad_disponible__gt=0, fecha_vencimiento__gte=hoy)
                     .exclude(estado__in=[IngresoMedicamento.DESCARTADO, IngresoMedicamento.DEVUELTO])
                     .aggregate(t=Sum('cantidad_disponible'))['t'] or Decimal(0))
            dias = int(saldo / por_dia) if por_dia else 999
            if dias >= umbral:
                continue
            if fin.get(medicamento) and (fin[medicamento] - hoy).days <= dias:
                continue  # alcanza hasta que termina la orden
            if saldo <= 0:
                titulo = f'{r.get_nombre()} no tiene {medicamento} en su cajón'
                gravedad = ALTA
            else:
                titulo = f'El {medicamento} de {r.get_nombre()} alcanza para {dias} día{"s" if dias != 1 else ""}'
                gravedad = MEDIA
            yield Candidato(
                clave=f'stock_bajo:{r.pk}:{medicamento.pk}', gravedad=gravedad, residente=r, titulo=titulo,
                mensaje='Pida a la familia o a la EPS que lo traiga. Mientras tanto se puede usar el botiquín como préstamo.',
                url=reverse('ingreso_lista', args=[r.pk]), texto_accion='Ver el cajón',
                roles=[Rol.JEFE_ENFERMERIA, Rol.ADMINISTRADOR, Rol.TRABAJO_SOCIAL],
            )


def prestamo_sin_reponer(hogar, config, residente=None):
    from medicamentos.models import Administracion
    limite = timezone.now() - timedelta(days=config.umbral('dias_prestamo_sin_reponer'))
    qs = Administracion.objects.filter(
        residente__hogar=hogar, residente__activo=True, motivo_uso_botiquin=Administracion.PRESTAMO,
        repuesto=False, anulada=False, fecha_administracion__lt=limite,
    ).select_related('residente', 'prescripcion__medicamento')
    if residente is not None:
        qs = qs.filter(residente=residente)
    for a in qs:
        dias = (timezone.now() - a.fecha_administracion).days
        yield Candidato(
            clave=f'prestamo:{a.pk}', gravedad=MEDIA, residente=a.residente,
            titulo=f'Préstamo del botiquín sin reponer: {a.prescripcion.medicamento} para {a.residente.get_nombre()} (hace {dias} días)',
            mensaje='Cuando la familia lo reponga, márquelo como repuesto en el botiquín.',
            url=reverse('botiquin_lista') + '#prestamos', texto_accion='Ver préstamos',
            roles=[Rol.JEFE_ENFERMERIA, Rol.ADMINISTRADOR],
        )


def orden_por_terminar(hogar, config, residente=None):
    from medicamentos.models import Prescripcion
    hoy = timezone.localdate()
    qs = Prescripcion.objects.filter(
        residente__hogar=hogar, residente__activo=True, estado=Prescripcion.ACTIVA,
        fecha_fin__gte=hoy, fecha_fin__lte=hoy + timedelta(days=config.umbral('dias_orden_por_terminar')),
    ).select_related('residente', 'medicamento')
    if residente is not None:
        qs = qs.filter(residente=residente)
    for p in qs:
        cuando = 'hoy' if p.fecha_fin == hoy else f'el {p.fecha_fin:%d/%m/%Y}'
        yield Candidato(
            clave=f'orden_por_terminar:{p.pk}:{p.fecha_fin:%Y%m%d}', gravedad=INFORMATIVA, residente=p.residente,
            titulo=f'La orden de {p.medicamento} de {p.residente.get_nombre()} termina {cuando}',
            mensaje='Si debe continuar, el médico debe registrar una nueva orden médica.',
            url=reverse('tratamiento_detalle', args=[p.pk]), texto_accion='Ver la orden médica',
            roles=[Rol.MEDICO, Rol.JEFE_ENFERMERIA],
        )


def toma_no_registrada(hogar, config, residente=None):
    """Una alerta por residente y día con todas las tomas sin registrar,
    para no llenar la bandeja con una alerta por cada toma."""
    from medicamentos import services as med
    limite = timezone.now() - timedelta(minutes=config.umbral('minutos_gracia_toma'))
    hoy = timezone.localdate()
    for r in _residentes(hogar, residente):
        for fecha in (hoy - timedelta(days=1), hoy):
            filas, _ = med.hoja_del_dia(r, fecha)
            pendientes = [f for f in filas if f['pendiente'] and f['fecha_programada'] < limite]
            if not pendientes:
                continue
            cuando = 'hoy' if fecha == hoy else 'ayer'
            n = len(pendientes)
            detalle = '; '.join(f'{_hora(f["fecha_programada"])} {f["prescripcion"].medicamento}' for f in pendientes[:6])
            if n > 6:
                detalle += f' y {n - 6} más'
            sin_existencias = any(f['sin_existencias'] for f in pendientes)
            yield Candidato(
                clave=f'toma:{r.pk}:{fecha:%Y%m%d}', gravedad=ALTA, residente=r,
                titulo=(f'{r.get_nombre()}: {n} toma{"s" if n != 1 else ""} de {cuando} sin registrar'),
                mensaje=(f'{detalle}. Registre si se suministró o por qué no se suministró.'
                         + (' Alguna no tiene existencias en el cajón.' if sin_existencias else '')),
                url=reverse('hoja_dia', args=[r.pk]) + (f'?fecha={fecha:%Y-%m-%d}' if fecha != hoy else ''),
                texto_accion='Ir a Medicamentos de hoy' if fecha == hoy else 'Registrar las de ayer',
                roles=[Rol.ENFERMERO, Rol.JEFE_ENFERMERIA],
            )


def prn_frecuente(hogar, config, residente=None):
    from medicamentos.models import Administracion, Prescripcion
    desde = timezone.now() - timedelta(hours=24)
    qs = Prescripcion.objects.filter(
        residente__hogar=hogar, residente__activo=True, estado=Prescripcion.ACTIVA,
        tipo_pauta=Prescripcion.PRN, dosis_maxima_dia__isnull=False,
    ).select_related('residente', 'medicamento')
    if residente is not None:
        qs = qs.filter(residente=residente)
    for p in qs:
        n = Administracion.objects.filter(prescripcion=p, estado=Administracion.ADMINISTRADO, anulada=False,
                                          fecha_administracion__gte=desde).count()
        if n > p.dosis_maxima_dia:
            yield Candidato(
                clave=f'prn_frecuente:{p.pk}', gravedad=ALTA, residente=p.residente,
                titulo=f'{p.residente.get_nombre()} recibió {n} dosis de {p.medicamento} (si es necesario) en 24 horas',
                mensaje=f'El máximo indicado es {p.dosis_maxima_dia} al día. Informe al médico.',
                url=reverse('tratamiento_detalle', args=[p.pk]), texto_accion='Ver la orden médica',
                roles=[Rol.MEDICO, Rol.JEFE_ENFERMERIA],
            )


# ── Alergias ────────────────────────────────────────────────────────

def sin_alergias_registradas(hogar, config, residente=None):
    from antecedentes.services import estado_alergias
    for r in _residentes(hogar, residente):
        if estado_alergias(r) == 'sin_dato':
            yield Candidato(
                clave=f'sin_alergias:{r.pk}', gravedad=MEDIA, residente=r,
                titulo=f'{r.get_nombre()} no tiene alergias registradas',
                mensaje='Registre sus alergias o declare "sin alergias conocidas": sin ese dato el sistema no puede avisar al formular.',
                url=reverse('residente_antecedentes', args=[r.pk]), texto_accion='Registrar alergias',
                roles=[Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ADMINISTRADOR],
            )


# ── Citas ───────────────────────────────────────────────────────────

ROLES_CITAS = [Rol.JEFE_ENFERMERIA, Rol.ENFERMERO, Rol.ADMINISTRADOR, Rol.TRABAJO_SOCIAL]


def _citas(hogar, residente):
    from citas.models import Cita
    qs = Cita.objects.filter(residente__hogar=hogar, residente__activo=True, estado=Cita.PROGRAMADA).select_related('residente')
    if residente is not None:
        qs = qs.filter(residente=residente)
    return qs, Cita


def cita_proxima(hogar, config, residente=None):
    qs, Cita = _citas(hogar, residente)
    hoy = timezone.localdate()
    ahora = timezone.now()
    for c in qs.filter(fecha_hora__gte=ahora - timedelta(hours=2)):
        dia = timezone.localdate(c.fecha_hora)
        if dia not in (hoy, hoy + timedelta(days=1)):
            continue
        cuando = 'hoy' if dia == hoy else 'mañana'
        faltantes = []
        if c.transporte == Cita.POR_DEFINIR:
            faltantes.append('transporte')
        if not c.acompanante and c.transporte != 'en_el_hogar':
            faltantes.append('acompañante')
        partes = [f'{c.lugar}.']
        if c.requiere_ayuno:
            partes.append('Requiere AYUNO.')
        if c.preparacion:
            partes.append(f'Preparación: {c.preparacion}')
        partes.append(f'Acompaña: {c.acompanante or "sin definir"}. Transporte: {c.get_transporte_display().lower()}.')
        if faltantes:
            partes.append(f'Falta definir {" y ".join(faltantes)}.')
        yield Candidato(
            clave=f'cita_proxima:{c.pk}:{cuando}', residente=c.residente,
            gravedad=ALTA if faltantes else (MEDIA if dia == hoy else INFORMATIVA),
            titulo=f'Cita {cuando} a las {_hora(c.fecha_hora)}: {c.titulo} — {c.nombre_residente}',
            mensaje=' '.join(partes),
            url=reverse('cita_detalle', args=[c.pk]), texto_accion='Ver cita',
            roles=ROLES_CITAS,
        )


def cita_sin_cierre(hogar, config, residente=None):
    qs, Cita = _citas(hogar, residente)
    limite = timezone.now() - timedelta(hours=config.umbral('horas_cita_sin_cierre'))
    for c in qs.filter(fecha_hora__lt=limite):
        yield Candidato(
            clave=f'cita_sin_cierre:{c.pk}', gravedad=MEDIA, residente=c.residente,
            titulo=f'No se ha registrado qué pasó en la cita del {_fecha(c.fecha_hora)} de {c.nombre_residente} ({c.titulo})',
            mensaje='Registre si se cumplió (con el resumen y la fórmula u orden) o si no asistió.',
            url=reverse('cita_detalle', args=[c.pk]), texto_accion='Registrar qué pasó',
            roles=ROLES_CITAS + [Rol.MEDICO],
        )


# ── Signos vitales, peso, líquidos y eliminación ────────────────────

ROLES_SIGNOS = [Rol.ENFERMERO, Rol.JEFE_ENFERMERIA]


def _controles_recientes(hogar, residente):
    from signos import services as sv
    for r in _residentes(hogar, residente):
        control = sv.ultimo_control(r)
        if control:
            yield r, control, sv


def signo_critico(hogar, config, residente=None):
    """Se mantiene mientras la última toma del residente tenga un valor
    crítico (una toma nueva normal la resuelve)."""
    for r, control, sv in _controles_recientes(hogar, residente):
        criticos, _ = sv.hallazgos(control)
        if criticos:
            yield Candidato(
                clave=f'signo_critico:{control.pk}', gravedad=CRITICA, residente=r,
                titulo=f'Signos vitales críticos de {r.get_nombre()}: {"; ".join(criticos)}',
                mensaje=f'Tomados el {_fecha(control.fecha_hora)} a las {_hora(control.fecha_hora)}. '
                        'Valore al residente, informe al médico y repita la toma.',
                url=reverse('signos_residente', args=[r.pk]), texto_accion='Ver signos vitales',
                roles=[Rol.MEDICO, Rol.JEFE_ENFERMERIA, Rol.ENFERMERO],
            )


def signo_fuera_rango(hogar, config, residente=None):
    limite = timezone.now() - timedelta(hours=config.umbral('horas_signo_fuera_rango'))
    for r, control, sv in _controles_recientes(hogar, residente):
        if control.fecha_hora < limite:
            continue
        criticos, fuera = sv.hallazgos(control)
        if fuera and not criticos:
            yield Candidato(
                clave=f'signo_fuera:{control.pk}', gravedad=MEDIA, residente=r,
                titulo=f'Signos fuera de rango de {r.get_nombre()}: {"; ".join(fuera)}',
                mensaje=f'Tomados a las {_hora(control.fecha_hora)} del {_fecha(control.fecha_hora)}. Vigile y repita la toma.',
                url=reverse('signos_residente', args=[r.pk]), texto_accion='Ver signos vitales',
                roles=ROLES_SIGNOS,
            )


def sin_control_signos(hogar, config, residente=None):
    from signos import services as sv
    horas = config.umbral('horas_sin_control_signos')
    limite = timezone.now() - timedelta(hours=horas)
    for r in _residentes(hogar, residente):
        if r.fecha_ingreso > limite:
            continue
        control = sv.ultimo_control(r)
        if control and control.fecha_hora >= limite:
            continue
        cuando = (f'desde el {_fecha(control.fecha_hora)} a las {_hora(control.fecha_hora)}' if control
                  else 'nunca se han registrado')
        yield Candidato(
            clave=f'sin_control_signos:{r.pk}', gravedad=MEDIA, residente=r,
            titulo=f'{r.get_nombre()} lleva más de {horas} horas sin toma de signos vitales',
            mensaje=f'Última toma: {cuando}.' if control else 'Nunca se han registrado signos vitales.',
            url=reverse('signos_control_crear', args=[r.pk]), texto_accion='Registrar signos vitales',
            roles=ROLES_SIGNOS,
        )


def sin_deposicion(hogar, config, residente=None):
    from signos import services as sv
    umbral = config.umbral('dias_sin_deposicion')
    for r in _residentes(hogar, residente):
        dias, referencia = sv.dias_sin_deposicion(r)
        if dias < umbral:
            continue
        desde = ('la última registrada fue el ' + _fecha(referencia)) if sv.ultima_eliminacion(r, 'deposicion') \
            else 'no hay ninguna registrada desde su ingreso'
        yield Candidato(
            clave=f'sin_deposicion:{r.pk}', gravedad=ALTA if dias >= umbral + 2 else MEDIA, residente=r,
            titulo=f'Alerta: {dias} días sin deposición — {r.get_nombre()}',
            mensaje=f'Según las notas de enfermería, {desde}. Valore distensión abdominal, dolor e hidratación e informe al médico.',
            url=reverse('signos_residente', args=[r.pk]), texto_accion='Ver eliminación',
            roles=[Rol.ENFERMERO, Rol.JEFE_ENFERMERIA, Rol.MEDICO],
        )


def sin_diuresis(hogar, config, residente=None):
    from signos import services as sv
    umbral = config.umbral('horas_sin_diuresis')
    for r in _residentes(hogar, residente):
        horas, referencia = sv.horas_sin_diuresis(r)
        if horas < umbral:
            continue
        yield Candidato(
            clave=f'sin_diuresis:{r.pk}', gravedad=ALTA, residente=r,
            titulo=f'{r.get_nombre()}: {horas} horas sin diuresis registrada',
            mensaje='Según las notas de enfermería. Revise si orinó (pañal, sonda) y regístrelo en la nota; si no, informe al médico.',
            url=reverse('signos_residente', args=[r.pk]), texto_accion='Ver eliminación',
            roles=[Rol.ENFERMERO, Rol.JEFE_ENFERMERIA, Rol.MEDICO],
        )


def perdida_peso(hogar, config, residente=None):
    from signos import services as sv
    umbral = config.umbral('porcentaje_perdida_peso')
    for r in _residentes(hogar, residente):
        cambio = sv.cambio_de_peso(r, dias=30)
        if not cambio or cambio[2] > -umbral:
            continue
        actual, referencia, pct = cambio
        yield Candidato(
            clave=f'perdida_peso:{r.pk}:{actual.pk}', gravedad=ALTA, residente=r,
            titulo=f'{r.get_nombre()} perdió {abs(pct):.1f} % de su peso en 30 días',
            mensaje=f'{referencia.peso} kg el {_fecha(referencia.fecha_hora)} → {actual.peso} kg el {_fecha(actual.fecha_hora)}. '
                    'Requiere valoración médica y nutricional.',
            url=reverse('signos_residente', args=[r.pk]) + '?dias=30', texto_accion='Ver evolución del peso',
            roles=[Rol.MEDICO, Rol.NUTRICIONISTA, Rol.JEFE_ENFERMERIA],
        )


def balance_negativo(hogar, config, residente=None):
    from signos import services as sv
    umbral = config.umbral('ml_balance_negativo')
    ahora = timezone.now()
    for r in _residentes(hogar, residente):
        b = sv.balance(r, ahora - timedelta(hours=24), ahora + timedelta(minutes=1))
        if not b['registros'] or b['balance'] > -umbral:
            continue
        yield Candidato(
            clave=f'balance_negativo:{r.pk}', gravedad=MEDIA, residente=r,
            titulo=f'Balance de líquidos negativo de {r.get_nombre()}: {b["balance"]} mL en 24 horas',
            mensaje=f'Ingresos {b["ingresos"]} mL, egresos {b["egresos"]} mL. Ofrezca líquidos si no hay restricción y vigile signos de deshidratación.',
            url=reverse('signos_residente', args=[r.pk]) + '#liquidos', texto_accion='Ver balance',
            roles=[Rol.ENFERMERO, Rol.JEFE_ENFERMERIA, Rol.MEDICO],
        )


# ── Valoración geriátrica ───────────────────────────────────────────

DIAS_AVISO_RESULTADO = 7


def valoracion_resultado(hogar, config, residente=None):
    """Resultado de riesgo o deterioro marcado en la última aplicación de
    cada escala; el aviso dura una semana desde la aplicación."""
    from valoracion import services as vs
    desde = timezone.localdate() - timedelta(days=DIAS_AVISO_RESULTADO)
    for r in _residentes(hogar, residente):
        for f in vs.estado_por_escala(r):
            v, e = f['ultima'], f['escala']
            if not v or v.fecha < desde:
                continue
            banda = e.interpretar(v.puntaje)
            empeoro = (e.deterioro_alerta and f['cambio'] is not None and f['cambio'] <= -e.deterioro_alerta)
            if not (banda and banda.alerta) and not empeoro:
                continue
            partes = []
            if empeoro:
                partes.append(f'empeoró {abs(f["cambio"])} puntos frente a la anterior ({f["anterior"].puntaje} el {f["anterior"].fecha:%d/%m/%Y})')
            titulo = (f'{e.corto} de {r.get_nombre()}: {v.puntaje} — {v.interpretacion}'
                      + (' (empeoró)' if empeoro else ''))
            yield Candidato(
                clave=f'valoracion_resultado:{v.pk}', gravedad=ALTA, residente=r, titulo=titulo,
                mensaje=(f'Aplicada el {v.fecha:%d/%m/%Y}. ' + ('; '.join(partes) + '. ' if partes else '')
                         + 'Considérelo en el plan de atención del residente.'),
                url=reverse('valoracion_detalle', args=[v.pk]), texto_accion='Ver resultado',
                roles=sorted(set(e.roles) | {Rol.MEDICO}),
            )


def valoracion_vencida(hogar, config, residente=None):
    from valoracion import services as vs
    from valoracion.models import ConfiguracionValoracion
    cv = ConfiguracionValoracion.para_hogar(hogar)
    for r in _residentes(hogar, residente):
        vencidas = vs.vencidas(r, cv)
        if not vencidas:
            continue
        nombres = ', '.join(f['escala'].corto for f in vencidas)
        yield Candidato(
            clave=f'valoracion_vencida:{r.pk}', gravedad=INFORMATIVA, residente=r,
            titulo=f'{r.get_nombre()}: escalas por aplicar o repetir — {nombres}',
            mensaje='Según la periodicidad que exige el hogar.',
            url=reverse('valoracion_residente', args=[r.pk]), texto_accion='Ver valoración geriátrica',
            roles=[Rol.MEDICO, Rol.JEFE_ENFERMERIA],
        )


# ── Plan de atención ────────────────────────────────────────────────

def plan_atencion(hogar, config, residente=None):
    """Residente sin plan vigente (después de 30 días del ingreso) o con la
    revisión del plan vencida."""
    from plan_atencion import services as ps
    for r in _residentes(hogar, residente):
        v = ps.vigente(r)
        if v is None and ps.falta_plan(r):
            b = ps.borrador(r)
            yield Candidato(
                clave=f'plan_faltante:{r.pk}', gravedad=MEDIA, residente=r,
                titulo=f'{r.get_nombre()} no tiene plan de atención vigente',
                mensaje=('Hay un borrador en elaboración: complételo y actívelo.' if b else
                         'Elabore el plan con el equipo a partir de la valoración geriátrica.'),
                url=reverse('plan_residente', args=[r.pk]), texto_accion='Abrir plan de atención',
                roles=[Rol.MEDICO, Rol.JEFE_ENFERMERIA],
            )
        elif v is not None and v.revision_vencida:
            yield Candidato(
                clave=f'plan_revision:{v.pk}', gravedad=MEDIA, residente=r,
                titulo=f'La revisión del plan de atención de {r.get_nombre()} está vencida (desde el {v.fecha_revision:%d/%m/%Y})',
                mensaje='Revise con el equipo los objetivos y cree la nueva versión del plan.',
                url=reverse('plan_detalle', args=[v.pk]), texto_accion='Revisar plan',
                roles=[Rol.MEDICO, Rol.JEFE_ENFERMERIA],
            )


# ── Registro ────────────────────────────────────────────────────────

REGLAS = {
    'examen_critico': (examen_critico, 'Resultado de examen con valores críticos'),
    'examen_por_revisar': (examen_por_revisar, 'Resultado de examen sin revisión médica'),
    'examen_sin_resultado': (examen_sin_resultado, 'Orden de examen sin resultado'),
    'lote_vencido': (lote_vencido, 'Lote de medicamento vencido'),
    'lote_por_vencer': (lote_por_vencer, 'Lote de medicamento por vencer'),
    'stock_bajo': (stock_bajo, 'Medicamento por agotarse en el cajón'),
    'prestamo_sin_reponer': (prestamo_sin_reponer, 'Préstamo del botiquín sin reponer'),
    'orden_por_terminar': (orden_por_terminar, 'Orden médica por terminar'),
    'toma_no_registrada': (toma_no_registrada, 'Toma de medicamento sin registrar'),
    'prn_frecuente': (prn_frecuente, 'Medicamento "si es necesario" por encima del máximo diario'),
    'sin_alergias': (sin_alergias_registradas, 'Residente sin alergias registradas'),
    'cita_proxima': (cita_proxima, 'Cita médica hoy o mañana'),
    'cita_sin_cierre': (cita_sin_cierre, 'Cita pasada sin registrar qué pasó'),
    'signo_critico': (signo_critico, 'Signos vitales en rango crítico'),
    'signo_fuera_rango': (signo_fuera_rango, 'Signos vitales fuera de rango'),
    'sin_control_signos': (sin_control_signos, 'Residente sin toma de signos vitales'),
    'sin_deposicion': (sin_deposicion, 'Días sin deposición'),
    'sin_diuresis': (sin_diuresis, 'Horas sin diuresis'),
    'perdida_peso': (perdida_peso, 'Pérdida de peso'),
    'balance_negativo': (balance_negativo, 'Balance de líquidos negativo'),
    'valoracion_resultado': (valoracion_resultado, 'Escala de valoración con resultado de riesgo o deterioro'),
    'valoracion_vencida': (valoracion_vencida, 'Escalas de valoración por aplicar o repetir'),
    'plan_atencion': (plan_atencion, 'Plan de atención faltante o con revisión vencida'),
}

# Qué reglas reevaluar de inmediato cuando cambia cada tipo de registro.
REGLAS_POR_MODELO = {
    'examen': ['examen_critico', 'examen_por_revisar', 'examen_sin_resultado'],
    'lote': ['lote_vencido', 'lote_por_vencer', 'stock_bajo'],
    'administracion': ['toma_no_registrada', 'prn_frecuente', 'prestamo_sin_reponer', 'stock_bajo'],
    'prescripcion': ['orden_por_terminar', 'stock_bajo', 'toma_no_registrada', 'prn_frecuente'],
    'alergias': ['sin_alergias'],
    'cita': ['cita_proxima', 'cita_sin_cierre'],
    'signos': ['signo_critico', 'signo_fuera_rango', 'sin_control_signos', 'perdida_peso'],
    'liquidos': ['balance_negativo'],
    'nota': ['sin_deposicion', 'sin_diuresis'],
    'valoracion': ['valoracion_resultado', 'valoracion_vencida'],
    'plan': ['plan_atencion'],
}
