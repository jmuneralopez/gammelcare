from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from alertas import motor
from alertas.models import Alerta, ConfiguracionAlertas
from auditoria.models import RegistroAuditoria
from notas_clinicas.models import NotaClinica
from residentes.models import Residente
from signos import parametros as P
from signos import services
from signos.models import ControlSignos, RangoResidente, RangosHogar, RegistroLiquidos

FMT = '%Y-%m-%dT%H:%M'


def _ahora(**delta):
    return timezone.localtime(timezone.now() - timedelta(**delta)).strftime(FMT)


def _control(residente, usuario, horas=0, **valores):
    return ControlSignos.objects.create(residente=residente, registrado_por=usuario,
                                        fecha_hora=timezone.now() - timedelta(hours=horas), **valores)


def _activas(hogar, regla):
    return Alerta.objects.filter(hogar=hogar, regla=regla, estado__in=Alerta.ACTIVAS)


def _antiguo(residente, dias):
    Residente.objects.filter(pk=residente.pk).update(fecha_ingreso=timezone.now() - timedelta(days=dias))
    residente.refresh_from_db()


# ── Registro ────────────────────────────────────────────────────────

def test_auxiliar_registra_signos_normales(client, residente, usuarios):
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('signos_control_crear', args=[residente.pk]), {
        'fecha_hora': _ahora(), 'pas': 120, 'pad': 75, 'fc': 72, 'fr': 16, 'temperatura': '36.6', 'spo2': 95,
    }, follow=True)
    c = ControlSignos.objects.get()
    assert c.registrado_por == usuarios['auxiliar'] and c.verificar_integridad()
    assert 'Signos vitales guardados.' in r.content.decode()
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.SIGNOS_REGISTRADOS).exists()


def test_valor_critico_avisa_y_genera_alerta(client, hogar, residente, usuarios, django_capture_on_commit_callbacks):
    client.force_login(usuarios['auxiliar'])
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(reverse('signos_control_crear', args=[residente.pk]),
                        {'fecha_hora': _ahora(), 'pas': 195, 'pad': 100, 'spo2': 85}, follow=True)
    html = r.content.decode()
    assert 'Valores críticos' in html and 'PAS 195' in html and 'SpO₂ 85' in html
    a = _activas(hogar, 'signo_critico').get()
    assert a.gravedad == Alerta.CRITICA and a.es_para(usuarios['medico'])


def test_validaciones(client, residente, usuarios):
    client.force_login(usuarios['auxiliar'])
    url = reverse('signos_control_crear', args=[residente.pk])
    r = client.post(url, {'fecha_hora': _ahora()})
    assert 'al menos un signo' in str(r.context['form'].non_field_errors())
    r = client.post(url, {'fecha_hora': _ahora(), 'pas': 120})
    assert 'pad' in r.context['form'].errors
    r = client.post(url, {'fecha_hora': _ahora(), 'pas': 80, 'pad': 90})
    assert 'pad' in r.context['form'].errors
    r = client.post(url, {'fecha_hora': _ahora(), 'temperatura': '365'})
    assert 'temperatura' in r.context['form'].errors
    r = client.post(url, {'fecha_hora': _ahora(), 'glucometria': 110})
    assert 'momento_glucometria' in r.context['form'].errors
    r = client.post(url, {'fecha_hora': _ahora(), 'spo2': 93, 'oxigeno_suplementario': 'on'})
    assert 'litros_oxigeno' in r.context['form'].errors
    r = client.post(url, {'fecha_hora': _ahora(hours=-2), 'fc': 70})
    assert 'fecha_hora' in r.context['form'].errors
    r = client.post(url, {'fecha_hora': _ahora(hours=80), 'fc': 70})
    assert 'fecha_hora' in r.context['form'].errors
    assert not ControlSignos.objects.exists()


