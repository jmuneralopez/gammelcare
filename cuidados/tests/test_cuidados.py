"""Cuidados diarios, plan de cuidados, heridas, alertas, ayuda y PDF."""
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from alertas import motor
from alertas.models import Alerta
from auditoria.models import RegistroAuditoria
from cuidados import services
from cuidados.models import Herida, PlanCuidados, RegistroCuidado, SeguimientoHerida
from medicamentos.tests.conftest import *  # noqa: F401,F403  (hogar, usuarios, residente)

pytestmark = pytest.mark.django_db

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


@pytest.fixture(autouse=True)
def media_privada(tmp_path, settings):
    settings.PRIVATE_MEDIA_ROOT = tmp_path


def _plan(residente, usuario, **kw):
    datos = dict(cambios_posicion=True, intervalo_posicion_horas=2, usa_panal=True)
    datos.update(kw)
    return PlanCuidados.objects.create(residente=residente, actualizado_por=usuario, **datos)


def _norton(residente, usuario, puntaje):
    from valoracion import escalas as E
    from valoracion.models import Valoracion
    b = E.POR_CODIGO['norton'].interpretar(puntaje)
    return Valoracion.objects.create(residente=residente, escala='norton', puntaje=puntaje, interpretacion=b.texto,
                                     nivel=b.nivel, registrado_por=usuario)


def _activas(hogar, regla):
    return Alerta.objects.filter(hogar=hogar, regla=regla, estado__in=Alerta.ACTIVAS)


