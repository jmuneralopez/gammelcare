from django.db import transaction
from django.utils import timezone

from .models import Alergia, EstadoAlergias


def alergias_activas(residente):
    return list(residente.alergias.filter(activo=True).select_related('medicamento'))


def conflictos_alergia(residente, medicamento):
    """Alergias activas del residente que coinciden con este medicamento
    (por enlace al catálogo o por nombre). No reconoce familias de
    medicamentos: una alergia a "penicilina" no avisa con "amoxicilina"."""
    return [a for a in alergias_activas(residente) if a.coincide_con(medicamento)]


@transaction.atomic
def registrar_alergia(alergia, usuario):
    alergia.registrado_por = usuario
    alergia.save()
    EstadoAlergias.objects.filter(residente=alergia.residente, sin_alergias_conocidas=True).update(
        sin_alergias_conocidas=False, actualizado_por=usuario, fecha_actualizacion=timezone.now(),
    )
    return alergia


def declarar_sin_alergias(residente, usuario):
    if residente.alergias.filter(activo=True).exists():
        raise ValueError('El residente tiene alergias activas registradas.')
    estado, _ = EstadoAlergias.objects.update_or_create(
        residente=residente,
        defaults={'sin_alergias_conocidas': True, 'actualizado_por': usuario, 'fecha_actualizacion': timezone.now()},
    )
    return estado


def estado_alergias(residente):
    """'alergias' | 'sin_alergias' | 'sin_dato' para mostrar en pantalla."""
    if residente.alergias.filter(activo=True).exists():
        return 'alergias'
    estado = EstadoAlergias.objects.filter(residente=residente).first()
    if estado and estado.sin_alergias_conocidas:
        return 'sin_alergias'
    return 'sin_dato'