def test_quien_puede_registrar(client, residente, usuarios, nutricionista):
    url = reverse('signos_control_crear', args=[residente.pk])
    client.force_login(nutricionista)
    client.post(url, {'fecha_hora': _ahora(), 'peso': '61.5'})
    assert ControlSignos.objects.count() == 1
    client.force_login(usuarios['social'])
    assert client.get(reverse('signos_residente', args=[residente.pk])).status_code == 200
    client.post(url, {'fecha_hora': _ahora(), 'peso': '61.5'})
    assert ControlSignos.objects.count() == 1


def test_registros_inmutables_y_anulacion(client, residente, usuarios):
    c = _control(residente, usuarios['auxiliar'], fc=200)
    c.fc = 80
    with pytest.raises(ValueError):
        c.save()
    with pytest.raises(ValueError):
        c.delete()
    client.force_login(usuarios['fisio'])  # no es el autor ni médico/jefe
    client.post(reverse('signos_control_anular', args=[c.pk]), {'motivo': 'x'})
    c.refresh_from_db()
    assert not c.anulado
    client.force_login(usuarios['auxiliar'])
    client.post(reverse('signos_control_anular', args=[c.pk]), {'motivo': 'Error de digitación'})
    c.refresh_from_db()
    assert c.anulado and c.anulado_por == usuarios['auxiliar'] and c.verificar_integridad()
    assert services.ultimo_control(residente) is None


def test_autor_no_anula_despues_de_24_horas_pero_jefe_si(client, residente, usuarios):
    c = _control(residente, usuarios['auxiliar'], fc=80)
    ControlSignos.objects.filter(pk=c.pk).update(fecha_registro=timezone.now() - timedelta(hours=30))
    client.force_login(usuarios['auxiliar'])
    client.post(reverse('signos_control_anular', args=[c.pk]), {'motivo': 'x'})
    c.refresh_from_db()
    assert not c.anulado
    client.force_login(usuarios['jefe'])
    client.post(reverse('signos_control_anular', args=[c.pk]), {'motivo': 'Residente equivocado'})
    c.refresh_from_db()
    assert c.anulado


def test_paginas_renderizan(client, residente, usuarios):
    _control(residente, usuarios['auxiliar'], horas=2, pas=130, pad=80, fc=70, temperatura=Decimal('36.5'), peso=Decimal('60'))
    _control(residente, usuarios['auxiliar'], pas=160, pad=95, fc=110, spo2=91, glucometria=200,
             momento_glucometria='ayunas', peso=Decimal('59.5'))
    RegistroLiquidos.objects.create(residente=residente, registrado_por=usuarios['auxiliar'], tipo='ingreso',
                                    via='oral', cantidad_ml=300)
    client.force_login(usuarios['medico'])
    for url in [reverse('signos_tablero'), reverse('signos_residente', args=[residente.pk]) + '?dias=30',
                reverse('signos_control_crear', args=[residente.pk]), reverse('signos_liquidos_crear', args=[residente.pk]),
                reverse('signos_rango_residente', args=[residente.pk]), reverse('signos_rangos_hogar'),
                reverse('residente_detalle', args=[residente.pk])]:
        r = client.get(url)
        assert r.status_code == 200, url
    html = client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()
    assert 'Signos vitales' in html and 'Registrar signos vitales' in html


def test_otro_hogar_no_ve(client, residente, usuarios, usuario_otro_hogar):
    c = _control(residente, usuarios['auxiliar'], fc=80)
    client.force_login(usuario_otro_hogar)
    assert client.get(reverse('signos_residente', args=[residente.pk])).status_code == 404
    assert client.post(reverse('signos_control_anular', args=[c.pk]), {'motivo': 'x'}).status_code == 404


# ── Rangos ──────────────────────────────────────────────────────────

