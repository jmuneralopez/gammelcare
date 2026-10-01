"""Quién puede ver y quién puede usar cada botón del módulo — la parte que
Juan Carlos pidió revisar explícitamente ("hay roles que no pueden
suministrar medicamentos, por ejemplo"). Cubre tanto el permiso de la URL
(el decorador) como las banderas de contexto que controlan si el botón se
pinta en la plantilla (puede_registrar_tratamiento, puede_registrar_ingreso).
"""
from datetime import date

import pytest
from django.urls import reverse

from medicamentos.models import Prescripcion

pytestmark = pytest.mark.django_db


# ── Vistas de solo lectura (GET) protegidas por rol ──────────────────

@pytest.mark.parametrize('rol_fixture, permitido', [
    ('usuario_administrador', True),
    ('usuario_medico', True),
    ('usuario_jefe_enfermeria', True),
    ('usuario_enfermero', False),
    ('usuario_fisioterapeuta', False),
])
def test_solo_quien_puede_formular_ve_el_formulario_de_tratamiento(
    client, request, residente, rol_fixture, permitido
):
    usuario = request.getfixturevalue(rol_fixture)
    client.force_login(usuario)
    resp = client.get(reverse('tratamiento_crear', args=[residente.pk]))
    if permitido:
        assert resp.status_code == 200
    else:
        assert resp.status_code == 302
        assert resp.url == reverse('dashboard')


@pytest.mark.parametrize('rol_fixture, permitido', [
    ('usuario_administrador', True),
    ('usuario_jefe_enfermeria', True),
    ('usuario_enfermero', True),
    ('usuario_medico', False),
    ('usuario_fisioterapeuta', False),
])
def test_solo_quien_puede_recibir_medicamentos_ve_el_formulario_de_ingreso(
    client, request, residente, rol_fixture, permitido
):
    usuario = request.getfixturevalue(rol_fixture)
    client.force_login(usuario)
    resp = client.get(reverse('ingreso_crear', args=[residente.pk]))
    if permitido:
        assert resp.status_code == 200
    else:
        assert resp.status_code == 302
        assert resp.url == reverse('dashboard')


@pytest.mark.parametrize('rol_fixture, permitido', [
    ('usuario_administrador', True),
    ('usuario_jefe_enfermeria', True),
    ('usuario_enfermero', True),
    ('usuario_medico', False),
    ('usuario_fisioterapeuta', False),
])
def test_botiquin_usa_el_mismo_permiso_que_ingreso(
    client, request, hogar, rol_fixture, permitido
):
    """Ver medicamentos/views.py::botiquin_lista — usa
    ingreso_medicamento_requerido a propósito, para no dejar al auxiliar
    de enfermería en un callejón sin salida después de registrar un
    ingreso al botiquín (bug ya corregido)."""
    usuario = request.getfixturevalue(rol_fixture)
    client.force_login(usuario)
    resp = client.get(reverse('botiquin_lista'))
    if permitido:
        assert resp.status_code == 200
    else:
        assert resp.status_code == 302
        assert resp.url == reverse('dashboard')


def test_usuario_sin_hogar_queda_bloqueado_antes_de_entrar(client, usuario_sin_hogar, residente):
    client.force_login(usuario_sin_hogar)
    resp = client.get(reverse('tratamiento_crear', args=[residente.pk]))
    assert resp.status_code == 302
    assert resp.url == reverse('dashboard')


# ── Botones que solo deben pintarse para quien realmente puede usarlos ──
# (bug ya corregido: antes se veían para roles que luego topaban con "no
# tienes permisos" al hacer clic)

def test_boton_registrar_tratamiento_no_aparece_para_quien_no_puede_usarlo(
    client, usuario_enfermero, residente
):
    client.force_login(usuario_enfermero)
    resp = client.get(reverse('tratamiento_lista', args=[residente.pk]))
    assert resp.status_code == 200
    assert resp.context['puede_registrar_tratamiento'] is False
    assert b'Registrar tratamiento' not in resp.content


def test_boton_registrar_tratamiento_aparece_para_quien_si_puede(
    client, usuario_medico, residente
):
    client.force_login(usuario_medico)
    resp = client.get(reverse('tratamiento_lista', args=[residente.pk]))
    assert resp.status_code == 200
    assert resp.context['puede_registrar_tratamiento'] is True
    assert b'Registrar tratamiento' in resp.content


def test_boton_registrar_ingreso_no_aparece_para_quien_no_puede_usarlo(
    client, usuario_medico, residente
):
    client.force_login(usuario_medico)
    resp = client.get(reverse('ingreso_lista', args=[residente.pk]))
    assert resp.status_code == 200
    assert resp.context['puede_registrar_ingreso'] is False


def test_boton_registrar_ingreso_aparece_para_quien_si_puede(
    client, usuario_enfermero, residente
):
    client.force_login(usuario_enfermero)
    resp = client.get(reverse('ingreso_lista', args=[residente.pk]))
    assert resp.status_code == 200
    assert resp.context['puede_registrar_ingreso'] is True


# ── Administrar / suspender: el administrador NUNCA toca al residente ──

def test_administrador_no_puede_administrar_medicamentos(
    client, usuario_administrador, prescripcion_horarios_fijos, ingreso_residente
):
    """Principio central del módulo (plan 4.1): el administrador registra
    y custodia, pero nunca ejecuta el acto clínico de dar el medicamento."""
    client.force_login(usuario_administrador)
    horario = prescripcion_horarios_fijos.horarios.first()
    resp = client.post(
        reverse('administracion_registrar', args=[prescripcion_horarios_fijos.pk, horario.pk]),
        data={'fecha': date.today().isoformat(), 'cantidad_administrada': '1', 'observacion': ''},
    )
    assert resp.status_code == 302
    assert resp.url == reverse('dashboard')
    assert not prescripcion_horarios_fijos.administraciones.exists()


def test_enfermero_no_puede_suspender_un_tratamiento(
    client, usuario_enfermero, prescripcion_horarios_fijos
):
    """Suspender es parte de REGISTRAR el tratamiento formulado
    (administrador, médico, jefe de enfermería) — el auxiliar de
    enfermería administra pero no decide suspender la fórmula."""
    client.force_login(usuario_enfermero)
    resp = client.post(
        reverse('tratamiento_suspender', args=[prescripcion_horarios_fijos.pk]),
        data={'motivo_suspension': 'Intento no autorizado'},
    )
    assert resp.status_code == 302
    assert resp.url == reverse('dashboard')
    prescripcion_horarios_fijos.refresh_from_db()
    assert prescripcion_horarios_fijos.estado == Prescripcion.ACTIVA
