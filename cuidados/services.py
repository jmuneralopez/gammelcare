"""Consultas y reglas de negocio de cuidados diarios y heridas."""
from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from .models import (BANIO, DETALLES, MOVILIZACION, PANAL, POSICION, ROTACION_POSICION, TIPOS_CUIDADO,
                     Herida, PlanCuidados, RegistroCuidado)

# Turnos del hogar: mañana 6-14, tarde 14-22, noche 22-6.
TURNOS = [('manana', 'Mañana', 6, 14), ('tarde', 'Tarde', 14, 22), ('noche', 'Noche', 22, 6)]
NORTON_RIESGO = 14          # Norton 14 o menos: riesgo de lesiones por presión.
NORTON_RIESGO_ALTO = 12     # 12 o menos: riesgo alto, cambios cada 2 horas.


def turno_actual(ahora=None):
    """(codigo, nombre, inicio, fin) del turno en curso, en hora local."""
    ahora = timezone.localtime(ahora or timezone.now())
    for codigo, nombre, h_ini, h_fin in TURNOS:
        if h_ini < h_fin and h_ini <= ahora.hour < h_fin:
            dia = ahora.date()
            inicio = datetime.combine(dia, time(h_ini))
            fin = datetime.combine(dia, time(h_fin))
            break
    else:
        codigo, nombre = 'noche', 'Noche'
        dia = ahora.date() if ahora.hour >= 22 else ahora.date() - timedelta(days=1)
        inicio = datetime.combine(dia, time(22))
        fin = datetime.combine(dia + timedelta(days=1), time(6))
    tz = timezone.get_current_timezone()
    return codigo, nombre, timezone.make_aware(inicio, tz), timezone.make_aware(fin, tz)


def plan_de(residente):
    """El plan del residente, o uno sin guardar con los valores por defecto
    (más los cambios de posición si la escala de Norton marca riesgo)."""
    plan = PlanCuidados.objects.filter(residente_id=residente.pk).first()
    return plan or sugerencia_plan(residente)


def ultimo_norton(residente):
    return (residente.valoraciones.filter(escala='norton', anulada=False)
            .order_by('-fecha', '-fecha_registro').first())


def sugerencia_plan(residente):
    # Por id, para no dejar el plan sin guardar en la caché del residente.
    plan = PlanCuidados(residente_id=residente.pk)
    norton = ultimo_norton(residente)
    if norton and norton.puntaje <= NORTON_RIESGO:
        plan.cambios_posicion = True
        plan.intervalo_posicion_horas = 2 if norton.puntaje <= NORTON_RIESGO_ALTO else 3
    return plan


def ultimo(residente, tipo):
    return (RegistroCuidado.objects.filter(residente=residente, tipo=tipo, anulado=False)
            .order_by('-fecha_hora').first())


def siguiente_posicion(ultimo_registro):
    if not ultimo_registro or ultimo_registro.detalle not in ROTACION_POSICION:
        return ROTACION_POSICION[0]
    i = ROTACION_POSICION.index(ultimo_registro.detalle)
    return ROTACION_POSICION[(i + 1) % len(ROTACION_POSICION)]