class TestRegistro:

    def test_registro_inmutable_con_hash(self, residente, usuario_enfermero):
        r = services.registrar(residente, 'posicion', 'lateral_der', usuario_enfermero)
        assert r.verificar_integridad()
        r.detalle = 'supino'
        with pytest.raises(ValueError):
            r.save()
        with pytest.raises(ValueError):
            r.delete()

    def test_opcion_invalida_y_futuro(self, residente, usuario_enfermero):
        with pytest.raises(ValueError):
            services.registrar(residente, 'posicion', 'parado', usuario_enfermero)
        with pytest.raises(ValueError):
            services.registrar(residente, 'banio', 'ducha', usuario_enfermero, timezone.now() + timedelta(hours=1))

    def test_rotacion_de_posicion(self, residente, usuario_enfermero):
        assert services.siguiente_posicion(None) == 'lateral_der'
        r = services.registrar(residente, 'posicion', 'lateral_der', usuario_enfermero)
        assert services.siguiente_posicion(r) == 'supino'

    def test_un_toque_desde_planilla(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        r = client.post(reverse('cuidados_registrar_rapido', args=[residente.pk]),
                        {'tipo': 'panal', 'detalle': 'orina', 'volver': reverse('cuidados_planilla')})
        assert r.status_code == 302 and r.url.endswith(f'#res-{residente.pk}')
        assert RegistroCuidado.objects.filter(residente=residente, tipo='panal', detalle='orina').exists()

    def test_volver_externo_se_ignora(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        r = client.post(reverse('cuidados_registrar_rapido', args=[residente.pk]),
                        {'tipo': 'banio', 'detalle': 'ducha', 'volver': 'https://otro.sitio/'})
        assert r.url.startswith(reverse('cuidados_planilla'))

    def test_medico_no_registra_cuidados(self, client, residente, usuario_medico):
        client.force_login(usuario_medico)
        r = client.post(reverse('cuidados_registrar_rapido', args=[residente.pk]), {'tipo': 'banio', 'detalle': 'ducha'})
        assert r.status_code in (302, 403)
        assert not RegistroCuidado.objects.exists()

    def test_registro_con_hora(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        hora = timezone.localtime() - timedelta(hours=3)
        client.post(reverse('cuidados_registrar', args=[residente.pk]), {
            'tipo': 'banio', 'detalle': 'cama', 'fecha_hora': hora.strftime('%Y-%m-%dT%H:%M'), 'observaciones': 'Piel íntegra'})
        r = RegistroCuidado.objects.get()
        assert r.detalle == 'cama' and r.observaciones == 'Piel íntegra'

    def test_anular_propio_y_ajeno(self, client, residente, usuario_enfermero, usuario_fisioterapeuta):
        r = services.registrar(residente, 'posicion', 'supino', usuario_enfermero)
        client.force_login(usuario_fisioterapeuta)
        client.post(reverse('cuidados_anular', args=[r.pk]), {'motivo': 'x'})
        r.refresh_from_db()
        assert not r.anulado
        client.force_login(usuario_enfermero)
        client.post(reverse('cuidados_anular', args=[r.pk]), {'motivo': 'Residente equivocado'})
        r.refresh_from_db()
        assert r.anulado and r.verificar_integridad()
        assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.CUIDADO_ANULADO).exists()


class TestPlanilla:

    def test_planilla_y_pendientes(self, client, residente, usuario_enfermero, usuario_jefe_enfermeria):
        p = _plan(residente, usuario_jefe_enfermeria)
        PlanCuidados.objects.filter(pk=p.pk).update(fecha_actualizacion=timezone.now() - timedelta(hours=3))
        client.force_login(usuario_enfermero)
        r = client.get(reverse('cuidados_planilla'))
        assert r.status_code == 200
        fila = r.context['filas'][0]
        assert list(fila['celdas'])[0] == 'posicion'
        assert fila['celdas']['posicion']['pendiente'] and fila['celdas']['posicion']['atraso'] > 0
        services.registrar(residente, 'posicion', 'lateral_der', usuario_enfermero)
        r = client.get(reverse('cuidados_planilla'))
        assert not r.context['filas'][0]['celdas']['posicion']['pendiente']
        assert 'Pasar a: Boca arriba' in r.content.decode()

    def test_sugerencia_por_norton(self, residente, usuario_medico):
        assert not services.plan_de(residente).cambios_posicion
        _norton(residente, usuario_medico, 11)
        plan = services.plan_de(residente)
        assert plan.cambios_posicion and plan.intervalo_posicion_horas == 2 and plan.pk is None

    def test_turnos(self):
        tz = timezone.get_current_timezone()
        from datetime import datetime
        assert services.turno_actual(timezone.make_aware(datetime(2026, 10, 1, 7), tz))[0] == 'manana'
        assert services.turno_actual(timezone.make_aware(datetime(2026, 10, 1, 15), tz))[0] == 'tarde'
        c, _, ini, fin = services.turno_actual(timezone.make_aware(datetime(2026, 10, 2, 3), tz))
        assert c == 'noche' and timezone.localtime(ini).day == 1 and timezone.localtime(fin).day == 2

    def test_plan_solo_medico_o_jefe(self, client, residente, usuario_enfermero, usuario_jefe_enfermeria):
        url = reverse('cuidados_plan', args=[residente.pk])
        client.force_login(usuario_enfermero)
        assert client.get(url).status_code in (302, 403)
        client.force_login(usuario_jefe_enfermeria)
        assert client.get(url).status_code == 200
        r = client.post(url, {'cambios_posicion': 'on', 'intervalo_posicion_horas': 3, 'banio': 'interdiario',
                              'higiene_oral': 'on', 'indicaciones': 'Colchón antiescaras'})
        assert r.status_code == 302
        p = PlanCuidados.objects.get(residente=residente)
        assert p.tipos() == ['posicion', 'banio', 'higiene_oral'] and p.intervalo_posicion_horas == 3
        assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.PLAN_CUIDADOS).exists()

    def test_pagina_residente(self, client, residente, usuario_enfermero):
        services.registrar(residente, 'higiene_oral', 'dientes', usuario_enfermero)
        client.force_login(usuario_enfermero)
        r = client.get(reverse('cuidados_residente', args=[residente.pk]), {'dias': 7})
        assert r.status_code == 200 and 'Cepillado' in r.content.decode()


class TestHeridas:

    def _herida(self, client, residente):
        return client.post(reverse('cuidados_herida_crear', args=[residente.pk]), {
            'tipo': 'lpp', 'ubicacion': 'sacro', 'estadio_inicial': '2', 'origen': 'hogar',
            'fecha_deteccion': timezone.localdate().strftime('%Y-%m-%d'), 'descripcion': 'Ampolla'})

    def test_lpp_exige_estadio(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        r = client.post(reverse('cuidados_herida_crear', args=[residente.pk]), {
            'tipo': 'lpp', 'ubicacion': 'sacro', 'origen': 'hogar', 'fecha_deteccion': timezone.localdate().strftime('%Y-%m-%d')})
        assert r.status_code == 200 and not Herida.objects.exists()

    def test_flujo_completo_con_foto(self, client, residente, usuario_enfermero, usuario_jefe_enfermeria, hogar):
        client.force_login(usuario_enfermero)
        r = self._herida(client, residente)
        h = Herida.objects.get()
        assert r.url == reverse('cuidados_seguimiento_crear', args=[h.pk])
        assert h.nombre == 'Lesión por presión — Sacro' and h.estadio_actual == 'Estadio 2'
        foto = SimpleUploadedFile('herida.png', PNG, content_type='image/png')
        r = client.post(reverse('cuidados_seguimiento_crear', args=[h.pk]), {
            'fecha_hora': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'largo_cm': '3', 'ancho_cm': '2',
            'estadio': '3', 'lecho': 'granulacion', 'exudado': 'escaso', 'piel_alrededor': 'enrojecida',
            'signos_infeccion': 'on', 'curacion': 'Solución salina e hidrocoloide', 'foto_archivo': foto})
        assert r.status_code == 302
        s = SeguimientoHerida.objects.get()
        assert s.area_cm2 == Decimal('6.0') and s.foto_tipo == 'image/png' and s.verificar_integridad()
        assert h.estadio_actual == 'Estadio 3'
        r = client.get(reverse('cuidados_foto', args=[s.pk]))
        assert r.status_code == 200 and r['Content-Type'] == 'image/png'
        assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.CONSULTA_FOTO_HERIDA).exists()
        assert client.get(reverse('cuidados_herida_detalle', args=[h.pk])).status_code == 200
        motor.evaluar_hogar(hogar)
        assert _activas(hogar, 'herida_infeccion').exists()
        assert _activas(hogar, 'lpp_nueva').exists()
        # Cerrar: solo jefe o médico
        client.post(reverse('cuidados_herida_cerrar', args=[h.pk]), {'motivo': 'cicatrizada'})
        h.refresh_from_db()
        assert h.activa
        client.force_login(usuario_jefe_enfermeria)
        client.post(reverse('cuidados_herida_cerrar', args=[h.pk]), {'motivo': 'cicatrizada'})
        h.refresh_from_db()
        assert not h.activa and h.cerrada_por == usuario_jefe_enfermeria
        motor.evaluar_hogar(hogar)
        assert not _activas(hogar, 'herida_infeccion').exists()

    def test_seguimiento_vacio_rechazado_y_pdf_no_aceptado(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        self._herida(client, residente)
        h = Herida.objects.get()
        url = reverse('cuidados_seguimiento_crear', args=[h.pk])
        r = client.post(url, {'fecha_hora': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
                              'exudado': 'ninguno', 'piel_alrededor': 'sana'})
        assert r.status_code == 200 and not SeguimientoHerida.objects.exists()
        pdf = SimpleUploadedFile('x.pdf', b'%PDF-1.4 xxx', content_type='application/pdf')
        r = client.post(url, {'fecha_hora': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'exudado': 'ninguno',
                              'piel_alrededor': 'sana', 'foto_archivo': pdf})
        assert r.status_code == 200 and not SeguimientoHerida.objects.exists()

    def test_tablero(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        self._herida(client, residente)
        r = client.get(reverse('cuidados_heridas'))
        assert r.status_code == 200 and r.context['lpp_hogar'] == 1


class TestAlertas:

    def test_posicion_atrasada_y_se_resuelve(self, hogar, residente, usuario_enfermero, usuario_jefe_enfermeria):
        p = _plan(residente, usuario_jefe_enfermeria)
        PlanCuidados.objects.filter(pk=p.pk).update(fecha_actualizacion=timezone.now() - timedelta(hours=3))
        motor.evaluar_hogar(hogar)
        a = _activas(hogar, 'posicion_atrasada').get()
        assert a.es_para(usuario_enfermero)
        services.registrar(residente, 'posicion', 'supino', usuario_enfermero)
        motor.evaluar_hogar(hogar)
        a.refresh_from_db()
        assert a.estado == Alerta.RESUELTA

    def test_riesgo_sin_cambios(self, hogar, residente, usuario_medico, usuario_jefe_enfermeria):
        _norton(residente, usuario_medico, 12)
        motor.evaluar_hogar(hogar)
        assert _activas(hogar, 'riesgo_sin_cambios').exists()
        _plan(residente, usuario_jefe_enfermeria)
        motor.evaluar_hogar(hogar)
        assert not _activas(hogar, 'riesgo_sin_cambios').exists()

    def test_herida_sin_seguimiento(self, hogar, residente, usuario_enfermero):
        h = Herida.objects.create(residente=residente, tipo='desgarro', ubicacion='brazo_der', origen='hogar',
                                  registrado_por=usuario_enfermero)
        Herida.objects.filter(pk=h.pk).update(fecha_registro=timezone.now() - timedelta(days=4))
        motor.evaluar_hogar(hogar)
        assert _activas(hogar, 'herida_sin_seguimiento').exists()


class TestIntegracion:

    def test_expediente_y_menu(self, client, residente, usuario_medico):
        client.force_login(usuario_medico)
        html = client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()
        assert 'Cuidados y heridas' in html and reverse('cuidados_planilla') in html
        assert 'value="cuidados"' in html

    def test_ayuda(self, client, usuario_enfermero):
        client.force_login(usuario_enfermero)
        html = client.get(reverse('cuidados_planilla')).content.decode()
        assert 'Cuidados del turno' in html and 'Registrar un cuidado con un toque' in html

    def test_pdf(self, residente, usuario_enfermero, usuario_jefe_enfermeria):
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from residentes import pdf_secciones
        n = getSampleStyleSheet()['Normal']
        kit = pdf_secciones.Kit(n, n, n, n, colors.blue, colors.white, colors.white)
        assert pdf_secciones.cuidados(residente, kit) == []
        _plan(residente, usuario_jefe_enfermeria)
        Herida.objects.create(residente=residente, tipo='lpp', ubicacion='talon_der', estadio_inicial='1',
                              registrado_por=usuario_enfermero)
        flow = pdf_secciones.cuidados(residente, kit)
        assert len(flow) >= 3
