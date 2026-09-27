"""Pruebas unitarias de medicamentos/services.py — la lógica de negocio
central del módulo: selección FEFO del lote, descuento y reverso de
inventario, y la regla de que el botiquín común NUNCA se usa solo
(ver plan-modulo-medicamentos.md, sección 2.3)."""
from decimal import Decimal
from datetime import date, timedelta

import pytest

from medicamentos import services
from medicamentos.models import IngresoMedicamento, MovimientoInventario, Administracion


@pytest.mark.django_db
class TestFEFO:

    def test_elige_el_lote_que_vence_primero(self, residente, medicamento, usuario_enfermero):
        IngresoMedicamento.objects.create(
            residente=residente, medicamento=medicamento, lote='LEJANO',
            fecha_vencimiento=date.today() + timedelta(days=300),
            cantidad_ingresada=10, cantidad_disponible=10, recibido_por=usuario_enfermero,
        )
        cercano = IngresoMedicamento.objects.create(
            residente=residente, medicamento=medicamento, lote='CERCANO',
            fecha_vencimiento=date.today() + timedelta(days=30),
            cantidad_ingresada=10, cantidad_disponible=10, recibido_por=usuario_enfermero,
        )
        assert services.elegir_lote_fefo(residente, medicamento) == cercano

    def test_nunca_elige_un_lote_vencido(self, residente, medicamento, usuario_enfermero):
        IngresoMedicamento.objects.create(
            residente=residente, medicamento=medicamento, lote='VENCIDO',
            fecha_vencimiento=date.today() - timedelta(days=1),
            cantidad_ingresada=10, cantidad_disponible=10, recibido_por=usuario_enfermero,
        )
        assert services.elegir_lote_fefo(residente, medicamento) is None

    def test_ignora_lotes_sin_saldo(self, residente, medicamento, usuario_enfermero):
        IngresoMedicamento.objects.create(
            residente=residente, medicamento=medicamento, lote='AGOTADO',
            fecha_vencimiento=date.today() + timedelta(days=100),
            cantidad_ingresada=10, cantidad_disponible=0,
            estado=IngresoMedicamento.AGOTADO, recibido_por=usuario_enfermero,
        )
        assert services.elegir_lote_fefo(residente, medicamento) is None


@pytest.mark.django_db
class TestRegistrarAdministracion:

    def test_descuenta_el_lote_y_deja_movimiento_de_inventario(
        self, prescripcion_horarios_fijos, ingreso_residente, usuario_enfermero
    ):
        horario = prescripcion_horarios_fijos.horarios.first()
        administracion = services.registrar_administracion(
            prescripcion=prescripcion_horarios_fijos, fecha_programada=None,
            horario=horario, cantidad=Decimal('1'), observacion='',
            usuario=usuario_enfermero,
        )
        ingreso_residente.refresh_from_db()
        assert ingreso_residente.cantidad_disponible == Decimal('29')
        assert administracion.ingreso_usado_id == ingreso_residente.pk

        movimiento = administracion.movimientos.get()
        assert movimiento.tipo == MovimientoInventario.SALIDA_ADMINISTRACION
        assert movimiento.cantidad == Decimal('-1')

    def test_agota_el_lote_cuando_la_cantidad_llega_a_cero(
        self, prescripcion_horarios_fijos, ingreso_residente, usuario_enfermero
    ):
        ingreso_residente.cantidad_disponible = Decimal('1')
        ingreso_residente.save(update_fields=['cantidad_disponible'])

        horario = prescripcion_horarios_fijos.horarios.first()
        services.registrar_administracion(
            prescripcion=prescripcion_horarios_fijos, fecha_programada=None,
            horario=horario, cantidad=Decimal('1'), observacion='',
            usuario=usuario_enfermero,
        )
        ingreso_residente.refresh_from_db()
        assert ingreso_residente.cantidad_disponible == Decimal('0')
        assert ingreso_residente.estado == IngresoMedicamento.AGOTADO

    def test_sin_existencias_propias_y_sin_botiquin_levanta_error(
        self, prescripcion_horarios_fijos, usuario_enfermero
    ):
        horario = prescripcion_horarios_fijos.horarios.first()
        with pytest.raises(services.SinExistenciasError):
            services.registrar_administracion(
                prescripcion=prescripcion_horarios_fijos, fecha_programada=None,
                horario=horario, cantidad=Decimal('1'), observacion='',
                usuario=usuario_enfermero,
            )

    def test_nunca_usa_el_botiquin_sin_autorizacion_explicita(
        self, prescripcion_horarios_fijos, ingreso_botiquin, usuario_enfermero
    ):
        """Regla central del módulo: aunque haya saldo en el botiquín del
        hogar, si usar_botiquin no viene marcado explícitamente el sistema
        JAMÁS se completa solo desde ahí (ver plan 2.3)."""
        horario = prescripcion_horarios_fijos.horarios.first()
        with pytest.raises(services.SinExistenciasError):
            services.registrar_administracion(
                prescripcion=prescripcion_horarios_fijos, fecha_programada=None,
                horario=horario, cantidad=Decimal('1'), observacion='',
                usuario=usuario_enfermero,
            )
        ingreso_botiquin.refresh_from_db()
        assert ingreso_botiquin.cantidad_disponible == Decimal('20')

    def test_usa_el_botiquin_cuando_se_autoriza_explicitamente(
        self, prescripcion_horarios_fijos, ingreso_botiquin, usuario_enfermero, hogar
    ):
        horario = prescripcion_horarios_fijos.horarios.first()
        administracion = services.registrar_administracion(
            prescripcion=prescripcion_horarios_fijos, fecha_programada=None,
            horario=horario, cantidad=Decimal('1'), observacion='Sin saldo propio',
            usuario=usuario_enfermero, usar_botiquin=True,
            motivo_uso_botiquin=Administracion.EMERGENCIA, hogar=hogar,
        )
        ingreso_botiquin.refresh_from_db()
        assert ingreso_botiquin.cantidad_disponible == Decimal('19')
        assert administracion.motivo_uso_botiquin == Administracion.EMERGENCIA
        assert administracion.es_uso_botiquin() is True


