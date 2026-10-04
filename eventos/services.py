"""Reglas de negocio e indicadores de eventos adversos."""
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from .models import CAIDA, GRAVEDADES_ALTAS, MEDICACION, TIPOS, ConfiguracionEventos, EventoAdverso, VigilanciaEvento


@transaction.atomic
def registrar(evento, usuario, anonimo=False):
    """Guarda el reporte. En modo anónimo voluntario, si quien reporta lo pide,
    no se guarda su nombre. Después de una caída programa la vigilancia."""
    config = ConfiguracionEventos.para_hogar(evento.residente.hogar)
    evento.hogar = evento.residente.hogar
    evento.anonimo = bool(anonimo and config.modo_reporte == ConfiguracionEventos.ANONIMO)
    evento.reportado_por = None if evento.anonimo else usuario
    evento.save()
    if evento.tipo == CAIDA and evento.gravedad != 'muerte':
        programar_vigilancia(evento, config)
    return evento


def programar_vigilancia(evento, config):
    intervalo = max(1, config.intervalo_vigilancia_horas)
    pasos = max(1, config.horas_vigilancia_caida // intervalo)
    base = max(evento.fecha_hora, timezone.now() - timedelta(hours=intervalo))
    VigilanciaEvento.objects.bulk_create([
        VigilanciaEvento(evento=evento, programada=base + timedelta(hours=intervalo * i)) for i in range(1, pasos + 1)
    ])


@transaction.atomic
def cerrar(evento, usuario, causas, acciones, responsable='', fecha_limite=None):
    if not evento.abierto:
        raise ValueError('El evento ya está cerrado.')
    evento.estado = EventoAdverso.CERRADO
    evento.causas = causas
    evento.acciones_mejora = acciones
    evento.responsable_acciones = responsable
    evento.fecha_limite_acciones = fecha_limite
    evento.cerrado_por = usuario
    evento.fecha_cierre = timezone.now()
    evento.save(update_fields=list(EventoAdverso.CAMPOS_CIERRE))
    return evento


def registrar_vigilancia(vigilancia, usuario, conciencia, dolor, hallazgos, requiere_medico):
    if not vigilancia.pendiente:
        raise ValueError('Esta revisión ya se registró.')
    vigilancia.realizada = timezone.now()
    vigilancia.realizada_por = usuario
    vigilancia.conciencia = conciencia
    vigilancia.dolor = dolor
    vigilancia.hallazgos = hallazgos
    vigilancia.requiere_medico = requiere_medico
    vigilancia.save()
    return vigilancia


def vigilancias_pendientes(hogar, hasta=None):
    hasta = hasta or timezone.now()
    return (VigilanciaEvento.objects.filter(evento__hogar=hogar, evento__residente__activo=True,
                                            realizada__isnull=True, programada__lte=hasta)
            .select_related('evento__residente').order_by('programada'))


# ── Indicadores ─────────────────────────────────────────────────────

def _mes(fecha):
    return date(fecha.year, fecha.month, 1)


def _sumar_meses(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def dias_residente(hogar, inicio, fin):
    """Días-residente del periodo [inicio, fin): días que cada residente vivió
    en el hogar (desde su ingreso hasta hoy, o hasta el fin de su última
    asignación de cama si ya egresó)."""
    from django.db.models import Max
    from residentes.models import Residente
    tz = timezone.get_current_timezone()
    ini = timezone.make_aware(datetime.combine(inicio, time.min), tz)
    hasta = min(timezone.make_aware(datetime.combine(fin, time.min), tz), timezone.now())
    total = 0.0
    for r in Residente.objects.filter(hogar=hogar, fecha_ingreso__lt=hasta).annotate(salida=Max('asignaciones__fecha_fin')):
        termina = hasta if r.activo else min(r.salida or r.fecha_ingreso, hasta)
        desde = max(r.fecha_ingreso, ini)
        if termina > desde:
            total += (termina - desde).total_seconds() / 86400
    return round(total)


def indicadores(hogar, meses=12):
    """Una fila por mes (del más antiguo al actual) con los indicadores."""
    from cuidados.models import Herida
    hoy = timezone.localdate()
    primero = _sumar_meses(_mes(hoy), -(meses - 1))
    eventos = list(EventoAdverso.objects.filter(hogar=hogar, fecha_hora__date__gte=primero))
    filas = []
    for i in range(meses):
        inicio = _sumar_meses(primero, i)
        fin = _sumar_meses(inicio, 1)
        del_mes = [e for e in eventos if inicio <= timezone.localdate(e.fecha_hora) < fin]
        caidas = [e for e in del_mes if e.tipo == CAIDA]
        dr = dias_residente(hogar, inicio, fin)
        filas.append({
            'mes': inicio,
            'total': len(del_mes),
            'por_tipo': {t: sum(1 for e in del_mes if e.tipo == t) for t, _ in TIPOS},
            'caidas': len(caidas),
            'caidas_con_dano': sum(1 for e in caidas if e.gravedad in GRAVEDADES_ALTAS),
            'medicacion': sum(1 for e in del_mes if e.tipo == MEDICACION),
            'graves': sum(1 for e in del_mes if e.gravedad in GRAVEDADES_ALTAS),
            'lpp_hogar': Herida.objects.filter(residente__hogar=hogar, tipo=Herida.LPP, origen='hogar',
                                               fecha_deteccion__gte=inicio, fecha_deteccion__lt=fin).count(),
            'dias_residente': dr,
            'tasa_caidas': round(1000 * len(caidas) / dr, 1) if dr else None,
        })
    return filas
