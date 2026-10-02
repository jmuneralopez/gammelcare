from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from alertas import motor
from alertas.models import Alerta
from auditoria.models import RegistroAuditoria
from residentes.models import Residente
from valoracion import escalas as E
from valoracion import services
from valoracion.models import ConfiguracionValoracion, Valoracion


def _post_items(escala, elegir, **extra):
    """elegir(item) → índice de opción."""
    datos = {'fecha': timezone.localdate().isoformat(), 'observaciones': ''}
    for i in escala.items:
        datos[f'i_{i.codigo}'] = elegir(i)
    datos.update(extra)
    return datos


def _mejor(i):
    return max(range(len(i.opciones)), key=lambda n: i.opciones[n][0])


def _peor(i):
    return min(range(len(i.opciones)), key=lambda n: i.opciones[n][0])


def _antiguo(residente, dias):
    Residente.objects.filter(pk=residente.pk).update(fecha_ingreso=timezone.now() - timedelta(days=dias))
    residente.refresh_from_db()


def _activas(hogar, regla):
    return Alerta.objects.filter(hogar=hogar, regla=regla, estado__in=Alerta.ACTIVAS)


# ── Cálculo ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('escala', [e for e in E.ESCALAS if e.modo == 'items'])
def test_maximos_y_minimos_de_cada_escala(escala):
    mejor = {i.codigo: max(p for p, _ in i.opciones) for i in escala.items}
    peor = {i.codigo: min(p for p, _ in i.opciones) for i in escala.items}
    alto, bajo = E.calcular(escala, mejor), E.calcular(escala, peor)
    assert (bajo, alto) == (escala.minimo, escala.maximo)
    assert escala.interpretar(alto) and escala.interpretar(bajo)


@pytest.mark.parametrize('escala', E.ESCALAS)
def test_bandas_cubren_todo_el_rango_sin_huecos(escala):
    for p in range(escala.minimo, escala.maximo + 1):
        assert escala.interpretar(p) is not None, (escala.codigo, p)


def test_interpretaciones_conocidas():
    assert E.KATZ.interpretar(6).texto == 'Independiente'
    assert E.KATZ.interpretar(4).texto == 'Dependencia moderada'
    assert E.KATZ.interpretar(2).alerta
    assert E.TINETTI.interpretar(18).alerta and not E.TINETTI.interpretar(19).alerta
    assert E.NORTON.interpretar(12).alerta and not E.NORTON.interpretar(13).alerta
    assert E.YESAVAGE.interpretar(6).texto == 'Probable depresión'


def test_pfeiffer_ajusta_por_nivel_educativo():
    tres_errores = {i.codigo: (1 if n < 3 else 0) for n, i in enumerate(E.PFEIFFER.items)}
    assert E.calcular(E.PFEIFFER, tres_errores, 'media') == 3
    assert E.calcular(E.PFEIFFER, tres_errores, 'basica') == 2
    assert E.calcular(E.PFEIFFER, tres_errores, 'superior') == 4
    cero = {i.codigo: 0 for i in E.PFEIFFER.items}
    assert E.calcular(E.PFEIFFER, cero, 'basica') == 0


# ── Aplicar ─────────────────────────────────────────────────────────

def test_solo_escalas_sin_licencia():
    assert set(E.CODIGOS) == {'katz', 'lawton', 'pfeiffer', 'yesavage', 'tinetti', 'norton'}
    assert all(e.modo == 'items' for e in E.ESCALAS)


def test_fisio_aplica_katz_y_queda_inmutable(client, residente, usuarios):
    client.force_login(usuarios['fisio'])
    r = client.post(reverse('valoracion_aplicar', args=[residente.pk, 'katz']), _post_items(E.KATZ, _mejor))
    v = Valoracion.objects.get()
    assert r.url == reverse('valoracion_detalle', args=[v.pk])
    assert (v.puntaje, v.interpretacion, v.nivel) == (6, 'Independiente', E.OK)
    assert v.respuestas['banarse']['texto'].startswith('Independiente') and v.verificar_integridad()
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.VALORACION_REGISTRADA).exists()
    v.puntaje = 50
    with pytest.raises(ValueError):
        v.save()
    with pytest.raises(ValueError):
        v.delete()


def test_faltan_items(client, residente, usuarios):
    client.force_login(usuarios['medico'])
    datos = _post_items(E.NORTON, _mejor)
    del datos['i_movilidad']
    r = client.post(reverse('valoracion_aplicar', args=[residente.pk, 'norton']), datos)
    assert r.status_code == 200 and 'i_movilidad' in r.context['form'].errors
    assert not Valoracion.objects.exists()


def test_rol_sin_permiso_para_la_escala(client, residente, usuarios, psicologo):
    client.force_login(usuarios['auxiliar'])  # aplica Norton y Katz, no Tinetti
    client.post(reverse('valoracion_aplicar', args=[residente.pk, 'tinetti']), _post_items(E.TINETTI, _mejor))
    assert not Valoracion.objects.exists()
    client.post(reverse('valoracion_aplicar', args=[residente.pk, 'norton']), _post_items(E.NORTON, _mejor))
    assert Valoracion.objects.filter(escala='norton').count() == 1
    client.force_login(psicologo)
    client.post(reverse('valoracion_aplicar', args=[residente.pk, 'yesavage']), _post_items(E.YESAVAGE, _mejor))
    assert Valoracion.objects.filter(escala='yesavage').count() == 1


def test_fecha_futura_o_muy_antigua(client, residente, usuarios):
    client.force_login(usuarios['medico'])
    url = reverse('valoracion_aplicar', args=[residente.pk, 'norton'])
    for fecha in (timezone.localdate() + timedelta(days=1), timezone.localdate() - timedelta(days=40)):
        r = client.post(url, _post_items(E.NORTON, _mejor, fecha=fecha.isoformat()))
        assert 'fecha' in r.context['form'].errors


