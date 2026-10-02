from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ObjetivoPlan, PlanAtencion, SeguimientoObjetivo

MESES_REVISION = 3
DIAS_SIN_PLAN = 30  # días desde el ingreso para exigir un plan vigente


def vigente(residente):
    return PlanAtencion.objects.filter(residente=residente, estado=PlanAtencion.VIGENTE).first()


def borrador(residente):
    return PlanAtencion.objects.filter(residente=residente, estado=PlanAtencion.BORRADOR).first()


def _fecha_revision():
    return timezone.localdate() + timedelta(days=30 * MESES_REVISION)


@transaction.atomic
def crear_borrador(residente, usuario):
    """Crea la siguiente versión en borrador. Si hay un plan vigente, copia
    su resumen, participantes y los objetivos que siguen en curso."""
    if borrador(residente):
        raise ValidationError('Ya hay un plan en borrador para este residente.')
    actual = vigente(residente)
    ultima = PlanAtencion.objects.filter(residente=residente).order_by('-version').first()
    plan = PlanAtencion.objects.create(
        residente=residente, version=(ultima.version + 1) if ultima else 1,
        resumen=actual.resumen if actual else '', participantes=actual.participantes if actual else '',
        acuerdos_familia=actual.acuerdos_familia if actual else '',
        fecha_revision=_fecha_revision(), creado_por=usuario, anterior=actual,
    )
    if actual:
        for o in actual.objetivos.filter(estado=ObjetivoPlan.EN_CURSO):
            ObjetivoPlan.objects.create(
                plan=plan, area=o.area, necesidad=o.necesidad, meta=o.meta, intervenciones=o.intervenciones,
                responsable=o.responsable, frecuencia=o.frecuencia,
                fecha_meta=max(o.fecha_meta, timezone.localdate() + timedelta(days=30)),
                origen=o.origen, creado_por=usuario, copiado_de=o,
            )
    return plan


@transaction.atomic
def activar(plan, usuario):
    plan = PlanAtencion.objects.select_for_update().get(pk=plan.pk)
    if plan.estado != PlanAtencion.BORRADOR:
        raise ValidationError('Solo se activa un plan en borrador.')
    if not plan.objetivos.exists():
        raise ValidationError('Agregue al menos un objetivo antes de activar el plan.')
    if not plan.resumen.strip():
        raise ValidationError('Escriba la situación actual del residente antes de activar el plan.')
    ahora = timezone.now()
    anterior = PlanAtencion.objects.select_for_update().filter(
        residente=plan.residente, estado=PlanAtencion.VIGENTE).first()
    if anterior:
        anterior.estado = PlanAtencion.REEMPLAZADO
        anterior.fecha_reemplazo = ahora
        anterior.save(update_fields=['estado', 'fecha_reemplazo'])
    plan.estado = PlanAtencion.VIGENTE
    plan.activado_por = usuario
    plan.fecha_activacion = ahora
    plan.save(update_fields=['estado', 'activado_por', 'fecha_activacion'])
    return plan


@transaction.atomic
def registrar_seguimiento(objetivo, usuario, estado, nota):
    objetivo = ObjetivoPlan.objects.select_for_update().select_related('plan').get(pk=objetivo.pk)
    if objetivo.plan.estado != PlanAtencion.VIGENTE:
        raise ValidationError('El seguimiento se registra sobre el plan vigente.')
    if not nota.strip():
        raise ValidationError('Escriba qué se observó.')
    s = SeguimientoObjetivo.objects.create(objetivo=objetivo, estado=estado, nota=nota.strip(), registrado_por=usuario)
    objetivo.estado = estado
    objetivo.save(update_fields=['estado'])
    return s


def falta_plan(residente):
    """True si el residente lleva más de DIAS_SIN_PLAN en el hogar sin plan vigente."""
    if vigente(residente):
        return False
    return residente.fecha_ingreso < timezone.now() - timedelta(days=DIAS_SIN_PLAN)
