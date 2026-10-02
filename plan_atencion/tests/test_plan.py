from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from alertas import motor
from alertas.models import Alerta
from auditoria.models import RegistroAuditoria
from plan_atencion import services
from plan_atencion.models import ObjetivoPlan, PlanAtencion, SeguimientoObjetivo
from residentes.models import Residente
from valoracion import escalas as E
from valoracion.models import Valoracion


def _objetivo_datos(**extra):
    d = {'area': 'caidas', 'necesidad': 'Riesgo de caídas', 'meta': 'Sin caídas en 3 meses',
         'intervenciones': 'Acompañar al caminar', 'responsable': 'fisioterapeuta', 'frecuencia': 'Diario',
         'fecha_meta': (timezone.localdate() + timedelta(days=90)).isoformat(), 'origen': ''}
    d.update(extra)
    return d


def _plan_listo(residente, usuario):
    plan = services.crear_borrador(residente, usuario)
    plan.resumen = 'Residente con riesgo de caídas.'
    plan.save()
    ObjetivoPlan.objects.create(plan=plan, area='caidas', necesidad='x', meta='Sin caídas', intervenciones='y',
                                responsable='fisioterapeuta', fecha_meta=timezone.localdate() + timedelta(days=60),
                                creado_por=usuario)
    return plan


def _activas(hogar, regla):
    return Alerta.objects.filter(hogar=hogar, regla=regla, estado__in=Alerta.ACTIVAS)


# ── Ciclo de vida ───────────────────────────────────────────────────

def test_flujo_completo_por_pantallas(client, residente, usuarios):
    client.force_login(usuarios['fisio'])
    r = client.post(reverse('plan_crear', args=[residente.pk]))
    plan = PlanAtencion.objects.get()
    assert r.url == reverse('plan_detalle', args=[plan.pk]) and plan.estado == PlanAtencion.BORRADOR and plan.version == 1
    client.post(reverse('plan_objetivo_crear', args=[plan.pk]), _objetivo_datos())
    assert plan.objetivos.count() == 1
    # el fisio no activa
    client.post(reverse('plan_activar', args=[plan.pk]))
    plan.refresh_from_db()
    assert plan.estado == PlanAtencion.BORRADOR
    client.force_login(usuarios['medico'])
    client.post(reverse('plan_activar', args=[plan.pk]))  # falta el resumen
    plan.refresh_from_db()
    assert plan.estado == PlanAtencion.BORRADOR
    client.post(reverse('plan_editar', args=[plan.pk]), {
        'resumen': 'Katz 4, Tinetti 15.', 'participantes': 'Equipo', 'acuerdos_familia': '',
        'fecha_revision': (timezone.localdate() + timedelta(days=90)).isoformat()})
    client.post(reverse('plan_activar', args=[plan.pk]))
    plan.refresh_from_db()
    assert plan.estado == PlanAtencion.VIGENTE and plan.activado_por == usuarios['medico']
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.PLAN_ATENCION).count() >= 2


def test_plan_vigente_no_se_edita(client, residente, usuarios):
    plan = _plan_listo(residente, usuarios['medico'])
    services.activar(plan, usuarios['medico'])
    o = plan.objetivos.get()
    client.force_login(usuarios['medico'])
    client.post(reverse('plan_objetivo_editar', args=[o.pk]), _objetivo_datos(meta='Cambiado'))
    o.refresh_from_db()
    assert o.meta == 'Sin caídas'
    client.post(reverse('plan_objetivo_quitar', args=[o.pk]))
    assert ObjetivoPlan.objects.filter(pk=o.pk).exists()
    r = client.post(reverse('plan_editar', args=[plan.pk]), {'resumen': 'x', 'fecha_revision': '2099-01-01'})
    plan.refresh_from_db()
    assert plan.resumen == 'Residente con riesgo de caídas.'
    with pytest.raises(ValueError):
        plan.delete()
    # sí se agregan objetivos nuevos
    client.post(reverse('plan_objetivo_crear', args=[plan.pk]), _objetivo_datos(area='piel', meta='Piel íntegra'))
    assert plan.objetivos.count() == 2


def test_seguimiento_cambia_estado_y_queda_registrado(client, residente, usuarios):
    plan = _plan_listo(residente, usuarios['medico'])
    o = plan.objetivos.get()
    client.force_login(usuarios['auxiliar'])
    client.post(reverse('plan_seguimiento', args=[o.pk]), {'estado': 'logrado', 'nota': 'x'})  # borrador: no
    assert not SeguimientoObjetivo.objects.exists()
    services.activar(plan, usuarios['medico'])
    client.post(reverse('plan_seguimiento', args=[o.pk]), {'estado': 'parcial', 'nota': 'Camina acompañado sin caídas'})
    o.refresh_from_db()
    s = SeguimientoObjetivo.objects.get()
    assert o.estado == 'parcial' and s.registrado_por == usuarios['auxiliar']
    with pytest.raises(ValueError):
        s.delete()
    assert plan.avance() == {'logrados': 0, 'total': 1, 'porcentaje': 0}


