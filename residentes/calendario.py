"""Calendario del residente y agenda del hogar.

Reúne en un solo lugar lo que pasó y lo que viene, sacado de cada módulo:
notas, citas, exámenes, órdenes médicas, escalas de valoración, plan de
atención, heridas y curaciones, dieta e ingreso. Cada evento pertenece a
una "capa" que se puede encender o apagar en pantalla.
"""
from dataclasses import dataclass
from datetime import date, datetime, time

from django.urls import reverse
from django.utils import timezone

CAPAS = [
    ('notas', 'Notas clínicas', '#2E75B6'),
    ('citas', 'Citas médicas', '#0B7285'),
    ('examenes', 'Exámenes', '#6f42c1'),
    ('medicamentos', 'Órdenes médicas', '#B35C00'),
    ('valoracion', 'Valoración geriátrica', '#198754'),
    ('plan', 'Plan de atención', '#1F4E79'),
    ('heridas', 'Heridas y curaciones', '#B42318'),
    ('dieta', 'Dieta', '#C2410C'),
    ('ingreso', 'Ingreso', '#495057'),
]
COLOR = {c: col for c, _, col in CAPAS}
NOMBRE_CAPA = {c: n for c, n, _ in CAPAS}
CAPAS_AGENDA = ['citas', 'plan', 'valoracion', 'heridas', 'medicamentos']


@dataclass
class Evento:
    capa: str
    titulo: str
    inicio: object          # datetime (con hora) o date (todo el día)
    url: str = ''
    detalle: str = ''
    pendiente: bool = False  # algo que está por hacerse
    residente: object = None

    @property
    def todo_el_dia(self):
        return not isinstance(self.inicio, datetime)

    @property
    def fecha(self):
        return timezone.localdate(self.inicio) if isinstance(self.inicio, datetime) else self.inicio

    @property
    def hora(self):
        return '' if self.todo_el_dia else timezone.localtime(self.inicio).strftime('%H:%M')

    def para_calendario(self):
        color = COLOR.get(self.capa, '#2E75B6')
        e = {
            'title': self.titulo,
            'start': (timezone.localtime(self.inicio).isoformat() if not self.todo_el_dia else self.inicio.isoformat()),
            'allDay': self.todo_el_dia,
            'color': color if not self.pendiente else '#ffffff',
            'textColor': '#ffffff' if not self.pendiente else color,
            'borderColor': color,
            'extendedProps': {'capa': self.capa, 'nombre_capa': NOMBRE_CAPA.get(self.capa, ''), 'url': self.url,
                              'detalle': self.detalle, 'pendiente': self.pendiente},
        }
        return e


def _en_rango(valor, desde, hasta):
    f = timezone.localdate(valor) if isinstance(valor, datetime) else valor
    return f is not None and desde <= f <= hasta


def _dt_rango(desde, hasta):
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(desde, time.min), tz),
            timezone.make_aware(datetime.combine(hasta, time.max), tz))


# ── Fuentes por capa (para un queryset de residentes) ───────────────

def _citas(residentes, desde, hasta):
    from citas.models import Cita
    ini, fin = _dt_rango(desde, hasta)
    hoy = timezone.now()
    for c in Cita.objects.filter(residente__in=residentes, fecha_hora__range=(ini, fin)) \
            .exclude(estado=Cita.REPROGRAMADA).select_related('residente'):
        estado = 'sin registrar qué pasó' if c.vencida_sin_cierre else c.get_estado_display().lower()
        yield Evento('citas', f'Cita: {c.titulo}', c.fecha_hora, reverse('cita_detalle', args=[c.pk]),
                     f'{c.lugar} · {estado}', pendiente=c.abierta and c.fecha_hora >= hoy, residente=c.residente)


