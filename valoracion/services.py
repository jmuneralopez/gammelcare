import calendar
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import escalas as E
from .models import ConfiguracionValoracion, Valoracion

# Días desde el ingreso para considerar vencida una escala exigida que nunca se aplicó.
DIAS_GRACIA_INGRESO = 15


def sumar_meses(fecha, meses):
    m = fecha.month - 1 + meses
    anio, mes = fecha.year + m // 12, m % 12 + 1
    return fecha.replace(year=anio, month=mes, day=min(fecha.day, calendar.monthrange(anio, mes)[1]))


def vigentes(residente, escala=None):
    qs = Valoracion.objects.filter(residente=residente, anulada=False)
    return qs.filter(escala=escala) if escala else qs


def registrar(residente, escala, usuario, fecha, respuestas=None, puntaje=None, educacion='',
              observaciones='', cuidador=''):
    """Crea la valoración calculando el puntaje (modo 'items') o tomando el
    puntaje digitado (modo 'puntaje')."""
    if escala.modo == 'items':
        puntos = {k: v['puntos'] for k, v in respuestas.items()}
        puntaje = E.calcular(escala, puntos, educacion or 'media')
    banda = escala.interpretar(puntaje)
    return Valoracion.objects.create(
        residente=residente, escala=escala.codigo, fecha=fecha, respuestas=respuestas or {},
        educacion=educacion, puntaje=puntaje, interpretacion=banda.texto, nivel=banda.nivel,
        observaciones=observaciones, cuidador_evaluado=cuidador, registrado_por=usuario,
    )


@transaction.atomic
def anular(valoracion, usuario, motivo):
    if not motivo.strip():
        raise ValueError('La anulación necesita un motivo.')
    v = Valoracion.objects.select_for_update().get(pk=valoracion.pk)
    if v.anulada:
        raise ValueError('Esa valoración ya estaba anulada.')
    v.anular(usuario, motivo.strip())
    return v


def cambio(escala, ultima, anterior):
    """Diferencia de puntaje expresada como mejoría (+) o empeoramiento (-)."""
    if not ultima or not anterior:
        return None
    dif = ultima.puntaje - anterior.puntaje
    return dif if escala.mayor_es_mejor else -dif


def estado_por_escala(residente, config=None):
    """Una fila por escala: última, anterior, cambio, próxima fecha, vencida."""
    config = config or ConfiguracionValoracion.para_hogar(residente.hogar)
    hoy = timezone.localdate()
    todas = list(vigentes(residente).order_by('-fecha', '-fecha_registro'))
    filas = []
    for e in E.ESCALAS:
        historial = [v for v in todas if v.escala == e.codigo]
        ultima = historial[0] if historial else None
        anterior = historial[1] if len(historial) > 1 else None
        meses = config.meses(e.codigo)
        proxima = sumar_meses(ultima.fecha, meses) if (ultima and meses) else None
        if ultima is None and meses:
            limite = timezone.localdate(residente.fecha_ingreso) + timedelta(days=DIAS_GRACIA_INGRESO)
            proxima = limite
        vencida = bool(meses and proxima and proxima < hoy)
        filas.append({
            'escala': e, 'ultima': ultima, 'anterior': anterior, 'historial': historial[:6],
            'cambio': cambio(e, ultima, anterior), 'meses': meses, 'exigida': meses > 0,
            'proxima': proxima, 'vencida': vencida, 'nunca': ultima is None,
        })
    return filas


def vencidas(residente, config=None):
    return [f for f in estado_por_escala(residente, config) if f['vencida']]
