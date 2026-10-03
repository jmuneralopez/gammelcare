"""Ajustes de navegación: menú por rol, campana, inicio por rol, calendario
del residente, agenda del hogar, ingreso sin alergias ni antecedentes y
página de configuración."""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from medicamentos.tests.conftest import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _menu(html):
    return html[html.index('<!-- SIDEBAR -->'):html.index('<!-- CONTENIDO PRINCIPAL -->')]


class TestMenu:

    def test_alertas_no_estan_en_el_menu_sino_en_la_campana(self, client, usuario_enfermero):
        client.force_login(usuario_enfermero)
        html = client.get(reverse('dashboard')).content.decode()
        assert reverse('alertas_bandeja') not in _menu(html)
        assert 'Ver todas las alertas' in html and 'title="Ir a todas las alertas"' in html

    def test_ronda_solo_enfermeria(self, client, usuario_enfermero, usuario_medico):
        client.force_login(usuario_enfermero)
        assert reverse('ronda') in _menu(client.get(reverse('dashboard')).content.decode())
        client.force_login(usuario_medico)
        assert reverse('ronda') not in _menu(client.get(reverse('dashboard')).content.decode())

    def test_configuracion_agrupada(self, client, usuario_administrador, usuario_enfermero):
        client.force_login(usuario_administrador)
        menu = _menu(client.get(reverse('dashboard')).content.decode())
        assert reverse('configuracion_hogar') in menu and reverse('eps_lista') not in menu
        r = client.get(reverse('configuracion_hogar'))
        assert r.status_code == 200 and reverse('eps_lista') in r.content.decode()
        client.force_login(usuario_enfermero)
        assert client.get(reverse('configuracion_hogar')).status_code == 403


class TestInicio:

    def test_secciones_por_rol(self, client, usuario_enfermero, usuario_medico, usuario_administrador,
                               usuario_nutricionista, residente):
        casos = [(usuario_enfermero, 'Turno de la'), (usuario_medico, 'Seguimiento médico'),
                 (usuario_administrador, 'Gestión del hogar'), (usuario_nutricionista, 'Nutrición')]
        for usuario, titulo in casos:
            client.force_login(usuario)
            r = client.get(reverse('dashboard'))
            assert r.status_code == 200
            titulos = [s.titulo for s in r.context['secciones']]
            assert any(t.startswith(titulo) for t in titulos), (usuario, titulos)
        client.force_login(usuario_enfermero)
        titulos = [s.titulo for s in client.get(reverse('dashboard')).context['secciones']]
        assert 'Gestión del hogar' not in titulos

    def test_tomas_atrasadas(self, client, usuario_enfermero, residente, medicamento, usuario_medico):
        from medicamentos.models import HorarioPrescripcion, Prescripcion
        ahora = timezone.localtime()
        if ahora.hour < 2:
            pytest.skip('Necesita una toma de hoy ya pasada.')
        p = Prescripcion.objects.create(residente=residente, medicamento=medicamento, dosis_cantidad=1,
                                        dosis_unidad='tableta', tipo_pauta=Prescripcion.HORARIOS_FIJOS,
                                        fecha_inicio=timezone.localdate() - timedelta(days=1), formulada_por='Dr',
                                        fecha_formula=timezone.localdate(), registrada_por=usuario_medico)
        HorarioPrescripcion.objects.create(prescripcion=p, hora=(ahora - timedelta(hours=1)).time().replace(second=0, microsecond=0))
        client.force_login(usuario_enfermero)
        secciones = client.get(reverse('dashboard')).context['secciones']
        turno = [s for s in secciones if s.titulo.startswith('Turno')][0]
        assert turno.tarjetas[0].valor == 1 and turno.tarjetas[0].color == 'danger'


class TestCalendario:

    def test_calendario_reune_modulos(self, client, usuario_medico, residente, prescripcion_horarios_fijos):
        from citas.models import Cita
        from notas_clinicas.models import NotaClinica
        Cita.objects.create(residente=residente, lugar='Clínica', especialidad='Cardiología',
                            fecha_hora=timezone.now() + timedelta(days=2), registrado_por=usuario_medico)
        NotaClinica.objects.create(residente=residente, autor=usuario_medico, tipo='evolucion', contenido='Control')
        client.force_login(usuario_medico)
        assert client.get(reverse('residente_calendario', args=[residente.pk])).status_code == 200
        hoy = timezone.localdate()
        datos = client.get(reverse('residente_calendario_data', args=[residente.pk]),
                           {'start': (hoy - timedelta(days=10)).isoformat(), 'end': (hoy + timedelta(days=10)).isoformat()}).json()
        capas = {e['extendedProps']['capa'] for e in datos}
        assert {'citas', 'notas', 'medicamentos'} <= capas
        cita = [e for e in datos if e['extendedProps']['capa'] == 'citas'][0]
        assert cita['extendedProps']['pendiente'] is True
        solo = client.get(reverse('residente_calendario_data', args=[residente.pk]),
                          {'start': hoy.isoformat(), 'end': (hoy + timedelta(days=10)).isoformat(), 'capas': 'citas'}).json()
        assert {e['extendedProps']['capa'] for e in solo} == {'citas'}

    def test_enlace_viejo_redirige(self, client, usuario_medico, residente):
        client.force_login(usuario_medico)
        r = client.get(reverse('notas_calendario', args=[residente.pk]))
        assert r.status_code == 302 and r.url == reverse('residente_calendario', args=[residente.pk])

    def test_agenda_con_otras_fechas(self, client, usuario_enfermero, usuario_jefe_enfermeria, residente):
        from plan_atencion import services as ps
        plan = ps.crear_borrador(residente, usuario_jefe_enfermeria)
        plan.fecha_revision = timezone.localdate() + timedelta(days=3)
        plan.resumen = 'Situación'
        plan.save()
        from plan_atencion.models import ObjetivoPlan
        ObjetivoPlan.objects.create(plan=plan, area='medicacion', necesidad='x', meta='y', intervenciones='z',
                                    responsable='medico', fecha_meta=timezone.localdate() + timedelta(days=30),
                                    creado_por=usuario_jefe_enfermeria)
        ps.activar(plan, usuario_jefe_enfermeria)
        client.force_login(usuario_enfermero)
        html = client.get(reverse('citas_agenda'), {'dias': 7}).content.decode()
        assert 'Revisión del plan de atención' in html
        html = client.get(reverse('citas_agenda'), {'dias': 7, 'ver': 'citas'}).content.decode()
        assert 'Revisión del plan de atención' not in html


class TestIngreso:

    def test_sin_alergias_ni_antecedentes_en_texto(self, client, usuario_administrador, residente):
        from residentes.forms import ExamenIngresoForm, ExpedienteIngresoForm
        assert 'alergias' not in ExpedienteIngresoForm().fields
        assert 'antecedentes_medicos' not in ExamenIngresoForm().fields
        client.force_login(usuario_administrador)
        html = client.get(reverse('residente_editar', args=[residente.pk])).content.decode()
        assert 'Pertenencias y observaciones del ingreso' in html

    def test_alerta_sin_existencias_sin_prestamo(self):
        import inspect
        from alertas import reglas
        assert 'como préstamo' not in inspect.getsource(reglas)