def _examenes(residentes, desde, hasta):
    from examenes.models import Examen
    for e in Examen.objects.filter(residente__in=residentes).exclude(estado=Examen.CANCELADO).select_related('residente'):
        fecha = e.fecha_toma or e.fecha_orden
        if _en_rango(fecha, desde, hasta):
            yield Evento('examenes', f'Examen: {e.nombre}', fecha, reverse('examen_detalle', args=[e.pk]),
                         e.get_estado_display(), pendiente=e.estado == Examen.PENDIENTE, residente=e.residente)


def _medicamentos(residentes, desde, hasta):
    from medicamentos.models import Prescripcion
    hoy = timezone.localdate()
    for p in Prescripcion.objects.filter(residente__in=residentes).select_related('medicamento', 'residente'):
        url = reverse('tratamiento_detalle', args=[p.pk])
        if _en_rango(p.fecha_inicio, desde, hasta):
            yield Evento('medicamentos', f'Inicia: {p.medicamento}', p.fecha_inicio, url, residente=p.residente)
        if p.fecha_fin and _en_rango(p.fecha_fin, desde, hasta):
            yield Evento('medicamentos', f'Termina: {p.medicamento}', p.fecha_fin, url,
                         pendiente=p.fecha_fin >= hoy and p.estado == Prescripcion.ACTIVA, residente=p.residente)


def _valoracion(residentes, desde, hasta):
    from valoracion import services as vs
    from valoracion.models import ConfiguracionValoracion, Valoracion
    for v in Valoracion.objects.filter(residente__in=residentes, anulada=False, fecha__range=(desde, hasta)) \
            .select_related('residente'):
        yield Evento('valoracion', f'{v.definicion.corto}: {v.puntaje} — {v.interpretacion}', v.fecha,
                     reverse('valoracion_detalle', args=[v.pk]), residente=v.residente)
    hoy = timezone.localdate()
    configs = {}
    for r in residentes:
        cv = configs.setdefault(r.hogar_id, ConfiguracionValoracion.para_hogar(r.hogar))
        for f in vs.estado_por_escala(r, cv):
            prox = f['proxima']
            if not (prox and f['exigida']):
                continue
            fecha = hoy if prox < hoy else prox  # una escala vencida se muestra hoy
            if _en_rango(fecha, desde, hasta):
                yield Evento('valoracion', f'Por aplicar: {f["escala"].corto}' + (' (vencida)' if f['vencida'] else ''),
                             fecha, reverse('valoracion_aplicar', args=[r.pk, f['escala'].codigo]),
                             pendiente=True, residente=r)


def _plan(residentes, desde, hasta):
    from plan_atencion.models import PlanAtencion
    hoy = timezone.localdate()
    for p in PlanAtencion.objects.filter(residente__in=residentes).exclude(estado=PlanAtencion.BORRADOR) \
            .select_related('residente'):
        url = reverse('plan_detalle', args=[p.pk])
        if p.fecha_activacion and _en_rango(p.fecha_activacion, desde, hasta):
            yield Evento('plan', f'Plan de atención v{p.version} activado', p.fecha_activacion, url, residente=p.residente)
        fecha = max(p.fecha_revision, hoy)  # una revisión vencida se muestra hoy
        if p.estado == PlanAtencion.VIGENTE and _en_rango(fecha, desde, hasta):
            yield Evento('plan', 'Revisión del plan de atención' + (' (vencida)' if p.fecha_revision < hoy else ''),
                         fecha, url, pendiente=True, residente=p.residente)


