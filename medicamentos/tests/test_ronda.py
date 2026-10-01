"""Ronda por franja horaria (3.1): todo el hogar agrupado por horario, en
vez de residente por residente, con un solo guardado al final."""
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from medicamentos import services
from medicamentos.models import (
    Prescripcion, HorarioPrescripcion, Administracion, IngresoMedicamento,
)

pytestmark = pytest.mark.django_db


class TestFranjasDelDia:

    def test_devuelve_las_horas_distintas_en_uso_ese_dia(
        self, residente, medicamento, usuario_medico
    ):
        p1 = Prescripcion.objects.create(
            residente=residente, medicamento=medicamento, dosis_cantidad=1,
            dosis_unidad='tableta', tipo_pauta=Prescripcion.HORARIOS_FIJOS,
            fecha_inicio=date.today() - timedelta(days=1),
            formulada_por='Dr. Prueba', fecha_formula=date.today() - timedelta(days=1),
            registrada_por=usuario_medico,
        )
        HorarioPrescripcion.objects.create(prescripcion=p1, hora=time(8, 0))
        HorarioPrescripcion.objects.create(prescripcion=p1, hora=time(20, 0))

        franjas = services.franjas_del_dia(residente.hogar, date.today())
        assert franjas == [time(8, 0), time(20, 0)]

    def test_ignora_horarios_de_tratamientos_suspendidos(
        self, residente, medicamento, usuario_medico
    ):
        p = Prescripcion.objects.create(
            residente=residente, medicamento=medicamento, dosis_cantidad=1,
            dosis_unidad='tableta', tipo_pauta=Prescripcion.HORARIOS_FIJOS,
            estado=Prescripcion.SUSPENDIDA,
            fecha_inicio=date.today() - timedelta(days=1),
            formulada_por='Dr. Prueba', fecha_formula=date.today() - timedelta(days=1),
            registrada_por=usuario_medico,
        )
        HorarioPrescripcion.objects.create(prescripcion=p, hora=time(8, 0))
        assert services.franjas_del_dia(residente.hogar, date.today()) == []

    def test_ignora_horarios_fuera_del_rango_de_vigencia(
        self, residente, medicamento, usuario_medico
    ):
        p = Prescripcion.objects.create(
            residente=residente, medicamento=medicamento, dosis_cantidad=1,
            dosis_unidad='tableta', tipo_pauta=Prescripcion.HORARIOS_FIJOS,
            fecha_inicio=date.today() + timedelta(days=5),  # aún no empieza
            formulada_por='Dr. Prueba', fecha_formula=date.today(),
            registrada_por=usuario_medico,
        )
        HorarioPrescripcion.objects.create(prescripcion=p, hora=time(8, 0))
        assert services.franjas_del_dia(residente.hogar, date.today()) == []


class TestFranjaMasCercana:

    def test_elige_la_hora_mas_proxima(self):
        franjas = [time(7, 0), time(12, 30), time(18, 30)]
        assert services.franja_mas_cercana(franjas, time(12, 45)) == time(12, 30)
        assert services.franja_mas_cercana(franjas, time(6, 0)) == time(7, 0)

    def test_lista_vacia_devuelve_none(self):
        assert services.franja_mas_cercana([], time(8, 0)) is None


class TestRondaPorFranja:

    def test_agrupa_por_residente_en_la_franja_pedida(
        self, prescripcion_horarios_fijos, ingreso_residente
    ):
        hora = prescripcion_horarios_fijos.horarios.first().hora
        bloques = services.ronda_por_franja(
            prescripcion_horarios_fijos.residente.hogar, date.today(), hora
        )
        assert len(bloques) == 1
        assert bloques[0]['residente'] == prescripcion_horarios_fijos.residente
        assert len(bloques[0]['filas']) == 1
        assert bloques[0]['filas'][0]['pendiente'] is True
        assert bloques[0]['filas'][0]['sin_existencias'] is False

    def test_residente_sin_tomas_en_esa_hora_no_aparece(
        self, prescripcion_horarios_fijos
    ):
        otra_hora = time(23, 59)
        bloques = services.ronda_por_franja(
            prescripcion_horarios_fijos.residente.hogar, date.today(), otra_hora
        )
        assert bloques == []

    def test_marca_sin_existencias_cuando_no_hay_lote_disponible(
        self, prescripcion_horarios_fijos
    ):
        hora = prescripcion_horarios_fijos.horarios.first().hora
        bloques = services.ronda_por_franja(
            prescripcion_horarios_fijos.residente.hogar, date.today(), hora
        )
        assert bloques[0]['filas'][0]['sin_existencias'] is True

    def test_ya_administrada_aparece_como_no_pendiente(
        self, prescripcion_horarios_fijos, ingreso_residente, usuario_enfermero
    ):
        horario = prescripcion_horarios_fijos.horarios.first()
        tz = timezone.get_current_timezone()
        fecha_programada = timezone.make_aware(datetime.combine(date.today(), horario.hora), tz)
        services.registrar_administracion(
            prescripcion=prescripcion_horarios_fijos, fecha_programada=fecha_programada,
            horario=horario, cantidad=Decimal('1'), observacion='',
            usuario=usuario_enfermero,
        )
        bloques = services.ronda_por_franja(
            prescripcion_horarios_fijos.residente.hogar, date.today(), horario.hora
        )
        assert bloques[0]['filas'][0]['pendiente'] is False


