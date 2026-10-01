import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from .models import Alerta, VistaAlerta
from .permisos import puede_ver_todas, roles_de


def orden_gravedad():
    return Case(*[When(gravedad=g, then=Value(o)) for g, o in Alerta.ORDEN_GRAVEDAD.items()],
                output_field=IntegerField())


def alertas_para(usuario, todas=False):
    """Alertas del hogar del usuario dirigidas a sus roles (o todas, si
    puede verlas), ordenadas por gravedad y antigüedad."""
    qs = Alerta.objects.filter(hogar=usuario.hogar).select_related('residente', 'atendida_por', 'creada_por')
    if not (todas and puede_ver_todas(usuario)):
        qs = qs.filter(Alerta.filtro_roles(roles_de(usuario)))
    return qs.annotate(_orden=orden_gravedad()).order_by('_orden', 'fecha_creacion')


def activas_para(usuario):
    return alertas_para(usuario).filter(estado__in=Alerta.ACTIVAS)


def marcar_vistas(usuario, alertas):
    ya = set(VistaAlerta.objects.filter(usuario=usuario, alerta__in=alertas).values_list('alerta_id', flat=True))
    VistaAlerta.objects.bulk_create(
        [VistaAlerta(alerta=a, usuario=usuario) for a in alertas if a.pk not in ya], ignore_conflicts=True,
    )
    return ya


@transaction.atomic
def atender(alerta, usuario, nota=''):
    alerta = Alerta.objects.select_for_update().get(pk=alerta.pk)
    if not alerta.activa:
        raise ValidationError('Esta alerta ya está cerrada.')
    if alerta.estado == Alerta.ATENDIDA:
        raise ValidationError('Esta alerta ya fue atendida.')
    if alerta.gravedad == Alerta.CRITICA and not nota.strip():
        raise ValidationError('Para una alerta crítica escriba qué se hizo.')
    alerta.estado = Alerta.ATENDIDA
    alerta.atendida_por = usuario
    alerta.fecha_atencion = timezone.now()
    alerta.nota_atencion = nota.strip()
    if alerta.origen == Alerta.MANUAL:
        alerta.vigente = False
        alerta.fecha_cierre = alerta.fecha_atencion
    alerta.save()
    return alerta


@transaction.atomic
def descartar(alerta, usuario, motivo):
    """'No aplica'. La alerta sigue vigente para el motor (no se vuelve a
    crear mientras exista la misma condición) pero sale de la bandeja."""
    if not motivo.strip():
        raise ValidationError('Escriba por qué no aplica.')
    alerta = Alerta.objects.select_for_update().get(pk=alerta.pk)
    if not alerta.activa:
        raise ValidationError('Esta alerta ya está cerrada.')
    alerta.estado = Alerta.DESCARTADA
    alerta.atendida_por = usuario
    alerta.fecha_atencion = timezone.now()
    alerta.nota_atencion = motivo.strip()
    alerta.fecha_cierre = alerta.fecha_atencion
    if alerta.origen == Alerta.MANUAL:
        alerta.vigente = False
    alerta.save()
    return alerta


def publicar_aviso(usuario, titulo, mensaje, gravedad, roles, horas, residente=None):
    if not roles:
        raise ValidationError('Elija al menos un rol.')
    return Alerta.objects.create(
        hogar=usuario.hogar, residente=residente, regla='aviso', clave=f'aviso:{uuid.uuid4().hex}',
        origen=Alerta.MANUAL, gravedad=gravedad, titulo=titulo.strip()[:200], mensaje=mensaje.strip(),
        roles_destino=Alerta.codificar_roles(roles), creada_por=usuario,
        vence=timezone.now() + timedelta(hours=horas),
        url_accion='', texto_accion='',
    )
