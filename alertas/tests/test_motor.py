"""Reglas del motor: cada condición crea UNA alerta vigente, se actualiza
mientras exista y se resuelve sola cuando desaparece."""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from alertas import motor
from alertas.models import Alerta, ConfiguracionAlertas
from antecedentes import services as antecedentes
from citas.models import Cita
from examenes import services as examenes
from examenes.models import AnalitoCatalogo, Examen
from medicamentos import services as med
from medicamentos.models import Administracion, HorarioPrescripcion, IngresoMedicamento, Prescripcion


def _activas(hogar, regla=None):
    qs = Alerta.objects.filter(hogar=hogar, estado__in=Alerta.ACTIVAS)
    return qs.filter(regla=regla) if regla else qs


def _lote(residente=None, hogar=None, medicamento=None, usuario=None, vence=None, cantidad=30, lote='L-1'):
    return IngresoMedicamento.objects.create(
        residente=residente, hogar=hogar, medicamento=medicamento, lote=lote,
        fecha_vencimiento=vence or date.today() + timedelta(days=400),
        cantidad_ingresada=cantidad, cantidad_disponible=cantidad, unidad='tabletas', recibido_por=usuario,
    )


def _orden(residente, medicamento, usuario, horas=(), **extra):
    campos = dict(residente=residente, medicamento=medicamento, dosis_cantidad=1, dosis_unidad='tableta',
                  tipo_pauta=Prescripcion.HORARIOS_FIJOS, fecha_inicio=date.today() - timedelta(days=10),
                  formulada_por='Dr. X', fecha_formula=date.today() - timedelta(days=10), registrada_por=usuario)
    campos.update(extra)
    p = Prescripcion.objects.create(**campos)
    for h in horas:
        HorarioPrescripcion.objects.create(prescripcion=p, hora=h)
    return p


# ── Lotes ───────────────────────────────────────────────────────────

def test_lote_vencido_con_el_mensaje_pedido_y_se_resuelve_al_descartar(hogar, residente, medicamento, usuarios):
    lote = _lote(residente=residente, medicamento=medicamento, usuario=usuarios['jefe'],
                 vence=date.today() - timedelta(days=2), lote='A123')
    motor.evaluar_hogar(hogar)
    alerta = _activas(hogar, 'lote_vencido').get()
    assert alerta.titulo == f'El lote A123 de {medicamento} se encuentra vencido. Por favor descártelo completamente.'
    assert alerta.gravedad == Alerta.ALTA and alerta.residente == residente
    assert set(alerta.lista_roles) == {'jefe_enfermeria', 'administrador'}

    motor.evaluar_hogar(hogar)  # no se duplica
    assert Alerta.objects.filter(regla='lote_vencido').count() == 1

    med.descartar_lote(lote, usuarios['jefe'], 'Lote vencido')
    motor.evaluar_hogar(hogar)
    alerta.refresh_from_db()
    assert alerta.estado == Alerta.RESUELTA and not alerta.vigente


def test_lote_del_botiquin_por_vencer(hogar, medicamento, usuarios):
    _lote(hogar=hogar, medicamento=medicamento, usuario=usuarios['jefe'], vence=date.today() + timedelta(days=30))
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'lote_por_vencer').get()
    assert a.gravedad == Alerta.INFORMATIVA and a.residente is None and 'botiquín' in a.mensaje


def test_descartar_lote_resuelve_la_alerta_de_inmediato(hogar, residente, medicamento, usuarios,
                                                       django_capture_on_commit_callbacks):
    lote = _lote(residente=residente, medicamento=medicamento, usuario=usuarios['jefe'], vence=date.today() - timedelta(days=1))
    motor.evaluar_hogar(hogar)
    with django_capture_on_commit_callbacks(execute=True):
        med.descartar_lote(lote, usuarios['jefe'], 'Vencido')
    assert not _activas(hogar, 'lote_vencido').exists()


# ── Exámenes ────────────────────────────────────────────────────────

def test_examen_critico_va_al_medico_y_se_resuelve_al_revisar(hogar, residente, usuarios):
    glucosa = AnalitoCatalogo.objects.get(codigo='glucosa')
    examen = Examen.objects.create(residente=residente, nombre='Glucosa', registrado_por=usuarios['auxiliar'],
                                   fecha_orden=date.today())
    examenes.cargar_resultado(examen, usuarios['auxiliar'], date.today(),
                              valores=[{'analito': glucosa, 'nombre': 'Glucosa', 'valor': Decimal('35'),
                                        'unidad': 'mg/dL', 'ref_min': Decimal('70'), 'ref_max': Decimal('100')}])
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'examen_critico').get()
    assert a.gravedad == Alerta.CRITICA and 'Glucosa 35' in a.mensaje
    assert a.es_para(usuarios['medico']) and not a.es_para(usuarios['auxiliar'])
    examenes.revisar(examen, usuarios['medico'], 'Glucometría cada 4 horas')
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.estado == Alerta.RESUELTA


