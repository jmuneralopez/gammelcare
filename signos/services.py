"""Rangos efectivos, interpretación, balance de líquidos y eliminación."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import parametros as P
from .models import ControlSignos, RangoResidente, RangosHogar, RegistroLiquidos

DEL_HOGAR = 'hogar'
DEL_RESIDENTE = 'residente'


def rangos_efectivos(residente):
    """{codigo: {'rango': {...}, 'origen': 'hogar'|'residente', 'regla': RangoResidente|None}}"""
    hogar = RangosHogar.para_hogar(residente.hogar)
    propios = {r.parametro: r for r in RangoResidente.objects.filter(residente=residente, activo=True)}
    efectivos = {}
    for codigo in P.CODIGOS:
        if codigo in propios:
            efectivos[codigo] = {'rango': propios[codigo].como_dict(), 'origen': DEL_RESIDENTE, 'regla': propios[codigo]}
        else:
            efectivos[codigo] = {'rango': hogar.rango(codigo), 'origen': DEL_HOGAR, 'regla': None}
    return efectivos


def interpretar_control(control, rangos=None):
    """{codigo: {'valor', 'interpretacion', 'parametro'}} solo de lo registrado."""
    rangos = rangos or rangos_efectivos(control.residente)
    salida = {}
    for codigo, valor in control.valores().items():
        salida[codigo] = {
            'valor': valor,
            'interpretacion': P.interpretar(valor, rangos[codigo]['rango']),
            'parametro': P.POR_CODIGO[codigo],
        }
    return salida


def hallazgos(control, rangos=None):
    """(criticos, fuera_de_rango) como listas de textos 'PAS 190 mmHg (crítico alto)'."""
    criticos, fuera = [], []
    for codigo, d in interpretar_control(control, rangos).items():
        if not P.fuera_de_rango(d['interpretacion']):
            continue
        p = d['parametro']
        texto = f'{p.corto} {d["valor"]:.{p.decimales}f} {p.unidad} ({P.ETIQUETAS[d["interpretacion"]].lower()})'
        (criticos if P.es_critico(d['interpretacion']) else fuera).append(texto)
    return criticos, fuera


def vigentes(qs):
    return qs.filter(anulado=False)


def ultimo_control(residente):
    return vigentes(ControlSignos.objects.filter(residente=residente)).order_by('-fecha_hora').first()


@transaction.atomic
def anular(registro, usuario, motivo):
    if not motivo.strip():
        raise ValueError('La anulación necesita un motivo.')
    registro = type(registro).objects.select_for_update().get(pk=registro.pk)
    if registro.anulado:
        raise ValueError('Ese registro ya estaba anulado.')
    registro.anular(usuario, motivo.strip())
    return registro


# ── Peso ────────────────────────────────────────────────────────────

def cambio_de_peso(residente, dias=30):
    """(peso_actual, peso_referencia, porcentaje) comparando el último peso
    con el primero registrado en los `dias` anteriores; None si no hay dos."""
    pesos = vigentes(ControlSignos.objects.filter(residente=residente, peso__isnull=False)).order_by('-fecha_hora')
    actual = pesos.first()
    if not actual:
        return None
    desde = actual.fecha_hora - timedelta(days=dias)
    referencia = pesos.filter(fecha_hora__gte=desde, fecha_hora__lt=actual.fecha_hora).order_by('fecha_hora').first()
    if not referencia or not referencia.peso:
        return None
    porcentaje = (actual.peso - referencia.peso) / referencia.peso * 100
    return actual, referencia, porcentaje


# ── Líquidos ────────────────────────────────────────────────────────

def balance(residente, desde, hasta):
    qs = vigentes(RegistroLiquidos.objects.filter(residente=residente, fecha_hora__gte=desde, fecha_hora__lt=hasta))
    ingresos = qs.filter(tipo=RegistroLiquidos.INGRESO).aggregate(t=Sum('cantidad_ml'))['t'] or 0
    egresos = qs.filter(tipo=RegistroLiquidos.EGRESO).aggregate(t=Sum('cantidad_ml'))['t'] or 0
    return {'ingresos': ingresos, 'egresos': egresos, 'balance': ingresos - egresos, 'registros': qs.count()}


def balance_del_dia(residente, fecha=None):
    fecha = fecha or timezone.localdate()
    inicio = timezone.make_aware(timezone.datetime.combine(fecha, timezone.datetime.min.time()))
    return balance(residente, inicio, inicio + timedelta(days=1))


# ── Eliminación (de las notas de enfermería) ────────────────────────

def _notas_enfermeria(residente):
    from notas_clinicas.models import NotaClinica
    return NotaClinica.objects.filter(residente=residente, tipo=NotaClinica.ENFERMERIA)


def eliminacion_por_dia(residente, dias=14):
    """Lista de los últimos `dias` días: {fecha, notas, diuresis, deposicion}
    según las casillas de las notas de enfermería (sí si al menos una nota
    del día la marcó)."""
    hoy = timezone.localdate()
    desde = hoy - timedelta(days=dias - 1)
    inicio = timezone.make_aware(timezone.datetime.combine(desde, timezone.datetime.min.time()))
    filas = {desde + timedelta(days=i): {'notas': 0, 'diuresis': False, 'deposicion': False} for i in range(dias)}
    for n in _notas_enfermeria(residente).filter(fecha_creacion__gte=inicio).only('fecha_creacion', 'diuresis', 'deposicion'):
        d = filas.get(timezone.localdate(n.fecha_creacion))
        if d is None:
            continue
        d['notas'] += 1
        d['diuresis'] |= n.diuresis
        d['deposicion'] |= n.deposicion
    return [{'fecha': f, **v} for f, v in sorted(filas.items())]


def ultima_eliminacion(residente, campo):
    """Fecha y hora de la última nota de enfermería con la casilla marcada."""
    nota = _notas_enfermeria(residente).filter(**{campo: True}).order_by('-fecha_creacion').first()
    return nota.fecha_creacion if nota else None


def dias_sin_deposicion(residente):
    """Días completos desde la última deposición registrada (o desde el
    ingreso del residente si nunca se ha registrado)."""
    referencia = ultima_eliminacion(residente, 'deposicion') or residente.fecha_ingreso
    return (timezone.localdate() - timezone.localdate(referencia)).days, referencia


def horas_sin_diuresis(residente):
    referencia = ultima_eliminacion(residente, 'diuresis') or residente.fecha_ingreso
    return int((timezone.now() - referencia).total_seconds() // 3600), referencia