class TestProcesarMarcasRonda:

    def _marca_base(self, prescripcion, horario, **overrides):
        marca = {
            'prescripcion': prescripcion,
            'horario': horario,
            'fecha_programada': None,
            'accion': 'administrar',
            'cantidad': None,
            'observacion': '',
            'motivo': '',
            'motivo_uso_botiquin': '',
        }
        marca.update(overrides)
        return marca

    def test_procesa_varias_marcas_exitosas_de_una_vez(
        self, prescripcion_horarios_fijos, ingreso_residente, usuario_enfermero
    ):
        horario = prescripcion_horarios_fijos.horarios.first()
        marcas = [self._marca_base(prescripcion_horarios_fijos, horario)]
        exitosas, fallidas = services.procesar_marcas_ronda(marcas, usuario_enfermero)
        assert len(exitosas) == 1
        assert fallidas == []
        ingreso_residente.refresh_from_db()
        assert ingreso_residente.cantidad_disponible == Decimal('29')

    def test_un_error_en_una_marca_no_tumba_las_demas(
        self, residente, medicamento, usuario_medico, usuario_enfermero, ingreso_residente
    ):
        """Dos tratamientos del mismo residente, mismo medicamento: el
        ingreso solo alcanza para uno. La marca sin saldo debe fallar sin
        afectar el resultado de la que sí tenía con qué completarse."""
        ingreso_residente.cantidad_disponible = Decimal('1')
        ingreso_residente.save(update_fields=['cantidad_disponible'])

        def _prescripcion(hora):
            p = Prescripcion.objects.create(
                residente=residente, medicamento=medicamento, dosis_cantidad=1,
                dosis_unidad='tableta', tipo_pauta=Prescripcion.HORARIOS_FIJOS,
                fecha_inicio=date.today() - timedelta(days=1),
                formulada_por='Dr. Prueba', fecha_formula=date.today() - timedelta(days=1),
                registrada_por=usuario_medico,
            )
            horario = HorarioPrescripcion.objects.create(prescripcion=p, hora=hora)
            return p, horario

        p_con_saldo, horario_con_saldo = _prescripcion(time(8, 0))
        p_sin_saldo, horario_sin_saldo = _prescripcion(time(9, 0))

        marcas = [
            self._marca_base(p_con_saldo, horario_con_saldo),
            self._marca_base(p_sin_saldo, horario_sin_saldo),
        ]
        exitosas, fallidas = services.procesar_marcas_ronda(marcas, usuario_enfermero)
        assert len(exitosas) == 1
        assert len(fallidas) == 1
        assert exitosas[0][0]['prescripcion'] == p_con_saldo
        assert fallidas[0][0]['prescripcion'] == p_sin_saldo

    def test_no_administrar_y_usar_botiquin_tambien_se_procesan(
        self, prescripcion_horarios_fijos, ingreso_botiquin, usuario_enfermero, hogar
    ):
        horario = prescripcion_horarios_fijos.horarios.first()
        marcas = [
            self._marca_base(
                prescripcion_horarios_fijos, horario,
                accion='usar_botiquin', motivo_uso_botiquin='emergencia',
                observacion='sin saldo propio', cantidad=Decimal('1'),
            ),
        ]
        exitosas, fallidas = services.procesar_marcas_ronda(marcas, usuario_enfermero)
        assert len(exitosas) == 1 and not fallidas
        ingreso_botiquin.refresh_from_db()
        assert ingreso_botiquin.cantidad_disponible == Decimal('19')


class TestVistaRonda:

    def test_muestra_las_franjas_y_los_bloques(
        self, client, usuario_enfermero, prescripcion_horarios_fijos, ingreso_residente
    ):
        client.force_login(usuario_enfermero)
        resp = client.get(reverse('ronda'), {'fecha': date.today().isoformat()})
        assert resp.status_code == 200
        assert len(resp.context['franjas']) == 1
        assert len(resp.context['bloques']) == 1

    def test_modo_alistamiento_es_de_solo_lectura_en_el_contexto(
        self, client, usuario_enfermero, prescripcion_horarios_fijos, ingreso_residente
    ):
        client.force_login(usuario_enfermero)
        resp = client.get(reverse('ronda'), {'modo': 'alistamiento'})
        assert resp.status_code == 200
        assert resp.context['modo_alistamiento'] is True

    def test_fisioterapeuta_puede_ver_la_ronda_pero_no_administrar(
        self, client, usuario_fisioterapeuta, prescripcion_horarios_fijos, ingreso_residente
    ):
        client.force_login(usuario_fisioterapeuta)
        resp = client.get(reverse('ronda'))
        assert resp.status_code == 200
        assert resp.context['puede_administrar'] is False

    def test_renderiza_la_advertencia_de_sin_existencias(
        self, client, usuario_enfermero, prescripcion_horarios_fijos
    ):
        """Sin ingreso_residente el lote FEFO no existe — la ronda debe
        mostrar la advertencia y el flujo de botiquín, no reventar."""
        client.force_login(usuario_enfermero)
        resp = client.get(reverse('ronda'), {'fecha': date.today().isoformat()})
        assert resp.status_code == 200
        assert resp.context['bloques'][0]['filas'][0]['sin_existencias'] is True
        assert 'sin existencias propias' in resp.content.decode('utf-8')


