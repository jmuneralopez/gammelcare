"""Ciclo de vida completo del módulo, de punta a punta, a través de las
vistas reales (no solo de services.py): formular un tratamiento, recibir
el medicamento, verlo pendiente en la hoja del día, administrarlo con
descuento FEFO, usar el botiquín del hogar cuando no hay saldo propio,
suspender el tratamiento y anular una administración con reverso de
stock. Cada paso también revisa que quedó su rastro de auditoría (ver
plan-modulo-medicamentos.md, sección 5).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from medicamentos.models import (
    Prescripcion, IngresoMedicamento, Administracion, MovimientoInventario,
)

pytestmark = pytest.mark.django_db


def _payload_tratamiento(medicamento, **overrides):
    data = {
        'medicamento': medicamento.pk,
        'dosis_cantidad': '1',
        'dosis_unidad': 'tableta',
        'via_administracion': 'oral',
        'tipo_pauta': Prescripcion.HORARIOS_FIJOS,
        'duracion_tipo': 'indefinida',
        'duracion_dias': '',
        'duracion_fecha': '',
        'dias_semana_sel': ['L', 'M', 'X', 'J', 'V', 'S', 'D'],
        'horas': '08:00',
        'fecha_inicio': date.today().isoformat(),
        'formulada_por': 'Dr. Restrepo — EPS Sanitas',
        'fecha_formula': date.today().isoformat(),
        'numero_formula': '',
        'indicaciones': '',
        'cantidad_total_formulada': '',
        'diagnostico': '',
        'frecuencia_minima_horas': '',
        'dosis_maxima_dia': '',
    }
    data.update(overrides)
    return data


def _payload_ingreso(medicamento, **overrides):
    data = {
        'entregado_por': 'Familiar de prueba',
        'fecha_ingreso': date.today().isoformat(),
        'observaciones': '',
        'filas-TOTAL_FORMS': '1',
        'filas-INITIAL_FORMS': '0',
        'filas-MIN_NUM_FORMS': '0',
        'filas-MAX_NUM_FORMS': '1000',
        'filas-0-medicamento': medicamento.pk,
        'filas-0-lote': 'L2026-09',
        'filas-0-cantidad_ingresada': '30',
        'filas-0-unidad': 'tabletas',
        'filas-0-fecha_vencimiento': (date.today() + timedelta(days=200)).isoformat(),
    }
    data.update(overrides)
    return data


def test_ciclo_completo_prescripcion_a_administracion_suspension_y_anulacion(
    client, residente, medicamento, usuario_medico, usuario_enfermero,
):
    # 1) El médico formula (transcribe) el tratamiento.
    client.force_login(usuario_medico)
    resp = client.post(
        reverse('tratamiento_crear', args=[residente.pk]),
        data=_payload_tratamiento(medicamento),
    )
    assert resp.status_code == 302, resp.context['form'].errors if resp.status_code == 200 else None
    prescripcion = Prescripcion.objects.get(residente=residente)
    assert prescripcion.horarios.count() == 1
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.PRESCRIPCION_CREADA).exists()

    # 2) El auxiliar de enfermería recibe el medicamento que trajo la familia.
    client.force_login(usuario_enfermero)
    resp = client.post(
        reverse('ingreso_crear', args=[residente.pk]),
        data=_payload_ingreso(medicamento),
    )
    assert resp.status_code == 302
    ingreso = IngresoMedicamento.objects.get(residente=residente, lote='L2026-09')
    assert ingreso.cantidad_disponible == Decimal('30')
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.INGRESO_MEDICAMENTO).exists()

    # 3) La hoja del día muestra la toma pendiente, ya con existencias.
    resp = client.get(
        reverse('hoja_dia', args=[residente.pk]), {'fecha': date.today().isoformat()}
    )
    assert resp.status_code == 200
    filas = resp.context['filas']
    assert len(filas) == 1
    assert filas[0]['pendiente'] is True
    assert filas[0]['sin_existencias'] is False

    # 4) El auxiliar de enfermería administra la toma — se descuenta FEFO.
    horario = prescripcion.horarios.first()
    resp = client.post(
        reverse('administracion_registrar', args=[prescripcion.pk, horario.pk]),
        data={'fecha': date.today().isoformat(), 'cantidad_administrada': '1', 'observacion': ''},
    )
    assert resp.status_code == 302
    assert resp.url == reverse('hoja_dia', args=[residente.pk])
    administracion = Administracion.objects.get(prescripcion=prescripcion)
    assert administracion.estado == Administracion.ADMINISTRADO
    ingreso.refresh_from_db()
    assert ingreso.cantidad_disponible == Decimal('29')
    assert administracion.movimientos.filter(tipo=MovimientoInventario.SALIDA_ADMINISTRACION).exists()

    # La hoja del día ya no debe mostrarla como pendiente.
    resp = client.get(
        reverse('hoja_dia', args=[residente.pk]), {'fecha': date.today().isoformat()}
    )
    assert resp.context['filas'][0]['pendiente'] is False

    # 5) El médico suspende el tratamiento (lo ordenó la EPS).
    client.force_login(usuario_medico)
    resp = client.post(
        reverse('tratamiento_suspender', args=[prescripcion.pk]),
        data={'motivo_suspension': 'La EPS suspendió el tratamiento por mejoría'},
    )
    assert resp.status_code == 302
    prescripcion.refresh_from_db()
    assert prescripcion.estado == Prescripcion.SUSPENDIDA
    assert prescripcion.suspendida_por == usuario_medico
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.PRESCRIPCION_SUSPENDIDA).exists()

    # 6) El mismo auxiliar que administró se da cuenta de un error y anula
    #    dentro de la ventana permitida — el stock debe devolverse.
    client.force_login(usuario_enfermero)
    resp = client.post(
        reverse('administracion_anular', args=[administracion.pk]),
        data={'motivo_anulacion': 'Se registró por error, el residente no la recibió'},
    )
    assert resp.status_code == 302
    administracion.refresh_from_db()
    ingreso.refresh_from_db()
    assert administracion.anulada is True
    assert ingreso.cantidad_disponible == Decimal('30')
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.ANULACION_ADMINISTRACION).exists()


def test_no_administracion_registra_motivo_sin_tocar_inventario(
    client, prescripcion_horarios_fijos, ingreso_residente, usuario_enfermero
):
    client.force_login(usuario_enfermero)
    horario = prescripcion_horarios_fijos.horarios.first()
    resp = client.post(
        reverse('administracion_no_registrar', args=[prescripcion_horarios_fijos.pk, horario.pk]),
        data={
            'fecha': date.today().isoformat(),
            'motivo_no_administracion': 'residente_rechazo',
            'observacion': 'El residente se negó a tomarlo',
        },
    )
    assert resp.status_code == 302
    administracion = Administracion.objects.get(prescripcion=prescripcion_horarios_fijos)
    assert administracion.estado == Administracion.NO_ADMINISTRADO
    assert administracion.motivo_no_administracion == 'residente_rechazo'
    assert administracion.ingreso_usado_id is None

    ingreso_residente.refresh_from_db()
    assert ingreso_residente.cantidad_disponible == Decimal('30')  # intacto
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.NO_ADMINISTRACION).exists()


def test_prn_usa_el_botiquin_del_hogar_cuando_no_hay_saldo_propio(
    client, prescripcion_prn, ingreso_botiquin, usuario_enfermero
):
    """El residente no tiene lote propio (no se creó ingreso_residente en
    este test) — solo autorizando explícitamente el botiquín se completa
    la toma PRN, tal como exige services.registrar_administracion."""
    client.force_login(usuario_enfermero)
    resp = client.post(
        reverse('administracion_prn_registrar', args=[prescripcion_prn.pk]),
        data={
            'cantidad_administrada': '1',
            'observacion': 'Dolor agudo, sin saldo propio disponible',
            'usar_botiquin': '1',
            'motivo_uso_botiquin': 'emergencia',
        },
    )
    assert resp.status_code == 302
    administracion = Administracion.objects.get(prescripcion=prescripcion_prn)
    assert administracion.estado == Administracion.ADMINISTRADO
    assert administracion.ingreso_usado_id == ingreso_botiquin.pk
    assert administracion.motivo_uso_botiquin == 'emergencia'

    ingreso_botiquin.refresh_from_db()
    assert ingreso_botiquin.cantidad_disponible == Decimal('19')
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.USO_BOTIQUIN).exists()


def test_prn_sin_saldo_en_ningun_lado_no_crea_nada_y_avisa(
    client, prescripcion_prn, usuario_enfermero
):
    client.force_login(usuario_enfermero)
    resp = client.post(
        reverse('administracion_prn_registrar', args=[prescripcion_prn.pk]),
        data={'cantidad_administrada': '1', 'observacion': 'Sin existencias en ningún lado'},
    )
    assert resp.status_code == 302
    assert not Administracion.objects.filter(prescripcion=prescripcion_prn).exists()