def test_orden_de_examen_sin_resultado(hogar, residente, usuarios):
    Examen.objects.create(residente=residente, nombre='Perfil lipídico', registrado_por=usuarios['auxiliar'],
                          fecha_orden=date.today() - timedelta(days=20))
    motor.evaluar_hogar(hogar)
    assert _activas(hogar, 'examen_sin_resultado').count() == 1


# ── Medicamentos ────────────────────────────────────────────────────

def test_toma_no_registrada_y_se_resuelve_al_suministrar(hogar, residente, medicamento, usuarios):
    hace_2h = (timezone.localtime() - timedelta(hours=2)).time().replace(second=0, microsecond=0)
    p = _orden(residente, medicamento, usuarios['medico'], horas=[hace_2h])
    _lote(residente=residente, medicamento=medicamento, usuario=usuarios['jefe'])
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'toma_no_registrada').get(clave=f'toma:{residente.pk}:{timezone.localdate():%Y%m%d}')
    assert a.gravedad == Alerta.ALTA and a.es_para(usuarios['auxiliar']) and '1 toma de hoy' in a.titulo
    filas, _ = med.hoja_del_dia(residente)
    fila = [f for f in filas if f['pendiente'] and f['fecha_programada'].date() == timezone.localdate()][0]
    med.registrar_administracion(prescripcion=p, fecha_programada=fila['fecha_programada'], horario=fila['horario'],
                                 cantidad=1, observacion='', usuario=usuarios['auxiliar'])
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.estado == Alerta.RESUELTA


def test_stock_bajo_y_sin_existencias(hogar, residente, medicamento, usuarios):
    _orden(residente, medicamento, usuarios['medico'], horas=['08:00', '20:00'])
    lote = _lote(residente=residente, medicamento=medicamento, usuario=usuarios['jefe'], cantidad=4)  # 2 días
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'stock_bajo').get()
    assert 'alcanza para 2 días' in a.titulo and a.gravedad == Alerta.MEDIA
    IngresoMedicamento.objects.filter(pk=lote.pk).update(cantidad_disponible=0)
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.gravedad == Alerta.ALTA and 'no tiene' in a.titulo
    assert Alerta.objects.filter(regla='stock_bajo').count() == 1  # la misma alerta, actualizada


def test_stock_que_alcanza_hasta_el_fin_de_la_orden_no_alerta(hogar, residente, medicamento, usuarios):
    _orden(residente, medicamento, usuarios['medico'], horas=['08:00'], fecha_fin=date.today() + timedelta(days=2))
    _lote(residente=residente, medicamento=medicamento, usuario=usuarios['jefe'], cantidad=3)
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'stock_bajo').exists()
    assert _activas(hogar, 'orden_por_terminar').count() == 1


def test_prn_por_encima_del_maximo(hogar, residente, medicamento, usuarios):
    p = _orden(residente, medicamento, usuarios['medico'], tipo_pauta=Prescripcion.PRN, dosis_maxima_dia=2)
    _lote(residente=residente, medicamento=medicamento, usuario=usuarios['jefe'])
    for i in range(3):
        med.registrar_administracion(prescripcion=p, fecha_programada=timezone.now() - timedelta(hours=i),
                                     horario=None, cantidad=1, observacion='dolor', usuario=usuarios['auxiliar'])
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'prn_frecuente').get()
    assert '3 dosis' in a.titulo and a.es_para(usuarios['medico'])


def test_prestamo_del_botiquin_sin_reponer(client, hogar, residente, medicamento, usuarios):
    p = _orden(residente, medicamento, usuarios['medico'], horas=['08:00'])
    _lote(hogar=hogar, medicamento=medicamento, usuario=usuarios['jefe'])
    adm = med.registrar_administracion(prescripcion=p, fecha_programada=timezone.now(), horario=None, cantidad=1,
                                       observacion='', usuario=usuarios['auxiliar'], usar_botiquin=True,
                                       motivo_uso_botiquin=Administracion.PRESTAMO)
    Administracion.objects.filter(pk=adm.pk).update(fecha_administracion=timezone.now() - timedelta(days=5))
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'prestamo_sin_reponer').get()
    client.force_login(usuarios['jefe'])
    from django.urls import reverse
    assert 'Marcar como repuesto' in client.get(reverse('botiquin_lista')).content.decode()
    client.post(reverse('prestamo_marcar_repuesto', args=[adm.pk]))
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.estado == Alerta.RESUELTA