@pytest.mark.django_db
class TestAnulacion:

    def test_anular_devuelve_el_stock_descontado(
        self, prescripcion_horarios_fijos, ingreso_residente, usuario_enfermero
    ):
        horario = prescripcion_horarios_fijos.horarios.first()
        administracion = services.registrar_administracion(
            prescripcion=prescripcion_horarios_fijos, fecha_programada=None,
            horario=horario, cantidad=Decimal('1'), observacion='',
            usuario=usuario_enfermero,
        )
        services.anular_administracion(administracion, usuario_enfermero, 'Error de digitación')

        ingreso_residente.refresh_from_db()
        administracion.refresh_from_db()
        assert ingreso_residente.cantidad_disponible == Decimal('30')
        assert administracion.anulada is True
        assert administracion.motivo_anulacion == 'Error de digitación'

    def test_anular_reactiva_un_lote_que_quedo_agotado(
        self, prescripcion_horarios_fijos, ingreso_residente, usuario_enfermero
    ):
        ingreso_residente.cantidad_disponible = Decimal('1')
        ingreso_residente.save(update_fields=['cantidad_disponible'])

        horario = prescripcion_horarios_fijos.horarios.first()
        administracion = services.registrar_administracion(
            prescripcion=prescripcion_horarios_fijos, fecha_programada=None,
            horario=horario, cantidad=Decimal('1'), observacion='',
            usuario=usuario_enfermero,
        )
        ingreso_residente.refresh_from_db()
        assert ingreso_residente.estado == IngresoMedicamento.AGOTADO

        services.anular_administracion(administracion, usuario_enfermero, 'Se anuló')
        ingreso_residente.refresh_from_db()
        assert ingreso_residente.estado == IngresoMedicamento.DISPONIBLE
        assert ingreso_residente.cantidad_disponible == Decimal('1')

    def test_administracion_es_inmutable_fuera_de_anulacion_y_reposicion(
        self, prescripcion_horarios_fijos, ingreso_residente, usuario_enfermero
    ):
        """Ver Administracion.save(): solo se permite update_fields dentro
        de CAMPOS_EDITABLES_POST_CREACION (anulación y reposición del
        botiquín) — cualquier otro intento de modificar un registro ya
        creado debe rechazarse (es historia clínica, no un formulario)."""
        horario = prescripcion_horarios_fijos.horarios.first()
        administracion = services.registrar_administracion(
            prescripcion=prescripcion_horarios_fijos, fecha_programada=None,
            horario=horario, cantidad=Decimal('1'), observacion='',
            usuario=usuario_enfermero,
        )
        administracion.observacion = 'intento de editar historia clínica'
        with pytest.raises(ValueError):
            administracion.save(update_fields=['observacion'])