def test_anulacion(client, residente, usuarios):
    v = services.registrar(residente, E.NORTON, usuarios['auxiliar'], timezone.localdate(),
                           respuestas={i.codigo: {'puntos': 4, 'opcion': 0, 'texto': 'x'} for i in E.NORTON.items})
    client.force_login(usuarios['fisio'])
    client.post(reverse('valoracion_anular', args=[v.pk]), {'motivo': 'x'})
    v.refresh_from_db()
    assert not v.anulada
    client.force_login(usuarios['auxiliar'])
    client.post(reverse('valoracion_anular', args=[v.pk]), {'motivo': 'Residente equivocado'})
    v.refresh_from_db()
    assert v.anulada and v.verificar_integridad()
    assert services.estado_por_escala(residente)[[e.codigo for e in E.ESCALAS].index('norton')]['ultima'] is None


# ── Estado, vencimientos y alertas ──────────────────────────────────

def _registrar(residente, usuario, escala, puntaje, dias_atras=0):
    v = Valoracion.objects.create(residente=residente, escala=escala.codigo, puntaje=puntaje,
                                      fecha=timezone.localdate() - timedelta(days=dias_atras),
                                      interpretacion=escala.interpretar(puntaje).texto,
                                      nivel=escala.interpretar(puntaje).nivel, registrado_por=usuario)
    return v


def test_vencimiento_segun_periodicidad(residente, usuarios):
    _antiguo(residente, 400)
    _registrar(residente, usuarios['medico'], E.KATZ, 4, dias_atras=200)
    estado = {f['escala'].codigo: f for f in services.estado_por_escala(residente)}
    assert estado['katz']['vencida'] and estado['pfeiffer']['vencida'] and estado['pfeiffer']['nunca']
    assert not estado['lawton']['exigida'] and not estado['lawton']['vencida']
    config = ConfiguracionValoracion.para_hogar(residente.hogar)
    config.periodicidad = {'katz': 12}
    config.save()
    estado = {f['escala'].codigo: f for f in services.estado_por_escala(residente)}
    assert not estado['katz']['vencida']


def test_recien_ingresado_tiene_gracia(residente):
    assert services.vencidas(residente) == []


def test_alerta_vencidas_agrupada(hogar, residente, usuarios):
    _antiguo(residente, 30)
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'valoracion_vencida').get()
    assert 'Katz' in a.titulo and 'Norton' in a.titulo and a.gravedad == Alerta.INFORMATIVA


def test_alerta_resultado_de_riesgo(hogar, residente, usuarios, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _registrar(residente, usuarios['fisio'], E.TINETTI, 15)
    a = _activas(hogar, 'valoracion_resultado').get()
    assert 'Riesgo alto de caídas' in a.titulo and a.es_para(usuarios['fisio']) and a.es_para(usuarios['medico'])


def test_alerta_deterioro_katz(hogar, residente, usuarios):
    _registrar(residente, usuarios['fisio'], E.KATZ, 6, dias_atras=90)
    _registrar(residente, usuarios['fisio'], E.KATZ, 4)
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'valoracion_resultado').get()
    assert 'empeoró' in a.titulo and '2 puntos' in a.mensaje


def test_resultado_antiguo_no_alerta(hogar, residente, usuarios):
    _registrar(residente, usuarios['fisio'], E.TINETTI, 15, dias_atras=10)
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'valoracion_resultado').exists()


# ── Pantallas y permisos ────────────────────────────────────────────

def test_paginas_renderizan(client, residente, usuarios):
    v1 = _registrar(residente, usuarios['medico'], E.KATZ, 5, dias_atras=100)
    client.force_login(usuarios['medico'])
    client.post(reverse('valoracion_aplicar', args=[residente.pk, 'katz']), _post_items(E.KATZ, _peor))
    v2 = Valoracion.objects.exclude(pk=v1.pk).get()
    urls = [reverse('valoracion_tablero'), reverse('valoracion_residente', args=[residente.pk]),
            reverse('valoracion_detalle', args=[v2.pk]), reverse('valoracion_configuracion'),
            reverse('residente_detalle', args=[residente.pk])]
    urls += [reverse('valoracion_aplicar', args=[residente.pk, e.codigo]) for e in E.ESCALAS if usuarios['medico'].tiene_rol(*e.roles)]
    for url in urls:
        assert client.get(url).status_code == 200, url
    html = client.get(reverse('valoracion_residente', args=[residente.pk])).content.decode()
    assert 'empeoró' in html and 'Aplicar Tinetti' in html
    assert 'Valoración geriátrica' in client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()


def test_configuracion_solo_admin_medico_jefe(client, hogar, usuarios):
    client.force_login(usuarios['auxiliar'])
    assert client.get(reverse('valoracion_configuracion')).status_code == 302
    client.force_login(usuarios['administrador'])
    datos = {e.codigo: e.periodicidad_meses for e in E.ESCALAS}
    datos['lawton'] = 12
    client.post(reverse('valoracion_configuracion'), datos)
    assert ConfiguracionValoracion.para_hogar(hogar).meses('lawton') == 12


def test_otro_hogar(client, residente, usuarios, usuario_otro_hogar):
    v = _registrar(residente, usuarios['medico'], E.NORTON, 15)
    client.force_login(usuario_otro_hogar)
    assert client.get(reverse('valoracion_detalle', args=[v.pk])).status_code == 404
    assert client.get(reverse('valoracion_residente', args=[residente.pk])).status_code == 404