class TestVistaRondaGuardar:

    def _payload(self, prescripcion, horario, **overrides):
        marca = {
            'prescripcion': prescripcion.pk, 'horario': horario.pk,
            'fecha': date.today().isoformat(), 'accion': 'administrar',
            'cantidad': '1', 'observacion': '',
        }
        marca.update(overrides)
        return marca

    def test_administrador_no_puede_guardar_la_ronda(
        self, client, usuario_administrador, prescripcion_horarios_fijos, ingreso_residente
    ):
        client.force_login(usuario_administrador)
        horario = prescripcion_horarios_fijos.horarios.first()
        resp = client.post(reverse('ronda_guardar'), data={
            'fecha': date.today().isoformat(), 'hora': horario.hora.strftime('%H:%M'),
            'acciones_json': json.dumps([self._payload(prescripcion_horarios_fijos, horario)]),
        })
        assert resp.status_code == 302
        assert resp.url == reverse('dashboard')
        assert not Administracion.objects.exists()

    def test_guarda_varias_marcas_en_un_solo_post(
        self, client, usuario_enfermero, prescripcion_horarios_fijos, ingreso_residente
    ):
        horario = prescripcion_horarios_fijos.horarios.first()
        client.force_login(usuario_enfermero)
        resp = client.post(reverse('ronda_guardar'), data={
            'fecha': date.today().isoformat(), 'hora': horario.hora.strftime('%H:%M'),
            'acciones_json': json.dumps([self._payload(prescripcion_horarios_fijos, horario)]),
        })
        assert resp.status_code == 302
        administracion = Administracion.objects.get(prescripcion=prescripcion_horarios_fijos)
        assert administracion.estado == Administracion.ADMINISTRADO
        ingreso_residente.refresh_from_db()
        assert ingreso_residente.cantidad_disponible == Decimal('29')

    def test_una_prescripcion_de_otro_hogar_se_descarta_sin_tumbar_el_resto(
        self, client, usuario_enfermero, prescripcion_horarios_fijos, ingreso_residente,
    ):
        from hogares.models import Hogar
        from residentes.models import Residente
        from usuarios.models import Rol

        otro_hogar = Hogar.objects.create(nombre='Otro Hogar', nit='900000001-1', direccion='Otra calle')
        otro_residente = Residente(
            hogar=otro_hogar, fecha_nacimiento=date(1950, 1, 1), tipo_documento='CC',
        )
        otro_residente.set_nombre('Ajeno')
        otro_residente.set_documento('999')
        otro_residente.set_contacto('300')
        otro_residente.save()
        otra_prescripcion = Prescripcion.objects.create(
            residente=otro_residente, medicamento=prescripcion_horarios_fijos.medicamento,
            dosis_cantidad=1, dosis_unidad='tableta', tipo_pauta=Prescripcion.HORARIOS_FIJOS,
            fecha_inicio=date.today(), formulada_por='Dr. Ajeno', fecha_formula=date.today(),
            registrada_por=prescripcion_horarios_fijos.registrada_por,
        )
        horario_ajeno = HorarioPrescripcion.objects.create(prescripcion=otra_prescripcion, hora=time(8, 0))
        horario_propio = prescripcion_horarios_fijos.horarios.first()

        client.force_login(usuario_enfermero)
        resp = client.post(reverse('ronda_guardar'), data={
            'fecha': date.today().isoformat(), 'hora': horario_propio.hora.strftime('%H:%M'),
            'acciones_json': json.dumps([
                self._payload(prescripcion_horarios_fijos, horario_propio),
                self._payload(otra_prescripcion, horario_ajeno),
            ]),
        })
        assert resp.status_code == 302
        # La propia sí se guarda; la ajena queda descartada por no pertenecer al hogar.
        assert Administracion.objects.filter(prescripcion=prescripcion_horarios_fijos).exists()
        assert not Administracion.objects.filter(prescripcion=otra_prescripcion).exists()

    def test_sin_nada_marcado_no_hace_nada(self, client, usuario_enfermero):
        client.force_login(usuario_enfermero)
        resp = client.post(reverse('ronda_guardar'), data={
            'fecha': date.today().isoformat(), 'hora': '08:00', 'acciones_json': '[]',
        })
        assert resp.status_code == 302
        assert not Administracion.objects.exists()