# ── Alergias ────────────────────────────────────────────────────────

def test_residente_sin_alergias_registradas(hogar, residente, usuarios):
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'sin_alergias').get()
    antecedentes.declarar_sin_alergias(residente, usuarios['medico'])
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.estado == Alerta.RESUELTA


# ── Citas ───────────────────────────────────────────────────────────

def _cita(residente, usuario, cuando, **extra):
    campos = dict(residente=residente, tipo='especialista', especialidad='Cardiología', lugar='Clínica X',
                  fecha_hora=cuando, registrado_por=usuario)
    campos.update(extra)
    return Cita.objects.create(**campos)


def test_cita_manana_con_logistica_incompleta_es_alta(hogar, residente, usuarios):
    manana = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=1), datetime.min.time())) + timedelta(hours=9)
    c = _cita(residente, usuarios['jefe'], manana, requiere_ayuno=True, preparacion='Llevar exámenes')
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'cita_proxima').get()
    assert a.gravedad == Alerta.ALTA and 'AYUNO' in a.mensaje and 'Falta definir transporte y acompañante' in a.mensaje
    assert a.titulo.startswith('Cita mañana a las 09:00')
    c.transporte, c.acompanante = 'familia', 'Hija'
    c.save()
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.gravedad == Alerta.INFORMATIVA


def test_cita_pasada_sin_cierre_y_se_resuelve_al_cerrar(hogar, residente, usuarios):
    from citas import services as citas
    c = _cita(residente, usuarios['jefe'], timezone.now() - timedelta(days=1))
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'cita_sin_cierre').get()
    citas.cerrar(c, usuarios['jefe'], Cita.CUMPLIDA, 'Sin cambios')
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.estado == Alerta.RESUELTA


def test_cita_lejana_no_alerta(hogar, residente, usuarios):
    _cita(residente, usuarios['jefe'], timezone.now() + timedelta(days=5))
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'cita_proxima').exists()


# ── Motor ───────────────────────────────────────────────────────────

def test_regla_desactivada_cierra_sus_alertas(hogar, residente):
    motor.evaluar_hogar(hogar)
    assert _activas(hogar, 'sin_alergias').exists()
    config = ConfiguracionAlertas.para_hogar(hogar)
    config.reglas_desactivadas = ['sin_alergias']
    config.save()
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'sin_alergias').exists()


def test_umbral_configurable(hogar, residente, usuarios):
    Examen.objects.create(residente=residente, nombre='TSH', registrado_por=usuarios['auxiliar'],
                          fecha_orden=date.today() - timedelta(days=5))
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'examen_sin_resultado').exists()
    config = ConfiguracionAlertas.para_hogar(hogar)
    config.umbrales = {'dias_examen_sin_resultado': 3}
    config.save()
    motor.evaluar_hogar(hogar)
    assert _activas(hogar, 'examen_sin_resultado').exists()


def test_una_regla_rota_no_detiene_las_demas(hogar, residente, monkeypatch):
    from alertas import reglas

    def rota(*a, **k):
        raise RuntimeError('fallo')
    monkeypatch.setitem(reglas.REGLAS, 'examen_critico', (rota, 'x'))
    monkeypatch.setattr(motor, 'REGLAS', reglas.REGLAS)
    motor.evaluar_hogar(hogar)
    assert _activas(hogar, 'sin_alergias').exists()


def test_evaluacion_perezosa_solo_cada_cinco_minutos(hogar, residente):
    assert motor.evaluar_si_toca(hogar) is True
    assert motor.evaluar_si_toca(hogar) is False
    ConfiguracionAlertas.objects.filter(hogar=hogar).update(ultima_evaluacion=timezone.now() - timedelta(minutes=6))
    assert motor.evaluar_si_toca(hogar) is True


def test_comando_evaluar_alertas(hogar, residente, capsys):
    call_command('evaluar_alertas')
    assert 'alerta(s) nueva(s)' in capsys.readouterr().out
    assert _activas(hogar, 'sin_alergias').exists()


def test_alertas_no_se_borran(hogar, residente):
    motor.evaluar_hogar(hogar)
    with pytest.raises(ValueError):
        Alerta.objects.first().delete()
