"""Transiciones de estado de las citas, en un solo lugar."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Cita

CAMPOS_COPIABLES = [
    'residente', 'tipo', 'especialidad', 'profesional', 'lugar', 'requiere_ayuno',
    'preparacion', 'acompanante', 'transporte', 'observaciones',
]


def _bloquear(cita):
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if not cita.abierta:
        raise ValidationError(f'Esta cita ya está {cita.get_estado_display().lower()}.')
    return cita


@transaction.atomic
def cerrar(cita, usuario, estado, resumen, archivo=None):
    """Registra qué pasó: cumplida (con resumen) o no asistió (con motivo)."""
    if estado not in (Cita.CUMPLIDA, Cita.NO_ASISTIO):
        raise ValidationError('Elija si la cita se cumplió o si no asistió.')
    if not resumen.strip():
        raise ValidationError('Escriba qué pasó en la cita o por qué no asistió.')
    cita = _bloquear(cita)
    if timezone.localdate(cita.fecha_hora) > timezone.localdate():
        raise ValidationError('No se puede cerrar una cita que todavía no ha llegado. Si no va a ir, cancélela.')
    cita.estado = estado
    cita.resumen = resumen.strip()
    if archivo:
        cita.archivo_soporte.save(archivo.name, archivo, save=False)
    cita.cerrada_por = usuario
    cita.fecha_cierre = timezone.now()
    cita.save()
    return cita


@transaction.atomic
def cancelar(cita, usuario, motivo):
    if not motivo.strip():
        raise ValidationError('La cancelación necesita un motivo.')
    cita = _bloquear(cita)
    cita.estado = Cita.CANCELADA
    cita.resumen = motivo.strip()
    cita.cerrada_por = usuario
    cita.fecha_cierre = timezone.now()
    cita.save()
    return cita


@transaction.atomic
def reprogramar(cita, usuario, nueva_fecha_hora, motivo, lugar=''):
    """Cierra la cita como reprogramada y crea la nueva, enlazada."""
    if not motivo.strip():
        raise ValidationError('La reprogramación necesita un motivo.')
    if nueva_fecha_hora < timezone.now():
        raise ValidationError('La nueva fecha ya pasó.')
    cita = _bloquear(cita)
    cita.estado = Cita.REPROGRAMADA
    cita.resumen = motivo.strip()
    cita.cerrada_por = usuario
    cita.fecha_cierre = timezone.now()
    cita.save()
    nueva = Cita(**{c: getattr(cita, c) for c in CAMPOS_COPIABLES})
    nueva.fecha_hora = nueva_fecha_hora
    if lugar.strip():
        nueva.lugar = lugar.strip()
    nueva.reprogramada_desde = cita
    nueva.registrado_por = usuario
    nueva.save()
    return nueva


def citas_del_hogar(hogar):
    return Cita.objects.filter(residente__hogar=hogar, residente__activo=True).select_related('residente')


def proximas(hogar, dias=7):
    """Citas programadas desde hoy a las 00:00 hasta completar `dias` días
    (dias=1 → solo hoy; dias=2 → hoy y mañana)."""
    inicio = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return citas_del_hogar(hogar).filter(
        estado=Cita.PROGRAMADA, fecha_hora__gte=inicio, fecha_hora__lt=inicio + timedelta(days=dias),
    )


def sin_cierre(hogar, horas_gracia=0):
    """Citas programadas cuya hora ya pasó (más la gracia) sin registro de qué pasó."""
    limite = timezone.now() - timedelta(hours=horas_gracia)
    return citas_del_hogar(hogar).filter(estado=Cita.PROGRAMADA, fecha_hora__lt=limite)