def test_rango_del_residente_cambia_la_interpretacion(client, residente, usuarios):
    c = _control(residente, usuarios['auxiliar'], spo2=89)
    assert services.interpretar_control(c)['spo2']['interpretacion'] == P.BAJO
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('signos_rango_residente', args=[residente.pk]), {'parametro': 'spo2', 'normal_min': 88, 'motivo': 'x'})
    assert not RangoResidente.objects.exists()  # solo el médico
    client.force_login(usuarios['medico'])
    client.post(reverse('signos_rango_residente', args=[residente.pk]),
                {'parametro': 'spo2', 'critico_min': 85, 'normal_min': 88, 'normal_max': 92, 'motivo': 'EPOC'})
    assert services.interpretar_control(c)['spo2']['interpretacion'] == P.NORMAL
    client.post(reverse('signos_rango_residente', args=[residente.pk]),
                {'parametro': 'spo2', 'critico_min': 84, 'normal_min': 87, 'motivo': 'Ajuste'})
    assert RangoResidente.objects.filter(residente=residente, parametro='spo2').count() == 2
    assert RangoResidente.objects.filter(residente=residente, parametro='spo2', activo=True).count() == 1
    regla = RangoResidente.objects.get(activo=True)
    client.post(reverse('signos_rango_quitar', args=[regla.pk]))
    assert services.interpretar_control(c)['spo2']['interpretacion'] == P.BAJO


def test_rango_con_limites_desordenados_se_rechaza(client, residente, usuarios):
    client.force_login(usuarios['medico'])
    r = client.post(reverse('signos_rango_residente', args=[residente.pk]),
                    {'parametro': 'fc', 'normal_min': 100, 'normal_max': 60, 'motivo': 'x'})
    assert r.status_code == 200 and not RangoResidente.objects.exists()


def test_rangos_del_hogar(client, hogar, residente, usuarios):
    c = _control(residente, usuarios['auxiliar'], pas=155, pad=85)
    assert services.interpretar_control(c)['pas']['interpretacion'] == P.ALTO
    client.force_login(usuarios['auxiliar'])
    assert client.get(reverse('signos_rangos_hogar')).status_code == 302
    client.force_login(usuarios['administrador'])
    datos = {}
    for p in P.PARAMETROS:
        for k, v in P.rango_por_defecto(p.codigo).items():
            datos[f'{p.codigo}__{k}'] = '' if v is None else str(v)
    datos['pas__normal_max'] = '160'
    r = client.post(reverse('signos_rangos_hogar'), datos)
    assert r.status_code == 302
    assert list(RangosHogar.para_hogar(hogar).rangos) == ['pas']
    assert services.interpretar_control(c)['pas']['interpretacion'] == P.NORMAL


# ── Líquidos ────────────────────────────────────────────────────────

def test_balance_de_liquidos(client, residente, usuarios):
    client.force_login(usuarios['auxiliar'])
    url = reverse('signos_liquidos_crear', args=[residente.pk])
    client.post(url, {'fecha_hora': _ahora(), 'via': 'oral', 'cantidad_ml': 800})
    client.post(url, {'fecha_hora': _ahora(), 'via': 'orina', 'cantidad_ml': 500})
    client.post(url, {'fecha_hora': _ahora(), 'via': 'otro_egreso', 'cantidad_ml': 100})
    b = services.balance_del_dia(residente)
    assert (b['ingresos'], b['egresos'], b['balance']) == (800, 600, 200)


def test_balance_negativo_alerta(hogar, residente, usuarios):
    RegistroLiquidos.objects.create(residente=residente, registrado_por=usuarios['auxiliar'], tipo='ingreso', via='oral', cantidad_ml=300)
    RegistroLiquidos.objects.create(residente=residente, registrado_por=usuarios['auxiliar'], tipo='egreso', via='vomito', cantidad_ml=900)
    motor.evaluar_hogar(hogar)
    assert '-600 mL' in _activas(hogar, 'balance_negativo').get().titulo


# ── Eliminación (notas de enfermería) ───────────────────────────────

def _nota(residente, usuario, dias_atras=0, deposicion=False, diuresis=True):
    n = NotaClinica.objects.create(residente=residente, autor=usuario, tipo=NotaClinica.ENFERMERIA,
                                   contenido='Turno sin novedad', deposicion=deposicion, diuresis=diuresis)
    NotaClinica.objects.filter(pk=n.pk).update(fecha_creacion=timezone.now() - timedelta(days=dias_atras))
    return n


