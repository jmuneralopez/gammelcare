"""Motor de alertas: evalúa las reglas y sincroniza las alertas vigentes.

Se ejecuta:
- cada 15 minutos con `python manage.py evaluar_alertas` (tarea programada);
- de forma perezosa cuando alguien abre una página y la última evaluación
  del hogar tiene más de EVALUACION_CADA_MIN minutos (por si la tarea
  programada no está corriendo);
- de inmediato, solo para el residente y las reglas afectadas, cuando se
  guarda un registro relevante (ver signals.py).
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Alerta, ConfiguracionAlertas
from .reglas import REGLAS

log = logging.getLogger(__name__)

EVALUACION_CADA_MIN = 5


def _sincronizar(hogar, codigo, candidatos, residente=None):
    existentes = Alerta.objects.filter(hogar=hogar, regla=codigo, vigente=True, origen=Alerta.SISTEMA)
    if residente is not None:
        existentes = existentes.filter(residente=residente)
    existentes = {a.clave: a for a in existentes}
    vistas = set()
    creadas = 0
    for c in candidatos:
        if c.clave in vistas:
            continue
        vistas.add(c.clave)
        alerta = existentes.get(c.clave)
        campos = dict(
            gravedad=c.gravedad, titulo=c.titulo[:200], mensaje=c.mensaje, url_accion=c.url,
            texto_accion=c.texto_accion[:60], roles_destino=Alerta.codificar_roles(c.roles),
        )
        if alerta is None:
            Alerta.objects.create(hogar=hogar, residente=c.residente, regla=codigo, clave=c.clave, **campos)
            creadas += 1
            continue
        cambios = [k for k, v in campos.items() if getattr(alerta, k) != v]
        if cambios:
            sube = Alerta.ORDEN_GRAVEDAD[c.gravedad] < Alerta.ORDEN_GRAVEDAD[alerta.gravedad]
            for k in cambios:
                setattr(alerta, k, campos[k])
            if sube and alerta.estado == Alerta.ATENDIDA:
                alerta.estado = Alerta.NUEVA  # empeoró: vuelve a pedir atención
                cambios.append('estado')
            alerta.save(update_fields=cambios + ['fecha_actualizacion'])
    ahora = timezone.now()
    resueltas = 0
    for clave, alerta in existentes.items():
        if clave in vistas:
            continue
        alerta.vigente = False
        if alerta.estado in Alerta.ACTIVAS:
            alerta.estado = Alerta.RESUELTA
            alerta.fecha_cierre = ahora
        alerta.save(update_fields=['vigente', 'estado', 'fecha_cierre', 'fecha_actualizacion'])
        resueltas += 1
    return creadas, resueltas


def vencer_avisos(hogar):
    ahora = timezone.now()
    return Alerta.objects.filter(
        hogar=hogar, origen=Alerta.MANUAL, vigente=True, vence__lt=ahora,
    ).update(vigente=False, estado=Alerta.VENCIDA, fecha_cierre=ahora)


def evaluar_hogar(hogar, reglas=None, residente=None):
    """Evalúa las reglas (todas o las indicadas) para el hogar o para un
    residente. Una regla que falla no detiene a las demás."""
    config = ConfiguracionAlertas.para_hogar(hogar)
    resumen = {}
    for codigo, (funcion, _nombre) in REGLAS.items():
        if reglas is not None and codigo not in reglas:
            continue
        try:
            with transaction.atomic():
                if config.regla_activa(codigo):
                    candidatos = list(funcion(hogar, config, residente=residente))
                else:
                    candidatos = []  # desactivada: cierra lo que hubiera
                resumen[codigo] = _sincronizar(hogar, codigo, candidatos, residente=residente)
        except Exception:  # noqa: BLE001 — una regla rota no debe tumbar las páginas
            log.exception('Falló la regla de alertas %s en el hogar %s', codigo, hogar.pk)
    if reglas is None and residente is None:
        vencer_avisos(hogar)
        ConfiguracionAlertas.objects.filter(pk=config.pk).update(ultima_evaluacion=timezone.now())
    return resumen


def evaluar_si_toca(hogar):
    """Evaluación perezosa: solo si la última tiene más de
    EVALUACION_CADA_MIN minutos. El UPDATE condicional evita que dos
    peticiones simultáneas evalúen a la vez."""
    config = ConfiguracionAlertas.para_hogar(hogar)
    limite = timezone.now() - timedelta(minutes=EVALUACION_CADA_MIN)
    tomado = ConfiguracionAlertas.objects.filter(pk=config.pk).filter(
        ultima_evaluacion__isnull=True,
    ).update(ultima_evaluacion=timezone.now()) or ConfiguracionAlertas.objects.filter(
        pk=config.pk, ultima_evaluacion__lt=limite,
    ).update(ultima_evaluacion=timezone.now())
    if tomado:
        evaluar_hogar(hogar)
        return True
    return False
