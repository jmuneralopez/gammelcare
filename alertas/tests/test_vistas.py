from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from alertas import motor
from alertas.models import Alerta, ConfiguracionAlertas
from auditoria.models import RegistroAuditoria


def _alerta(hogar, gravedad=Alerta.CRITICA, roles=('medico',), **extra):
    campos = dict(hogar=hogar, regla='prueba', clave=f'prueba:{gravedad}:{",".join(roles)}', gravedad=gravedad,
                  titulo=f'Alerta {gravedad}', roles_destino=Alerta.codificar_roles(roles))
    campos.update(extra)
    return Alerta.objects.create(**campos)


def test_cada_rol_ve_solo_sus_alertas(client, hogar, usuarios, settings):
    settings.ALERTAS_EVALUACION_PEREZOSA = False
    _alerta(hogar, Alerta.CRITICA, ('medico',), titulo='Para el médico')
    _alerta(hogar, Alerta.MEDIA, ('enfermero',), titulo='Para la auxiliar')
    client.force_login(usuarios['auxiliar'])
    html = client.get(reverse('alertas_bandeja')).content.decode()
    assert 'Para la auxiliar' in html and 'Para el médico' not in html
    # el jefe puede ver todas
    client.force_login(usuarios['jefe'])
    html = client.get(reverse('alertas_bandeja') + '?ver=todas').content.decode()
    assert 'Para la auxiliar' in html and 'Para el médico' in html
    # la auxiliar no, aunque lo pida
    client.force_login(usuarios['auxiliar'])
    html = client.get(reverse('alertas_bandeja') + '?ver=todas').content.decode()
    assert 'Para el médico' not in html


def test_campana_y_franja_critica(client, hogar, usuarios, settings):
    settings.ALERTAS_EVALUACION_PEREZOSA = False
    _alerta(hogar, Alerta.CRITICA, ('medico',), titulo='Glucosa crítica', url_accion='/examenes/', texto_accion='Revisar')
    client.force_login(usuarios['medico'])
    r = client.get(reverse('dashboard'))
    assert r.context['alertas_campana']['total'] == 1
    assert r.context['alertas_campana']['color'] == 'danger'
    html = r.content.decode()
    assert 'Alerta crítica:' in html and 'Glucosa crítica' in html
    client.force_login(usuarios['auxiliar'])
    r = client.get(reverse('dashboard'))
    assert r.context['alertas_campana']['total'] == 0 and 'Alerta crítica:' not in r.content.decode()


def test_atender_critica_exige_nota(client, hogar, usuarios, settings):
    settings.ALERTAS_EVALUACION_PEREZOSA = False
    a = _alerta(hogar, Alerta.CRITICA, ('medico',))
    client.force_login(usuarios['medico'])
    client.post(reverse('alerta_atender', args=[a.pk]), {'nota': ''})
    a.refresh_from_db()
    assert a.estado == Alerta.NUEVA
    client.post(reverse('alerta_atender', args=[a.pk]), {'nota': 'Llamé a la familia y ajusté insulina'})
    a.refresh_from_db()
    assert a.estado == Alerta.ATENDIDA and a.atendida_por == usuarios['medico'] and a.vigente
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.ALERTA_ATENDIDA).exists()


def test_no_atiende_quien_no_es_destinatario(client, hogar, usuarios, settings):
    settings.ALERTAS_EVALUACION_PEREZOSA = False
    a = _alerta(hogar, Alerta.MEDIA, ('medico',))
    client.force_login(usuarios['fisio'])
    client.post(reverse('alerta_atender', args=[a.pk]), {'nota': 'x'})
    a.refresh_from_db()
    assert a.estado == Alerta.NUEVA


def test_descartada_no_se_vuelve_a_crear(client, hogar, residente, usuarios):
    motor.evaluar_hogar(hogar)
    a = Alerta.objects.get(regla='sin_alergias')
    client.force_login(usuarios['medico'])
    client.post(reverse('alerta_descartar', args=[a.pk]), {'motivo': 'Se está averiguando con la familia'})
    a.refresh_from_db()
    assert a.estado == Alerta.DESCARTADA
    motor.evaluar_hogar(hogar)
    assert Alerta.objects.filter(regla='sin_alergias').count() == 1