def posicion_vencida(plan, ultimo_registro, ahora=None, gracia_min=0):
    """Minutos de atraso del próximo cambio de posición (0 si está al día)."""
    if not plan.cambios_posicion:
        return 0
    ahora = ahora or timezone.now()
    desde = ultimo_registro.fecha_hora if ultimo_registro else (plan.fecha_actualizacion if plan.pk else None)
    if desde is None:
        return 0
    limite = desde + timedelta(hours=plan.intervalo_posicion_horas, minutes=gracia_min)
    return max(0, int((ahora - limite).total_seconds() // 60))


def dias_sin_banio(residente):
    u = ultimo(residente, BANIO)
    referencia = u.fecha_hora if u else residente.fecha_ingreso
    return (timezone.localdate() - timezone.localdate(referencia)).days, u


def banio_pendiente(plan, residente):
    if plan.banio == PlanCuidados.NO_APLICA:
        return False
    dias, _ = dias_sin_banio(residente)
    return dias >= (1 if plan.banio == PlanCuidados.DIARIO else 2)


def celda(residente, plan, tipo, desde_turno, ahora=None):
    """Estado de un cuidado para la planilla: último registro, conteo en el
    turno, opción sugerida y si está pendiente."""
    ahora = ahora or timezone.now()
    u = ultimo(residente, tipo)
    en_turno = RegistroCuidado.objects.filter(residente=residente, tipo=tipo, anulado=False,
                                              fecha_hora__gte=desde_turno).count()
    sugerido = DETALLES[tipo][0][0]
    pendiente = False
    atraso = 0
    if tipo == POSICION:
        sugerido = siguiente_posicion(u)
        atraso = posicion_vencida(plan, u, ahora)
        pendiente = atraso > 0
    elif tipo == BANIO:
        horas = 48 if plan.banio == PlanCuidados.INTERDIARIO else 24
        pendiente = u is None or (ahora - u.fecha_hora) > timedelta(hours=horas)
    elif tipo == PANAL:
        pendiente = u is None or (ahora - u.fecha_hora) > timedelta(hours=4)
    elif tipo == MOVILIZACION:
        pendiente = en_turno == 0 and u is not None and (ahora - u.fecha_hora) > timedelta(hours=24)
    else:  # higiene oral: al menos cada 12 horas
        pendiente = u is None or (ahora - u.fecha_hora) > timedelta(hours=12)
    return {
        'tipo': tipo, 'ultimo': u, 'en_turno': en_turno, 'pendiente': pendiente, 'atraso': atraso,
        'sugerido': sugerido, 'sugerido_texto': dict(DETALLES[tipo])[sugerido], 'opciones': DETALLES[tipo],
        'minutos': int((ahora - u.fecha_hora).total_seconds() // 60) if u else None,
    }


def planilla(hogar, ahora=None):
    """Una fila por residente activo, en el orden de pabellón, habitación y
    cama, con una celda por cuidado que tiene en su plan."""
    from residentes.models import Residente
    ahora = ahora or timezone.now()
    _, _, inicio, _ = turno_actual(ahora)
    residentes = (Residente.objects.filter(hogar=hogar, activo=True)
                  .select_related('cama_actual__habitacion__departamento')
                  .order_by('cama_actual__habitacion__departamento__nombre', 'cama_actual__habitacion__numero',
                            'cama_actual__codigo'))
    filas = []
    for r in residentes:
        plan = plan_de(r)
        celdas = {t: celda(r, plan, t, inicio, ahora) for t in plan.tipos()}
        filas.append({
            'residente': r, 'nombre': r.get_nombre(), 'plan': plan, 'celdas': celdas,
            'pendientes': sum(1 for c in celdas.values() if c['pendiente']),
            'heridas': r.heridas.filter(estado=Herida.ACTIVA).count(),
        })
    return filas


def detalle_valido(tipo, detalle):
    return tipo in DETALLES and detalle in dict(DETALLES[tipo])


@transaction.atomic
def registrar(residente, tipo, detalle, usuario, fecha_hora=None, observaciones=''):
    if not detalle_valido(tipo, detalle):
        raise ValueError('Cuidado u opción no válida.')
    ahora = timezone.now()
    fecha_hora = fecha_hora or ahora
    if fecha_hora > ahora + timedelta(minutes=5):
        raise ValueError('La hora del cuidado no puede estar en el futuro.')
    return RegistroCuidado.objects.create(residente=residente, tipo=tipo, detalle=detalle, fecha_hora=fecha_hora,
                                          observaciones=observaciones, registrado_por=usuario)


def historial(residente, desde, hasta):
    return (RegistroCuidado.objects.filter(residente=residente, fecha_hora__gte=desde, fecha_hora__lt=hasta)
            .select_related('registrado_por', 'anulado_por').order_by('-fecha_hora'))


def resumen_dia(residente, dia=None):
    """Conteo de cada cuidado en un día (para el expediente)."""
    dia = dia or timezone.localdate()
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(dia, time.min), tz)
    regs = RegistroCuidado.objects.filter(residente=residente, anulado=False, fecha_hora__gte=inicio,
                                          fecha_hora__lt=inicio + timedelta(days=1))
    conteo = {codigo: 0 for codigo, _ in TIPOS_CUIDADO}
    for r in regs:
        conteo[r.tipo] += 1
    return conteo


def heridas_activas(residente):
    return residente.heridas.filter(estado=Herida.ACTIVA).prefetch_related('seguimientos')


def dias_sin_seguimiento(herida):
    s = herida.ultimo_seguimiento()
    referencia = s.fecha_hora if s else herida.fecha_registro
    return (timezone.localdate() - timezone.localdate(referencia)).days, s
