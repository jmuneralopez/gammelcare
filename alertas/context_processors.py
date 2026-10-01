"""Campana de alertas en la barra superior y franja roja de críticas."""
import logging

from django.conf import settings

log = logging.getLogger(__name__)


def alertas(request):
    usuario = getattr(request, 'user', None)
    if not usuario or not usuario.is_authenticated or not usuario.hogar_id:
        return {}
    try:
        from .models import Alerta
        from .motor import evaluar_si_toca
        from .services import activas_para
        if getattr(settings, 'ALERTAS_EVALUACION_PEREZOSA', True):
            evaluar_si_toca(usuario.hogar)
        activas = activas_para(usuario)
        nuevas = activas.filter(estado=Alerta.NUEVA)
        primeras = list(activas[:5])
        criticas = list(nuevas.filter(gravedad=Alerta.CRITICA)[:3])
        total = nuevas.count()
        peor = min((Alerta.ORDEN_GRAVEDAD[g] for g in nuevas.values_list('gravedad', flat=True).distinct()), default=None)
    except Exception:  # noqa: BLE001 — la campana nunca debe tumbar una página
        log.exception('No se pudo calcular la campana de alertas')
        return {}
    color = {0: 'danger', 1: 'warning', 2: 'primary', 3: 'secondary'}.get(peor, 'secondary')
    return {
        'alertas_campana': {'total': total, 'primeras': primeras, 'color': color},
        'alertas_criticas': criticas,
    }