def test_revision_crea_version_nueva_copiando_lo_en_curso(residente, usuarios):
    plan = _plan_listo(residente, usuarios['medico'])
    ObjetivoPlan.objects.create(plan=plan, area='piel', necesidad='x', meta='Piel', intervenciones='y',
                                responsable='enfermero', fecha_meta=timezone.localdate() + timedelta(days=60),
                                creado_por=usuarios['medico'], estado='logrado')
    services.activar(plan, usuarios['medico'])
    v2 = services.crear_borrador(residente, usuarios['jefe'])
    assert v2.version == 2 and v2.anterior == plan and v2.resumen == plan.resumen
    assert list(v2.objetivos.values_list('meta', flat=True)) == ['Sin caídas']
    with pytest.raises(ValidationError):
        services.crear_borrador(residente, usuarios['jefe'])
    services.activar(v2, usuarios['jefe'])
    plan.refresh_from_db()
    assert plan.estado == PlanAtencion.REEMPLAZADO and services.vigente(residente) == v2


def test_descartar_borrador(client, residente, usuarios):
    plan = services.crear_borrador(residente, usuarios['medico'])
    client.force_login(usuarios['social'])
    client.post(reverse('plan_descartar', args=[plan.pk]))
    assert not PlanAtencion.objects.exists()


def test_auxiliar_no_elabora(client, residente, usuarios):
    client.force_login(usuarios['auxiliar'])
    client.post(reverse('plan_crear', args=[residente.pk]))
    assert not PlanAtencion.objects.exists()
    assert client.get(reverse('plan_residente', args=[residente.pk])).status_code == 200


# ── Sugerencias ─────────────────────────────────────────────────────

def test_sugerencia_desde_tinetti(client, residente, usuarios):
    b = E.TINETTI.interpretar(14)
    Valoracion.objects.create(residente=residente, escala='tinetti', puntaje=14, interpretacion=b.texto, nivel=b.nivel,
                              registrado_por=usuarios['fisio'])
    plan = services.crear_borrador(residente, usuarios['fisio'])
    client.force_login(usuarios['fisio'])
    html = client.get(reverse('plan_detalle', args=[plan.pk])).content.decode()
    assert 'Objetivos sugeridos' in html and 'Tinetti 14' in html
    r = client.get(reverse('plan_objetivo_crear', args=[plan.pk]) + '?sugerencia=caidas')
    assert r.context['form'].initial['area'] == 'caidas'
    datos = {k: v for k, v in r.context['form'].initial.items()}
    datos['fecha_meta'] = datos['fecha_meta'].isoformat()
    client.post(reverse('plan_objetivo_crear', args=[plan.pk]), datos)
    o = plan.objetivos.get()
    assert o.origen.startswith('Tinetti 14')
    assert 'Objetivos sugeridos' not in client.get(reverse('plan_detalle', args=[plan.pk])).content.decode()


# ── Alertas ─────────────────────────────────────────────────────────

def test_alerta_sin_plan_y_revision_vencida(hogar, residente, usuarios):
    motor.evaluar_hogar(hogar)
    assert not _activas(hogar, 'plan_atencion').exists()  # recién ingresado
    Residente.objects.filter(pk=residente.pk).update(fecha_ingreso=timezone.now() - timedelta(days=40))
    residente.refresh_from_db()
    motor.evaluar_hogar(hogar)
    a = _activas(hogar, 'plan_atencion').get()
    assert 'no tiene plan' in a.titulo
    plan = _plan_listo(residente, usuarios['medico'])
    services.activar(plan, usuarios['medico'])
    motor.evaluar_hogar(hogar)
    a.refresh_from_db()
    assert a.estado == Alerta.RESUELTA
    PlanAtencion.objects.filter(pk=plan.pk).update(fecha_revision=timezone.localdate() - timedelta(days=1))
    motor.evaluar_hogar(hogar)
    assert 'revisión' in _activas(hogar, 'plan_atencion').get().titulo


# ── Pantallas y aislamiento ─────────────────────────────────────────

def test_paginas(client, residente, usuarios):
    plan = _plan_listo(residente, usuarios['medico'])
    client.force_login(usuarios['medico'])
    for url in [reverse('plan_tablero'), reverse('plan_residente', args=[residente.pk]),
                reverse('plan_detalle', args=[plan.pk]), reverse('plan_editar', args=[plan.pk]),
                reverse('plan_objetivo_crear', args=[plan.pk]),
                reverse('plan_objetivo_editar', args=[plan.objetivos.get().pk]),
                reverse('residente_detalle', args=[residente.pk])]:
        assert client.get(url).status_code == 200, url
    services.activar(plan, usuarios['medico'])
    r = client.get(reverse('plan_residente', args=[residente.pk]))
    assert r.url == reverse('plan_detalle', args=[plan.pk])
    assert 'Plan de atención' in client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()


def test_otro_hogar(client, residente, usuarios, usuario_otro_hogar):
    plan = _plan_listo(residente, usuarios['medico'])
    client.force_login(usuario_otro_hogar)
    assert client.get(reverse('plan_detalle', args=[plan.pk])).status_code == 404
    assert client.post(reverse('plan_activar', args=[plan.pk])).status_code == 404