def test_auxiliar_no_descarta_alertas_del_sistema(client, hogar, residente, usuarios):
    motor.evaluar_hogar(hogar)
    a = Alerta.objects.get(regla='sin_alergias')
    a.roles_destino = Alerta.codificar_roles(['enfermero'])
    a.save()
    client.force_login(usuarios['auxiliar'])
    client.post(reverse('alerta_descartar', args=[a.pk]), {'motivo': 'x'})
    a.refresh_from_db()
    assert a.estado == Alerta.NUEVA


def test_publicar_aviso_llega_a_los_roles_y_vence(client, hogar, residente, usuarios, settings):
    settings.ALERTAS_EVALUACION_PEREZOSA = False
    client.force_login(usuarios['jefe'])
    r = client.post(reverse('aviso_crear'), {
        'titulo': 'Ofrecer líquidos cada 2 horas', 'mensaje': '', 'residente': residente.pk,
        'gravedad': 'alta', 'roles': ['enfermero'], 'horas': 8,
    })
    assert r.status_code == 302
    aviso = Alerta.objects.get(origen=Alerta.MANUAL)
    assert aviso.creada_por == usuarios['jefe'] and aviso.residente == residente
    client.force_login(usuarios['auxiliar'])
    assert client.get(reverse('dashboard')).context['alertas_campana']['total'] == 1
    Alerta.objects.filter(pk=aviso.pk).update(vence=timezone.now() - timedelta(minutes=1))
    motor.evaluar_hogar(hogar)
    aviso.refresh_from_db()
    assert aviso.estado == Alerta.VENCIDA and not aviso.vigente


def test_alertas_en_el_expediente(client, hogar, residente, usuarios):
    motor.evaluar_hogar(hogar)
    client.force_login(usuarios['medico'])
    html = client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()
    assert 'Alertas de este residente' in html and 'no tiene alergias registradas' in html


def test_configuracion_solo_admin_y_jefe(client, hogar, residente, usuarios):
    client.force_login(usuarios['medico'])
    r = client.get(reverse('alertas_configuracion'))
    assert r.status_code == 302
    client.force_login(usuarios['administrador'])
    assert client.get(reverse('alertas_configuracion')).status_code == 200
    from alertas.reglas import REGLAS, UMBRALES
    datos = {f'regla_{c}': 'on' for c in REGLAS if c != 'sin_alergias'}
    datos.update({f'umbral_{n}': v['defecto'] for n, v in UMBRALES.items()})
    datos['umbral_dias_stock_bajo'] = 10
    r = client.post(reverse('alertas_configuracion'), datos)
    assert r.status_code == 302
    config = ConfiguracionAlertas.para_hogar(hogar)
    assert config.reglas_desactivadas == ['sin_alergias'] and config.umbral('dias_stock_bajo') == 10
    assert not Alerta.objects.filter(regla='sin_alergias', estado__in=Alerta.ACTIVAS).exists()


def test_otro_hogar_no_toca_alertas_ajenas(client, hogar, usuarios, usuario_otro_hogar, settings):
    settings.ALERTAS_EVALUACION_PEREZOSA = False
    a = _alerta(hogar, Alerta.MEDIA, ('jefe_enfermeria',))
    client.force_login(usuario_otro_hogar)
    assert client.post(reverse('alerta_atender', args=[a.pk]), {'nota': 'x'}).status_code == 404
    assert 'Alerta media' not in client.get(reverse('alertas_bandeja')).content.decode()


def test_next_externo_no_redirige_fuera(client, hogar, usuarios, settings):
    settings.ALERTAS_EVALUACION_PEREZOSA = False
    a = _alerta(hogar, Alerta.MEDIA, ('medico',))
    client.force_login(usuarios['medico'])
    r = client.post(reverse('alerta_atender', args=[a.pk]), {'nota': '', 'next': 'https://malo.example/'})
    assert r.url == reverse('alertas_bandeja')
