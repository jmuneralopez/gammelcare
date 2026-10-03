"""Historial, Kardex, hoja de tratamiento, vencimientos, devolución a la
familia, actas, configuración e integración con atención y notas."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from medicamentos import services
from medicamentos.models import (
    Administracion, ConfiguracionMedicamentos, IngresoMedicamento, MovimientoInventario,
)

pytestmark = pytest.mark.django_db


def _suministrar(p, usuario, cuando=None):
    cuando = cuando or timezone.make_aware(datetime.combine(date.today(), time(8, 0)))
    return services.registrar_administracion(
        prescripcion=p, fecha_programada=cuando, horario=p.horarios.first(),
        cantidad=Decimal('1'), observacion='', usuario=usuario,
    )


class TestHistorial:

    def test_residente_muestra_suministros(self, client, usuario_enfermero, residente,
                                           prescripcion_horarios_fijos, ingreso_residente):
        _suministrar(prescripcion_horarios_fijos, usuario_enfermero)
        client.force_login(usuario_enfermero)
        r = client.get(reverse('historial_residente', args=[residente.pk]))
        assert r.status_code == 200
        assert 'Suministrado' in r.content.decode()
        assert '1 suministrados' in r.content.decode()

    def test_hogar_y_filtro_no_suministrado(self, client, usuario_jefe_enfermeria, residente,
                                            prescripcion_horarios_fijos, ingreso_residente):
        _suministrar(prescripcion_horarios_fijos, usuario_jefe_enfermeria)
        client.force_login(usuario_jefe_enfermeria)
        r = client.get(reverse('historial_hogar'), {'estado': 'no_suministrado'})
        assert r.status_code == 200
        assert 'Sin registros en este periodo' in r.content.decode()

    def test_csv_solo_roles_exportacion_y_audita(self, client, usuario_jefe_enfermeria, usuario_enfermero,
                                                 residente, prescripcion_horarios_fijos, ingreso_residente):
        _suministrar(prescripcion_horarios_fijos, usuario_enfermero)
        client.force_login(usuario_enfermero)
        r = client.get(reverse('historial_residente', args=[residente.pk]), {'formato': 'csv'})
        assert r.status_code == 403 or 'text/csv' not in r.get('Content-Type', '')
        client.force_login(usuario_jefe_enfermeria)
        r = client.get(reverse('historial_residente', args=[residente.pk]), {'formato': 'csv'})
        assert 'text/csv' in r['Content-Type']
        contenido = r.content.decode('utf-8-sig')
        assert 'Acetaminofén' in contenido
        assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.EXPORTACION).exists()


class TestKardex:

    def test_cuadricula_del_mes(self, client, usuario_enfermero, residente,
                                prescripcion_horarios_fijos, ingreso_residente):
        _suministrar(prescripcion_horarios_fijos, usuario_enfermero)
        client.force_login(usuario_enfermero)
        r = client.get(reverse('kardex', args=[residente.pk]))
        assert r.status_code == 200
        filas = r.context['filas']
        assert len(filas) == 1 and filas[0]['hora'] == '08:00'
        tipos = [c['tipo'] for c in filas[0]['celdas']]
        assert tipos[date.today().day - 1] == 'ok'
        assert 'Imprimir Kardex' in r.content.decode()

    def test_mes_anterior_sin_ordenes(self, client, usuario_enfermero, residente, prescripcion_horarios_fijos):
        client.force_login(usuario_enfermero)
        r = client.get(reverse('kardex', args=[residente.pk]), {'mes': '2020-01'})
        assert r.status_code == 200
        assert r.context['filas'] == []

    def test_mes_invalido_no_rompe(self, client, usuario_enfermero, residente):
        client.force_login(usuario_enfermero)
        assert client.get(reverse('kardex', args=[residente.pk]), {'mes': 'xx'}).status_code == 200


class TestHojaTratamiento:

    def test_lista_ordenes_activas(self, client, usuario_enfermero, residente, prescripcion_horarios_fijos):
        client.force_login(usuario_enfermero)
        r = client.get(reverse('hoja_tratamiento', args=[residente.pk]))
        assert r.status_code == 200
        html = r.content.decode()
        assert 'Acetaminofén' in html and '08:00' in html


class TestVencimientos:

    def test_semaforo_y_filtros(self, client, usuario_enfermero, residente, medicamento, hogar, ingreso_residente):
        IngresoMedicamento.objects.create(
            residente=residente, medicamento=medicamento, lote='VIEJO',
            fecha_vencimiento=date.today() - timedelta(days=2), cantidad_ingresada=5,
            cantidad_disponible=5, unidad='tabletas', recibido_por=usuario_enfermero)
        IngresoMedicamento.objects.create(
            residente=residente, medicamento=medicamento, lote='NUEVO',
            fecha_vencimiento=date.today() + timedelta(days=500), cantidad_ingresada=5,
            cantidad_disponible=5, unidad='tabletas', recibido_por=usuario_enfermero)
        client.force_login(usuario_enfermero)
        r = client.get(reverse('vencimientos'))
        assert r.status_code == 200
        lotes = [f['lote'].lote for f in r.context['filas']]
        assert 'VIEJO' in lotes and 'L-RESIDENTE-1' in lotes and 'NUEVO' not in lotes
        r = client.get(reverse('vencimientos'), {'ver': 'todos'})
        assert {'VIEJO', 'L-RESIDENTE-1', 'NUEVO'} <= {f['lote'].lote for f in r.context['filas']}
        assert r.context['conteo']['vencido'] == 1

    def test_medico_no_entra(self, client, usuario_medico):
        client.force_login(usuario_medico)
        assert client.get(reverse('vencimientos')).status_code in (302, 403)


class TestDevolucion:

    def test_servicio_devuelve_saldo(self, residente, ingreso_residente, usuario_jefe_enfermeria):
        lote, saldo = services.devolver_lote(ingreso_residente, usuario_jefe_enfermeria, 'Hija María')
        lote.refresh_from_db()
        assert saldo == 30 and lote.cantidad_disponible == 0
        assert lote.estado == IngresoMedicamento.DEVUELTO
        mov = MovimientoInventario.objects.get(ingreso=lote, tipo=MovimientoInventario.DEVOLUCION_FAMILIA)
        assert mov.cantidad == -30

    def test_no_devuelve_botiquin(self, ingreso_botiquin, usuario_jefe_enfermeria):
        with pytest.raises(Exception):
            services.devolver_lote(ingreso_botiquin, usuario_jefe_enfermeria, 'X')

    def test_vista_devuelve_y_redirige_al_acta(self, client, usuario_jefe_enfermeria, residente, ingreso_residente):
        client.force_login(usuario_jefe_enfermeria)
        url = reverse('medicamentos_devolver', args=[residente.pk])
        assert client.get(url).status_code == 200
        r = client.post(url, {'lotes': [ingreso_residente.pk], 'entregado_a': 'Hija María', 'motivo': 'Egreso'})
        assert r.status_code == 302 and reverse('acta_devolucion', args=[residente.pk]) in r.url
        assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.DEVOLUCION_MEDICAMENTOS).exists()
        acta = client.get(r.url)
        assert acta.status_code == 200
        assert 'ACTA DE DEVOLUCIÓN' in acta.content.decode()
        assert len(acta.context['filas']) == 1

    def test_requiere_lote_y_quien_recibe(self, client, usuario_jefe_enfermeria, residente, ingreso_residente):
        client.force_login(usuario_jefe_enfermeria)
        r = client.post(reverse('medicamentos_devolver', args=[residente.pk]), {'entregado_a': ''})
        assert r.status_code == 200
        ingreso_residente.refresh_from_db()
        assert ingreso_residente.cantidad_disponible == 30

    def test_medico_no_devuelve(self, client, usuario_medico, residente, ingreso_residente):
        client.force_login(usuario_medico)
        r = client.post(reverse('medicamentos_devolver', args=[residente.pk]),
                        {'lotes': [ingreso_residente.pk], 'entregado_a': 'X'})
        assert r.status_code in (302, 403)
        ingreso_residente.refresh_from_db()
        assert ingreso_residente.cantidad_disponible == 30


class TestActaRecepcion:

    def test_lista_lo_guardado_hoy(self, client, usuario_enfermero, residente, ingreso_residente):
        client.force_login(usuario_enfermero)
        r = client.get(reverse('acta_recepcion', args=[residente.pk]))
        assert r.status_code == 200
        assert 'ACTA DE RECEPCIÓN' in r.content.decode()
        assert len(r.context['filas']) == 1


class TestConfiguracion:

    def test_jefe_guarda(self, client, usuario_jefe_enfermeria, hogar):
        client.force_login(usuario_jefe_enfermeria)
        url = reverse('medicamentos_configuracion')
        r = client.get(url)
        assert r.status_code == 200
        datos = {k: v.value() for k, v in r.context['form'].items() if v.value() is not None} \
            if hasattr(r.context['form'], 'items') else {}
        datos = {}
        for f in r.context['form']:
            v = f.value()
            if v is not None:
                datos[f.name] = v.strftime('%H:%M') if hasattr(v, 'strftime') else v
        datos['dias_semaforo_verde'] = 200
        datos['dias_semaforo_amarillo'] = 60
        r = client.post(url, datos)
        assert r.status_code == 302, r.context['form'].errors if r.context else ''
        c = ConfiguracionMedicamentos.para_hogar(hogar)
        assert c.dias_semaforo_verde == 200 and c.dias_semaforo_amarillo == 60
        assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.CONFIGURACION_MEDICAMENTOS).exists()

    def test_enfermero_no_entra(self, client, usuario_enfermero):
        client.force_login(usuario_enfermero)
        assert client.get(reverse('medicamentos_configuracion')).status_code in (302, 403)


class TestIntegracion:

    def test_tomas_de_hoy_e_indicador(self, client, usuario_enfermero, residente,
                                      prescripcion_horarios_fijos, ingreso_residente):
        t = services.tomas_de_hoy(residente)
        assert t['total'] == 1
        _suministrar(prescripcion_horarios_fijos, usuario_enfermero)
        assert services.tomas_de_hoy(residente)['suministradas'] == 1
        client.force_login(usuario_enfermero)
        assert client.get(reverse('atencion_lista')).status_code == 200

    def test_nota_muestra_turno_solo_lectura(self, client, usuario_enfermero, residente,
                                             prescripcion_horarios_fijos, ingreso_residente):
        _suministrar(prescripcion_horarios_fijos, usuario_enfermero, cuando=timezone.now() - timedelta(hours=1))
        client.force_login(usuario_enfermero)
        r = client.get(reverse('nota_crear', args=[residente.pk]))
        assert r.status_code == 200
        assert 'Copiar este resumen en la nota' in r.content.decode()

    def test_expediente_resumen_y_enlaces(self, client, usuario_enfermero, residente, prescripcion_horarios_fijos):
        client.force_login(usuario_enfermero)
        html = client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()
        assert reverse('kardex', args=[residente.pk]) in html
        assert reverse('hoja_tratamiento', args=[residente.pk]) in html

    def test_ayuda_en_pantallas_nuevas(self, client, usuario_jefe_enfermeria, residente):
        client.force_login(usuario_jefe_enfermeria)
        html = client.get(reverse('kardex', args=[residente.pk])).content.decode()
        assert 'Historial de suministros y Kardex' in html
