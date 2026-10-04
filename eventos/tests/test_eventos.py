"""Eventos adversos: reporte, modos de identificación, vigilancia, cierre,
alertas, indicadores e integración con otros módulos."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from alertas import motor
from alertas.models import Alerta
from auditoria.models import RegistroAuditoria
from eventos import services
from eventos.models import ConfiguracionEventos, EventoAdverso, VigilanciaEvento
from medicamentos.tests.conftest import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _activas(hogar, regla):
    return Alerta.objects.filter(hogar=hogar, regla=regla, estado__in=Alerta.ACTIVAS)


def _datos(**kw):
    d = {'tipo': 'caida', 'fecha_hora': (timezone.localtime() - timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'),
         'lugar': 'bano', 'descripcion': 'Se resbaló al salir de la ducha', 'accion_inmediata': 'Se levantó con ayuda',
         'gravedad': 'leve', 'golpe_cabeza': 'on'}
    d.update(kw)
    return d


def _modo(hogar, modo):
    c = ConfiguracionEventos.para_hogar(hogar)
    c.modo_reporte = modo
    c.save()


class TestReporte:

    def test_caida_programa_vigilancia(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        r = client.post(reverse('eventos_reportar', args=[residente.pk]), _datos())
        e = EventoAdverso.objects.get()
        assert r.status_code == 302 and e.golpe_cabeza and e.verificar_integridad()
        assert e.reportado_por == usuario_enfermero
        assert e.vigilancias.count() == 9  # 72 h cada 8 h
        with pytest.raises(ValueError):
            e.descripcion = 'otra'
            e.save()
        with pytest.raises(ValueError):
            e.delete()

    def test_campos_que_no_aplican_se_limpian(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        client.post(reverse('eventos_reportar', args=[residente.pk]), _datos(tipo='fuga', lugar='exterior'))
        e = EventoAdverso.objects.get()
        assert not e.golpe_cabeza and not e.vigilancias.exists()

    def test_error_de_medicacion_exige_que_fallo(self, client, residente, usuario_enfermero, prescripcion_horarios_fijos):
        client.force_login(usuario_enfermero)
        r = client.post(reverse('eventos_reportar', args=[residente.pk]), _datos(tipo='medicacion'))
        assert r.status_code == 200 and not EventoAdverso.objects.exists()
        client.post(reverse('eventos_reportar', args=[residente.pk]),
                    _datos(tipo='medicacion', tipo_error='dosis', prescripcion=prescripcion_horarios_fijos.pk))
        assert EventoAdverso.objects.get().prescripcion == prescripcion_horarios_fijos

    def test_familia_exige_a_quien(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        r = client.post(reverse('eventos_reportar', args=[residente.pk]), _datos(aviso_familia='on'))
        assert r.status_code == 200 and not EventoAdverso.objects.exists()


class TestModosDeReporte:

    def test_confidencial_solo_jefe_ve_quien(self, client, residente, usuario_enfermero, usuario_jefe_enfermeria,
                                              usuario_medico, hogar):
        _modo(hogar, ConfiguracionEventos.CONFIDENCIAL)
        client.force_login(usuario_enfermero)
        client.post(reverse('eventos_reportar', args=[residente.pk]), _datos())
        e = EventoAdverso.objects.get()
        client.force_login(usuario_jefe_enfermeria)
        assert client.get(reverse('eventos_detalle', args=[e.pk])).context['ve_quien'] is True
        client.force_login(usuario_medico)
        assert client.get(reverse('eventos_detalle', args=[e.pk])).context['ve_quien'] is False

    def test_identificado_supervision_ve_quien(self, client, residente, usuario_enfermero, usuario_medico, hogar):
        _modo(hogar, ConfiguracionEventos.IDENTIFICADO)
        client.force_login(usuario_enfermero)
        client.post(reverse('eventos_reportar', args=[residente.pk]), _datos())
        client.force_login(usuario_medico)
        e = EventoAdverso.objects.get()
        assert client.get(reverse('eventos_detalle', args=[e.pk])).context['ve_quien'] is True

    def test_anonimo_no_guarda_nombre_ni_en_auditoria(self, client, residente, usuario_enfermero, hogar):
        client.force_login(usuario_enfermero)
        assert 'anonimo' not in client.get(reverse('eventos_reportar', args=[residente.pk])).context['form'].fields
        _modo(hogar, ConfiguracionEventos.ANONIMO)
        assert 'anonimo' in client.get(reverse('eventos_reportar', args=[residente.pk])).context['form'].fields
        client.post(reverse('eventos_reportar', args=[residente.pk]), _datos(anonimo='on'))
        e = EventoAdverso.objects.get()
        assert e.anonimo and e.reportado_por is None
        a = RegistroAuditoria.objects.get(accion=RegistroAuditoria.EVENTO_REPORTADO)
        assert a.usuario is None and a.ip_address is None

    def test_anonimo_ignorado_si_el_hogar_no_lo_permite(self, residente, usuario_enfermero):
        e = EventoAdverso(residente=residente, tipo='otro', descripcion='x', accion_inmediata='y', gravedad='sin_dano')
        services.registrar(e, usuario_enfermero, anonimo=True)
        assert not e.anonimo and e.reportado_por == usuario_enfermero


class TestSeguimiento:

    def _evento(self, residente, usuario, **kw):
        datos = dict(residente=residente, tipo='caida', descripcion='x', accion_inmediata='y', gravedad='leve')
        datos.update(kw)
        return services.registrar(EventoAdverso(**datos), usuario)

    def test_cierre_solo_jefe_o_medico(self, client, residente, usuario_enfermero, usuario_jefe_enfermeria):
        e = self._evento(residente, usuario_enfermero)
        datos = {'causas': 'Piso mojado', 'acciones': 'Tapete antideslizante'}
        client.force_login(usuario_enfermero)
        client.post(reverse('eventos_cerrar', args=[e.pk]), datos)
        e.refresh_from_db()
        assert e.abierto
        client.force_login(usuario_jefe_enfermeria)
        client.post(reverse('eventos_cerrar', args=[e.pk]), datos)
        e.refresh_from_db()
        assert not e.abierto and e.cerrado_por == usuario_jefe_enfermeria and e.verificar_integridad()

    def test_nota_y_vigilancia(self, client, residente, usuario_enfermero, hogar):
        e = self._evento(residente, usuario_enfermero)
        client.force_login(usuario_enfermero)
        client.post(reverse('eventos_nota', args=[e.pk]), {'texto': 'Se habló con la hija'})
        assert e.notas.count() == 1
        v = e.vigilancias.first()
        client.post(reverse('eventos_vigilancia', args=[v.pk]), {'conciencia': 'confuso', 'dolor': 3})
        v.refresh_from_db()
        assert v.realizada and v.preocupante
        motor.evaluar_hogar(hogar)
        assert _activas(hogar, 'vigilancia_alarma').exists()
        r = client.post(reverse('eventos_vigilancia', args=[v.pk]), {'conciencia': 'alerta'})
        v.refresh_from_db()
        assert v.conciencia == 'confuso'  # no se reescribe

    def test_alertas(self, hogar, residente, usuario_enfermero):
        e = self._evento(residente, usuario_enfermero, gravedad='grave')
        VigilanciaEvento.objects.filter(evento=e).update(programada=timezone.now() - timedelta(hours=2))
        EventoAdverso.objects.filter(pk=e.pk).update(fecha_registro=timezone.now() - timedelta(days=8))
        motor.evaluar_hogar(hogar)
        assert _activas(hogar, 'evento_grave').get().gravedad == Alerta.CRITICA
        assert _activas(hogar, 'vigilancia_atrasada').exists()
        assert _activas(hogar, 'evento_sin_analizar').exists()

    def test_indicadores(self, client, hogar, residente, usuario_enfermero, usuario_administrador, cama):
        from residentes.models import Residente
        Residente.objects.filter(pk=residente.pk).update(fecha_ingreso=timezone.now() - timedelta(days=40))
        self._evento(residente, usuario_enfermero, gravedad='moderado')
        filas = services.indicadores(hogar, meses=3)
        actual = filas[-1]
        assert actual['caidas'] == 1 and actual['caidas_con_dano'] == 1 and actual['dias_residente'] > 0
        assert actual['tasa_caidas'] is not None
        client.force_login(usuario_administrador)
        assert client.get(reverse('eventos_indicadores')).status_code == 200

    def test_auxiliar_ve_solo_lo_suyo_en_la_bandeja(self, client, residente, usuario_enfermero, usuario_jefe_enfermeria):
        self._evento(residente, usuario_jefe_enfermeria)
        client.force_login(usuario_enfermero)
        assert client.get(reverse('eventos_bandeja')).context['eventos'] == []
        assert client.get(reverse('eventos_indicadores')).status_code in (302, 403)


class TestIntegracion:

    def test_desde_lesion_por_presion(self, client, residente, usuario_enfermero):
        from cuidados.models import Herida
        h = Herida.objects.create(residente=residente, tipo='lpp', ubicacion='sacro', estadio_inicial='2',
                                  origen='hogar', registrado_por=usuario_enfermero)
        client.force_login(usuario_enfermero)
        assert client.get(reverse('cuidados_herida_detalle', args=[h.pk])).context['proponer_evento']
        r = client.get(reverse('eventos_reportar', args=[residente.pk]), {'herida': h.pk})
        assert r.context['form'].initial['tipo'] == 'lpp' and r.context['origen'] == 'herida'
        client.post(reverse('eventos_reportar', args=[residente.pk]),
                    _datos(tipo='lpp', herida=h.pk, origen='herida', gravedad='moderado'))
        e = EventoAdverso.objects.get()
        assert e.herida == h and e.origen == 'herida'
        assert not client.get(reverse('cuidados_herida_detalle', args=[h.pk])).context['proponer_evento']

    def test_desde_suministro_corregido(self, client, residente, usuario_enfermero, prescripcion_horarios_fijos,
                                        ingreso_residente):
        from medicamentos import services as ms
        a = ms.registrar_administracion(prescripcion=prescripcion_horarios_fijos, fecha_programada=timezone.now(),
                                        horario=prescripcion_horarios_fijos.horarios.first(), cantidad=Decimal('1'),
                                        observacion='', usuario=usuario_enfermero)
        ms.anular_administracion(a, usuario_enfermero, 'Se dio al residente equivocado')
        client.force_login(usuario_enfermero)
        r = client.get(reverse('hoja_dia', args=[residente.pk]))
        assert r.context['corregidos_sin_evento'] == [a]
        r = client.get(reverse('eventos_reportar', args=[residente.pk]), {'administracion': a.pk})
        assert r.context['form'].initial['tipo'] == 'medicacion'

    def test_expediente_calendario_menu_y_pdf(self, client, residente, usuario_medico):
        e = services.registrar(EventoAdverso(residente=residente, tipo='caida', descripcion='x', accion_inmediata='y',
                                             gravedad='leve'), usuario_medico)
        client.force_login(usuario_medico)
        html = client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()
        assert 'Eventos adversos' in html and reverse('eventos_reportar', args=[residente.pk]) in html
        assert 'value="eventos"' in html
        hoy = timezone.localdate()
        datos = client.get(reverse('residente_calendario_data', args=[residente.pk]),
                           {'start': (hoy - timedelta(days=2)).isoformat(), 'end': (hoy + timedelta(days=4)).isoformat(),
                            'capas': 'eventos'}).json()
        assert any(d['extendedProps']['pendiente'] for d in datos) and any(not d['extendedProps']['pendiente'] for d in datos)
        r = client.get(reverse('residente_pdf', args=[residente.pk]), {'secciones': ['eventos']})
        assert r.content[:4] == b'%PDF'
