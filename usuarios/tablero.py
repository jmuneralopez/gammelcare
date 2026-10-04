"""Pantalla de inicio por rol.

Cada rol ve lo que tiene que resolver hoy: un número con el enlace a la
pantalla donde se resuelve. Muchos números salen de las alertas vigentes
(las mismas reglas que ya avisan), para que el inicio y la campana nunca
digan cosas distintas. Si un usuario tiene varios roles, ve la unión de
las secciones, sin repetir.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.urls import reverse
from django.utils import timezone

from usuarios.models import Rol


@dataclass
class Tarjeta:
    titulo: str
    valor: object
    url: str
    icono: str = 'bi-circle'
    color: str = 'primary'      # danger / warning / primary / success / secondary
    detalle: str = ''


@dataclass
class Seccion:
    titulo: str
    tarjetas: list = field(default_factory=list)
    lista: list = field(default_factory=list)       # filas extra (p. ej. citas de hoy)
    lista_titulo: str = ''
    lista_vacia: str = ''


def _color(valor, alto='danger', medio=None):
    if not valor:
        return 'success'
    return alto if medio is None else medio


def _alertas(usuario):
    from alertas.models import Alerta
    from alertas.services import activas_para
    return activas_para(usuario), Alerta


def _por_regla(activas, *reglas):
    return activas.filter(regla__in=reglas).count()


def _url_alertas(*reglas):
    return reverse('alertas_bandeja') + '?regla=' + ','.join(reglas)


def _citas_de(hogar, desde, hasta):
    from citas.models import Cita
    return (Cita.objects.filter(residente__hogar=hogar, residente__activo=True, estado=Cita.PROGRAMADA,
                                fecha_hora__gte=desde, fecha_hora__lt=hasta)
            .select_related('residente').order_by('fecha_hora'))


def _hoy_en_el_hogar(usuario, activas, Alerta):
    from residentes.models import Residente
    hogar = usuario.hogar
    tz = timezone.get_current_timezone()
    hoy = timezone.localdate()
    inicio = timezone.make_aware(datetime.combine(hoy, time.min), tz)
    citas_hoy = list(_citas_de(hogar, inicio, inicio + timedelta(days=1)))
    criticas = activas.filter(gravedad=Alerta.CRITICA).count()
    nuevas = activas.filter(estado=Alerta.NUEVA).count()
    s = Seccion('Hoy en el hogar', [
        Tarjeta('Residentes activos', Residente.objects.filter(hogar=hogar, activo=True).count(),
                reverse('atencion_lista') if usuario.es_clinico() else reverse('residente_lista'),
                'bi-people', 'primary'),
        Tarjeta('Alertas críticas para usted', criticas, reverse('alertas_bandeja') + '?gravedad=critica',
                'bi-exclamation-octagon', _color(criticas)),
        Tarjeta('Alertas nuevas para usted', nuevas, reverse('alertas_bandeja'), 'bi-bell',
                _color(nuevas, 'warning')),
        Tarjeta('Citas médicas de hoy', len(citas_hoy), reverse('citas_agenda'), 'bi-calendar2-week',
                'primary' if citas_hoy else 'secondary'),
    ], lista_titulo='Citas de hoy', lista_vacia='No hay citas hoy.')
    s.lista = [{
        'hora': timezone.localtime(c.fecha_hora).strftime('%H:%M'), 'texto': f'{c.nombre_residente} — {c.titulo}',
        'detalle': ', '.join(filter(None, [c.lugar, 'en ayunas' if c.requiere_ayuno else '',
                                           c.get_transporte_display().lower() if c.transporte != c.POR_DEFINIR else ''])),
        'url': reverse('cita_detalle', args=[c.pk]),
    } for c in citas_hoy]
    return s


def _enfermeria(usuario, activas):
    from cuidados import services as cs
    from cuidados.models import Herida
    from medicamentos import services as ms
    from nutricion import services as ns
    from nutricion.models import ConfiguracionNutricion, NOMBRE_COMIDA, RegistroIngesta
    from residentes.models import Residente
    hogar = usuario.hogar
    _, turno, _, _ = cs.turno_actual()
    residentes = list(Residente.objects.filter(hogar=hogar, activo=True))
    atrasadas = sum(ms.tomas_de_hoy(r)['atrasadas'] for r in residentes)
    config = ConfiguracionNutricion.para_hogar(hogar)
    comida = ns.comida_actual(config)
    con_registro = set(RegistroIngesta.objects.filter(residente__hogar=hogar, fecha=timezone.localdate(),
                                                       comida=comida, anulado=False).values_list('residente_id', flat=True))
    sin_comida = sum(1 for r in residentes if r.pk not in con_registro) if comida else 0
    hoy = timezone.localdate()
    curaciones = 0
    for h in Herida.objects.filter(residente__hogar=hogar, residente__activo=True, estado=Herida.ACTIVA):
        s = h.ultimo_seguimiento()
        if s is None or (s.proxima_curacion and s.proxima_curacion <= hoy):
            curaciones += 1
    posicion = _por_regla(activas, 'posicion_atrasada')
    signos = _por_regla(activas, 'sin_control_signos')
    from eventos import services as es
    vigilancias = es.vigilancias_pendientes(hogar).count()
    return Seccion(f'Turno de la {turno.lower()}', [
        Tarjeta('Tomas de medicamentos atrasadas', atrasadas,
                reverse('ronda') if usuario.tiene_rol(*Rol.ROLES_RONDA) else reverse('atencion_lista'),
                'bi-capsule', _color(atrasadas), 'Hoy, sin registrar'),
        Tarjeta('Cambios de posición atrasados', posicion, reverse('cuidados_planilla') + '?ver=pendientes',
                'bi-arrow-left-right', _color(posicion)),
        Tarjeta(f'{NOMBRE_COMIDA.get(comida, "Comida")}: sin registrar', sin_comida,
                reverse('nutricion_planilla') + (f'?comida={comida}' if comida else ''), 'bi-cup-hot',
                _color(sin_comida, 'warning')),
        Tarjeta('Curaciones de hoy o vencidas', curaciones, reverse('cuidados_heridas'), 'bi-bandaid',
                _color(curaciones, 'warning')),
        Tarjeta('Residentes sin signos en 24 horas', signos, reverse('signos_tablero'), 'bi-heart-pulse',
                _color(signos, 'warning')),
        Tarjeta('Revisiones después de caídas pendientes', vigilancias, reverse('eventos_bandeja'), 'bi-eye',
                _color(vigilancias)),
    ])


def _medico(usuario, activas):
    from eventos.models import EventoAdverso
    from examenes.models import Examen
    por_analizar = EventoAdverso.objects.filter(hogar=usuario.hogar, estado=EventoAdverso.ABIERTO).count()
    por_revisar = Examen.objects.filter(residente__hogar=usuario.hogar, residente__activo=True,
                                        estado=Examen.RESULTADO).count()
    t = [
        Tarjeta('Exámenes por revisar', por_revisar, reverse('examenes_bandeja'), 'bi-clipboard2-data',
                _color(por_revisar, 'warning')),
        Tarjeta('Eventos adversos por analizar', por_analizar, reverse('eventos_bandeja'), 'bi-exclamation-diamond',
                _color(por_analizar, 'warning')),
    ]
    for titulo, reglas, url, icono, color in (
        ('Signos vitales críticos', ('signo_critico',), None, 'bi-heart-pulse', 'danger'),
        ('Heridas con signos de infección', ('herida_infeccion',), None, 'bi-bandaid', 'danger'),
        ('Escalas por aplicar o repetir', ('valoracion_vencida',), reverse('valoracion_tablero'), 'bi-clipboard2-pulse', 'warning'),
        ('Planes de atención faltantes o por revisar', ('plan_atencion',), reverse('plan_tablero'), 'bi-journal-check', 'warning'),
        ('Órdenes médicas por terminar', ('orden_por_terminar',), None, 'bi-capsule', 'warning'),
    ):
        n = _por_regla(activas, *reglas)
        t.append(Tarjeta(titulo, n, url or _url_alertas(*reglas), icono, _color(n, color)))
    return Seccion('Seguimiento médico', t)


def _nutricion(usuario, activas):
    t = []
    for titulo, reglas, url, icono, color in (
        ('Comen la mitad o menos', ('ingesta_baja',), None, 'bi-cup-hot', 'danger'),
        ('Con pérdida de peso', ('perdida_peso',), None, 'bi-graph-down-arrow', 'danger'),
        ('Pocos líquidos o por encima del máximo', ('liquidos_insuficientes',), None, 'bi-droplet', 'warning'),
        ('Sin dieta indicada', ('sin_dieta',), reverse('nutricion_cocina'), 'bi-egg-fried', 'warning'),
    ):
        n = _por_regla(activas, *reglas)
        t.append(Tarjeta(titulo, n, url or _url_alertas(*reglas), icono, _color(n, color)))
    return Seccion('Nutrición', t)


def _administracion(usuario, activas):
    from cuidados.models import Herida
    from infraestructura.models import Cama
    from residentes.models import Residente
    from usuarios.models import Usuario
    hogar = usuario.hogar
    hoy = timezone.localdate()
    camas = Cama.objects.filter(habitacion__departamento__hogar=hogar, activo=True)
    total, ocupadas = camas.count(), camas.filter(estado='ocupada').count()
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(hoy, time.min), tz)
    semana = _citas_de(hogar, inicio, inicio + timedelta(days=7)).count()
    lotes = _por_regla(activas, 'lote_vencido', 'lote_por_vencer')
    prestamos = _por_regla(activas, 'prestamo_sin_reponer')
    from eventos.models import CAIDA, EventoAdverso
    caidas_mes = EventoAdverso.objects.filter(hogar=hogar, tipo=CAIDA, fecha_hora__year=hoy.year,
                                              fecha_hora__month=hoy.month).count()
    lpp_mes = Herida.objects.filter(residente__hogar=hogar, tipo=Herida.LPP, origen='hogar',
                                    fecha_deteccion__year=hoy.year, fecha_deteccion__month=hoy.month).count()
    ingresos = Residente.objects.filter(hogar=hogar, fecha_ingreso__year=hoy.year,
                                        fecha_ingreso__month=hoy.month).count()
    return Seccion('Gestión del hogar', [
        Tarjeta('Camas ocupadas', f'{ocupadas} de {total}', reverse('institucion'), 'bi-hospital', 'primary',
                f'{round(100 * ocupadas / total) if total else 0} % de ocupación · {total - ocupadas} libres'),
        Tarjeta('Ingresos este mes', ingresos, reverse('residente_lista') if usuario.es_administrador_hogar()
                else reverse('atencion_lista'), 'bi-door-open', 'primary'),
        Tarjeta('Lotes vencidos o por vencer', lotes, reverse('vencimientos'), 'bi-hourglass-split',
                _color(lotes, 'warning')),
        Tarjeta('Préstamos del botiquín sin reponer', prestamos, reverse('botiquin_lista') + '#prestamos',
                'bi-arrow-repeat', _color(prestamos, 'warning')),
        Tarjeta('Citas de los próximos 7 días', semana, reverse('citas_agenda'), 'bi-calendar2-week', 'primary'),
        Tarjeta('Lesiones por presión aparecidas en el hogar este mes', lpp_mes, reverse('cuidados_heridas'),
                'bi-bandaid', _color(lpp_mes)),
        Tarjeta('Caídas este mes', caidas_mes, reverse('eventos_indicadores'), 'bi-exclamation-diamond', _color(caidas_mes)),
        Tarjeta('Usuarios activos', Usuario.objects.filter(hogar=hogar, activo=True).count(),
                reverse('usuario_lista'), 'bi-person-badge', 'secondary'),
    ])


def secciones(usuario):
    if not usuario.hogar_id:
        return []
    activas, Alerta = _alertas(usuario)
    salida = [_hoy_en_el_hogar(usuario, activas, Alerta)]
    if usuario.tiene_rol(Rol.JEFE_ENFERMERIA, Rol.ENFERMERO):
        salida.append(_enfermeria(usuario, activas))
    if usuario.tiene_rol(Rol.MEDICO, Rol.JEFE_ENFERMERIA):
        salida.append(_medico(usuario, activas))
    if usuario.tiene_rol(Rol.NUTRICIONISTA, Rol.MEDICO):
        salida.append(_nutricion(usuario, activas))
    if usuario.tiene_rol(Rol.ADMINISTRADOR):
        salida.append(_administracion(usuario, activas))
    return salida
