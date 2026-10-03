"""Consultas y reglas de negocio de nutrición e hidratación."""
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import NOMBRE_COMIDA, ConfiguracionNutricion, DietaResidente, RegistroIngesta

DIAS_SIN_DIETA = 3


def dieta_vigente(residente):
    return (DietaResidente.objects.filter(residente=residente, vigente=True).select_related('tipo').first())


@transaction.atomic
def cambiar_dieta(residente, dieta_nueva, usuario):
    """Cierra la dieta vigente (queda en el historial) y activa la nueva."""
    ahora = timezone.now()
    DietaResidente.objects.filter(residente=residente, vigente=True).update(vigente=False, fecha_fin=ahora)
    dieta_nueva.residente = residente
    dieta_nueva.registrado_por = usuario
    dieta_nueva.fecha_inicio = ahora
    dieta_nueva.vigente = True
    dieta_nueva.pk = None
    dieta_nueva.save()
    return dieta_nueva


def alergias_alimentarias(residente):
    from antecedentes.models import Alergia
    return list(residente.alergias.filter(activo=True, tipo__in=[Alergia.ALIMENTO, Alergia.OTRA]))


def meta_liquidos(residente, dieta=None, config=None):
    dieta = dieta if dieta is not None else dieta_vigente(residente)
    if dieta and dieta.meta_liquidos_ml:
        meta = dieta.meta_liquidos_ml
    else:
        meta = (config or ConfiguracionNutricion.para_hogar(residente.hogar)).meta_liquidos_ml
    if dieta and dieta.restriccion_liquidos_ml:
        meta = min(meta, dieta.restriccion_liquidos_ml)
    return meta


def _inicio_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min), timezone.get_current_timezone())


def liquidos_orales(residente, desde, hasta):
    from signos.models import RegistroLiquidos
    return (RegistroLiquidos.objects
            .filter(residente=residente, anulado=False, tipo=RegistroLiquidos.INGRESO, via='oral',
                    fecha_hora__gte=desde, fecha_hora__lt=hasta)
            .aggregate(t=Sum('cantidad_ml'))['t'] or 0)


def liquidos_del_dia(residente, fecha=None):
    inicio = _inicio_dia(fecha or timezone.localdate())
    return liquidos_orales(residente, inicio, inicio + timedelta(days=1))


def registrar_vaso(residente, usuario, cantidad_ml):
    from signos.models import RegistroLiquidos
    return RegistroLiquidos.objects.create(residente=residente, tipo=RegistroLiquidos.INGRESO, via='oral',
                                           cantidad_ml=cantidad_ml, registrado_por=usuario,
                                           observaciones='Registrado desde Nutrición (+1 vaso)')


def comida_actual(config, ahora=None):
    """La comida cuya hora es la más cercana (hacia atrás) a la hora actual."""
    ahora = timezone.localtime(ahora or timezone.now())
    comidas = config.comidas()
    if not comidas:
        return None
    minutos = ahora.hour * 60 + ahora.minute
    actual = comidas[0][0]
    for codigo, _, hora in comidas:
        h, m = (int(x) for x in hora.split(':'))
        if minutos >= h * 60 + m - 30:  # desde media hora antes de servirla
            actual = codigo
    return actual


def ingestas(residente, desde, hasta):
    return RegistroIngesta.objects.filter(residente=residente, anulado=False, fecha__gte=desde, fecha__lte=hasta)


@transaction.atomic
def registrar_ingesta(residente, fecha, comida, consumo, usuario, observaciones='', motivo_correccion=''):
    """Registra cuánto comió. Si ya había un registro de esa comida, lo anula
    (queda en el historial) y deja el nuevo."""
    if comida not in NOMBRE_COMIDA:
        raise ValueError('Comida no válida.')
    if consumo not in RegistroIngesta.PORCENTAJE:
        raise ValueError('Opción no válida.')
    if fecha > timezone.localdate():
        raise ValueError('No se registra la ingesta de un día futuro.')
    anterior = (RegistroIngesta.objects.select_for_update()
                .filter(residente=residente, fecha=fecha, comida=comida, anulado=False).first())
    if anterior:
        anterior.anular(usuario, motivo_correccion or f'Corregido: antes "{anterior.get_consumo_display()}"')
    return RegistroIngesta.objects.create(residente=residente, fecha=fecha, comida=comida, consumo=consumo,
                                          observaciones=observaciones, registrado_por=usuario)