def _heridas(residentes, desde, hasta):
    from cuidados.models import Herida, SeguimientoHerida
    hoy = timezone.localdate()
    for h in Herida.objects.filter(residente__in=residentes).select_related('residente'):
        url = reverse('cuidados_herida_detalle', args=[h.pk])
        if _en_rango(h.fecha_deteccion, desde, hasta):
            yield Evento('heridas', f'Herida detectada: {h.nombre}', h.fecha_deteccion, url, residente=h.residente)
        if h.fecha_cierre and _en_rango(h.fecha_cierre, desde, hasta):
            yield Evento('heridas', f'Herida cerrada: {h.nombre}', h.fecha_cierre, url,
                         h.get_motivo_cierre_display(), residente=h.residente)
    ini, fin = _dt_rango(desde, hasta)
    ultimos = {}
    for s in SeguimientoHerida.objects.filter(herida__residente__in=residentes, anulado=False) \
            .select_related('herida__residente').order_by('fecha_hora'):
        if ini <= s.fecha_hora <= fin:
            yield Evento('heridas', f'Curación: {s.herida.nombre}', s.fecha_hora,
                         reverse('cuidados_herida_detalle', args=[s.herida_id]), s.curacion[:120],
                         residente=s.herida.residente)
        ultimos[s.herida_id] = s
    for s in ultimos.values():
        if not (s.herida.activa and s.proxima_curacion):
            continue
        fecha = max(s.proxima_curacion, hoy)
        if _en_rango(fecha, desde, hasta):
            yield Evento('heridas', f'Próxima curación: {s.herida.nombre}' + (' (vencida)' if s.proxima_curacion < hoy else ''),
                         fecha, reverse('cuidados_seguimiento_crear', args=[s.herida_id]),
                         pendiente=True, residente=s.herida.residente)


def _dieta(residentes, desde, hasta):
    from nutricion.models import DietaResidente
    ini, fin = _dt_rango(desde, hasta)
    for d in DietaResidente.objects.filter(residente__in=residentes, fecha_inicio__range=(ini, fin)) \
            .select_related('tipo', 'residente'):
        yield Evento('dieta', f'Dieta: {d.resumen}', d.fecha_inicio, reverse('nutricion_residente', args=[d.residente_id]),
                     residente=d.residente)


def _notas(residentes, desde, hasta, filtro=None):
    from notas_clinicas.models import NotaClinica
    ini, fin = _dt_rango(desde, hasta)
    qs = filtro if filtro is not None else NotaClinica.objects.filter(residente__in=residentes)
    tipos = dict(NotaClinica.TIPOS)
    for n in qs.filter(fecha_creacion__range=(ini, fin)).select_related('autor', 'residente'):
        yield Evento('notas', tipos.get(n.tipo, 'Nota'), n.fecha_creacion, reverse('nota_detalle', args=[n.pk]),
                     n.autor.get_full_name() or n.autor.username, residente=n.residente)


def _ingreso(residentes, desde, hasta):
    for r in residentes:
        if r.fecha_ingreso and _en_rango(r.fecha_ingreso, desde, hasta):
            yield Evento('ingreso', 'Ingreso al hogar', r.fecha_ingreso, reverse('residente_detalle', args=[r.pk]),
                         residente=r)


FUENTES = {
    'citas': _citas, 'examenes': _examenes, 'medicamentos': _medicamentos, 'valoracion': _valoracion,
    'plan': _plan, 'heridas': _heridas, 'dieta': _dieta, 'ingreso': _ingreso,
}


def eventos_residente(residente, desde, hasta, capas, notas_qs=None):
    salida = []
    for capa in capas:
        if capa == 'notas':
            salida.extend(_notas([residente], desde, hasta, notas_qs))
        elif capa in FUENTES:
            salida.extend(FUENTES[capa]([residente], desde, hasta))
    return salida


def agenda_hogar(hogar, desde, hasta, capas):
    """Lo que viene para todos los residentes activos (sin notas)."""
    from residentes.models import Residente
    residentes = list(Residente.objects.filter(hogar=hogar, activo=True))
    salida = []
    for capa in capas:
        if capa in FUENTES and capa != 'ingreso':
            salida.extend(e for e in FUENTES[capa](residentes, desde, hasta) if e.pendiente)
    salida.sort(key=lambda e: (e.fecha, e.hora or '00:00'))
    return salida


def parse_fecha(valor, defecto):
    """FullCalendar envía fechas ISO con hora y zona; se usa solo la fecha."""
    if not valor:
        return defecto
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return defecto