def test_alerta_dias_sin_deposicion_y_se_resuelve_con_la_nota(hogar, residente, usuarios,
                                                             django_capture_on_commit_callbacks):
    _antiguo(residente, 10)
    _nota(residente, usuarios['auxiliar'], dias_atras=4, deposicion=True)
    _nota(residente, usuarios['auxiliar'], dias_atras=1)
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'sin_deposicion').get()
    assert a.titulo.startswith('Alerta: 4 días sin deposición') and a.gravedad == Alerta.MEDIA
    with django_capture_on_commit_callbacks(execute=True):
        _nota(residente, usuarios['auxiliar'], deposicion=True)
    a.refresh_from_db()
    assert a.estado == Alerta.RESUELTA


def test_dias_sin_deposicion_cuenta_desde_el_ingreso(hogar, residente, usuarios):
    _antiguo(residente, 6)
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'sin_deposicion').get()
    assert '6 días' in a.titulo and a.gravedad == Alerta.ALTA and 'desde su ingreso' in a.mensaje


def test_residente_recien_ingresado_no_alerta(hogar, residente):
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'sin_deposicion').exists()
    assert not _activas(hogar, 'sin_control_signos').exists()


def test_umbral_de_deposicion_configurable(hogar, residente, usuarios):
    _antiguo(residente, 10)
    _nota(residente, usuarios['auxiliar'], dias_atras=2, deposicion=True)
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'sin_deposicion').exists()
    config = ConfiguracionAlertas.para_hogar(hogar)
    config.umbrales = {'dias_sin_deposicion': 2}
    config.save()
    motor.evaluar_hogar(hogar)
    assert _activas(hogar, 'sin_deposicion').exists()


def test_sin_diuresis(hogar, residente, usuarios):
    _antiguo(residente, 5)
    _nota(residente, usuarios['auxiliar'], dias_atras=2, diuresis=True)
    _nota(residente, usuarios['auxiliar'], dias_atras=0, diuresis=False)
    motor.evaluar_hogar(hogar)
    assert _activas(hogar, 'sin_diuresis').get().gravedad == Alerta.ALTA


def test_eliminacion_por_dia(residente, usuarios):
    _nota(residente, usuarios['auxiliar'], dias_atras=0, deposicion=True, diuresis=True)
    _nota(residente, usuarios['auxiliar'], dias_atras=1, deposicion=False, diuresis=True)
    filas = services.eliminacion_por_dia(residente, 3)
    assert [(f['notas'], f['deposicion']) for f in filas] == [(0, False), (1, False), (1, True)]


# ── Otras alertas ───────────────────────────────────────────────────

def test_toma_nueva_normal_resuelve_el_critico(hogar, residente, usuarios):
    _control(residente, usuarios['auxiliar'], horas=1, temperatura=Decimal('39.2'))
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'signo_critico').get()
    _control(residente, usuarios['auxiliar'], temperatura=Decimal('37.0'))
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.estado == Alerta.RESUELTA


def test_fuera_de_rango_no_critico(hogar, residente, usuarios):
    _control(residente, usuarios['auxiliar'], fc=105)
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'signo_fuera_rango').get()
    assert a.gravedad == Alerta.MEDIA and not _activas(hogar, 'signo_critico').exists()


def test_sin_control_de_signos(hogar, residente, usuarios):
    _antiguo(residente, 3)
    motor.evaluar_hogar(hogar)
    assert _activas(hogar, 'sin_control_signos').exists()
    _control(residente, usuarios['auxiliar'], fc=70)
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'sin_control_signos').exists()


def test_perdida_de_peso(hogar, residente, usuarios):
    c = _control(residente, usuarios['auxiliar'], horas=24 * 20, peso=Decimal('60'))
    _control(residente, usuarios['auxiliar'], peso=Decimal('56.4'))
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'perdida_peso').get()
    assert '6.0 %' in a.titulo and a.es_para(usuarios['medico'])