def promedio(registros):
    valores = [r.porcentaje for r in registros if r.porcentaje is not None]
    return round(sum(valores) / len(valores)) if valores else None


def ultimas_comidas(residente, cantidad):
    """Las últimas `cantidad` comidas registradas en las que estaba presente."""
    orden = {c: i for i, c in enumerate(NOMBRE_COMIDA)}
    regs = list(RegistroIngesta.objects.filter(residente=residente, anulado=False)
                .exclude(consumo=RegistroIngesta.AUSENTE).order_by('-fecha')[:cantidad * 3])
    regs.sort(key=lambda r: (r.fecha, orden.get(r.comida, 0)), reverse=True)
    return regs[:cantidad]


def cuadricula(residente, config, dias=7):
    """Últimos `dias` días: una fila por día con la ingesta de cada comida,
    el promedio del día y los líquidos orales."""
    hoy = timezone.localdate()
    desde = hoy - timedelta(days=dias - 1)
    regs = {(r.fecha, r.comida): r for r in ingestas(residente, desde, hoy)}
    filas = []
    for i in range(dias):
        f = hoy - timedelta(days=i)
        celdas = [regs.get((f, c)) for c, _, _ in config.comidas()]
        filas.append({'fecha': f, 'celdas': celdas, 'promedio': promedio([c for c in celdas if c]),
                      'liquidos': liquidos_del_dia(residente, f)})
    return filas


def planilla(hogar, fecha, comida, config):
    from residentes.models import Residente
    residentes = (Residente.objects.filter(hogar=hogar, activo=True)
                  .select_related('cama_actual__habitacion__departamento')
                  .order_by('cama_actual__habitacion__departamento__nombre', 'cama_actual__habitacion__numero',
                            'cama_actual__codigo'))
    regs_dia = {}
    for r in RegistroIngesta.objects.filter(residente__hogar=hogar, fecha=fecha, anulado=False):
        regs_dia.setdefault(r.residente_id, {})[r.comida] = r
    filas = []
    for r in residentes:
        dieta = dieta_vigente(r)
        del_dia = regs_dia.get(r.pk, {})
        filas.append({
            'residente': r, 'nombre': r.get_nombre(), 'dieta': dieta,
            'alergias': alergias_alimentarias(r),
            'registro': del_dia.get(comida),
            'dia': [(c, n, del_dia.get(c)) for c, n, _ in config.comidas()],
            'liquidos': liquidos_del_dia(r, fecha), 'meta': meta_liquidos(r, dieta, config),
        })
    return filas


def lista_cocina(hogar):
    """Residentes activos agrupados por dieta y textura, para la cocina."""
    from residentes.models import Residente
    grupos = {}
    sin_dieta = []
    for r in (Residente.objects.filter(hogar=hogar, activo=True)
              .select_related('cama_actual__habitacion__departamento')
              .order_by('cama_actual__habitacion__departamento__nombre', 'cama_actual__habitacion__numero',
                        'cama_actual__codigo')):
        d = dieta_vigente(r)
        item = {'residente': r, 'nombre': r.get_nombre(), 'dieta': d, 'alergias': alergias_alimentarias(r)}
        if d is None:
            sin_dieta.append(item)
            continue
        clave = (d.tipo.nombre, d.get_textura_display())
        grupos.setdefault(clave, []).append(item)
    return [{'dieta': k[0], 'textura': k[1], 'residentes': v} for k, v in sorted(grupos.items())], sin_dieta
