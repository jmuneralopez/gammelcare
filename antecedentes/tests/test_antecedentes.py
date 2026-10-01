from datetime import date

import pytest
from django.urls import reverse

from antecedentes import services
from antecedentes.models import Alergia, Antecedente, EstadoAlergias
from auditoria.models import RegistroAuditoria
from medicamentos.models import Prescripcion


def _orden(medicamento, **extra):
    from medicamentos.tests.test_lifecycle import _payload_tratamiento
    return _payload_tratamiento(medicamento, **extra)


# ── Estado de alergias ──────────────────────────────────────────────

def test_estado_sin_dato_sin_alergias_y_con_alergias(client, residente, usuarios):
    assert services.estado_alergias(residente) == 'sin_dato'
    client.force_login(usuarios['auxiliar'])
    client.post(reverse('declarar_sin_alergias', args=[residente.pk]))
    assert services.estado_alergias(residente) == 'sin_alergias'

    r = client.post(reverse('alergia_crear', args=[residente.pk]), {
        'tipo': 'alimento', 'sustancia': 'Mariscos', 'reaccion': 'erupcion', 'severidad': 'moderada', 'fuente': 'familia',
    })
    assert r.status_code == 302
    assert services.estado_alergias(residente) == 'alergias'
    assert not EstadoAlergias.objects.get(residente=residente).sin_alergias_conocidas
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.ALERGIA_REGISTRADA).exists()


def test_no_se_declara_sin_alergias_si_hay_alergias(residente, usuarios):
    Alergia.objects.create(residente=residente, sustancia='Látex', tipo='ambiental', registrado_por=usuarios['jefe'])
    with pytest.raises(ValueError):
        services.declarar_sin_alergias(residente, usuarios['jefe'])


def test_alergia_con_medicamento_toma_su_nombre(client, residente, usuarios, amoxicilina):
    client.force_login(usuarios['medico'])
    client.post(reverse('alergia_crear', args=[residente.pk]), {
        'tipo': 'alimento', 'medicamento': amoxicilina.pk, 'sustancia': '',
        'reaccion': 'anafilaxia', 'severidad': 'grave', 'fuente': 'historia',
    })
    a = Alergia.objects.get()
    assert a.sustancia == 'Amoxicilina' and a.tipo == Alergia.MEDICAMENTO and a.medicamento == amoxicilina


def test_alergia_sin_sustancia_ni_medicamento_rechazada(client, residente, usuarios):
    client.force_login(usuarios['medico'])
    r = client.post(reverse('alergia_crear', args=[residente.pk]), {
        'tipo': 'medicamento', 'sustancia': '', 'reaccion': 'desconocida', 'severidad': 'desconocida', 'fuente': 'familia',
    })
    assert r.status_code == 200 and 'sustancia' in r.context['form'].errors


# ── Coincidencias con medicamentos ──────────────────────────────────

@pytest.mark.parametrize('sustancia,coincide', [
    ('Acetaminofen', True), ('dolex', True), ('ACETAMINOFÉN', True), ('Ibuprofeno', False), ('ace', False),
])
def test_coincidencia_por_nombre(residente, usuarios, acetaminofen, sustancia, coincide):
    a = Alergia.objects.create(residente=residente, sustancia=sustancia, tipo='medicamento', registrado_por=usuarios['jefe'])
    assert a.coincide_con(acetaminofen) is coincide


def test_alergia_alimentaria_no_coincide_con_medicamento(residente, usuarios, acetaminofen):
    a = Alergia.objects.create(residente=residente, sustancia='Acetaminofén', tipo='alimento', registrado_por=usuarios['jefe'])
    assert not a.coincide_con(acetaminofen)


def test_alergia_inactiva_no_coincide(residente, usuarios, amoxicilina):
    a = Alergia.objects.create(residente=residente, sustancia='Amoxicilina', medicamento=amoxicilina,
                               tipo='medicamento', registrado_por=usuarios['jefe'])
    a.inactivar(usuarios['medico'], 'Descartada')
    assert services.conflictos_alergia(residente, amoxicilina) == []


# ── Aviso al registrar una orden médica ─────────────────────────────

def test_orden_medica_con_alergia_exige_confirmacion(client, residente, usuarios, amoxicilina):
    Alergia.objects.create(residente=residente, sustancia='Amoxicilina', medicamento=amoxicilina,
                           tipo='medicamento', severidad='grave', registrado_por=usuarios['jefe'])
    client.force_login(usuarios['medico'])
    r = client.post(reverse('tratamiento_crear', args=[residente.pk]), _orden(amoxicilina))
    assert r.status_code == 200
    assert 'alergia a Amoxicilina' in r.content.decode()
    assert not Prescripcion.objects.exists()

    r = client.post(reverse('tratamiento_crear', args=[residente.pk]), _orden(amoxicilina, confirmar_alergia='on'))
    assert r.status_code == 302 and Prescripcion.objects.count() == 1
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.ORDEN_PESE_A_ALERGIA).exists()


def test_orden_medica_sin_alergia_no_pide_confirmacion(client, residente, usuarios, acetaminofen):
    client.force_login(usuarios['medico'])
    r = client.post(reverse('tratamiento_crear', args=[residente.pk]), _orden(acetaminofen))
    assert r.status_code == 302
    assert not RegistroAuditoria.objects.filter(accion=RegistroAuditoria.ORDEN_PESE_A_ALERGIA).exists()


# ── Inactivar ───────────────────────────────────────────────────────

@pytest.mark.parametrize('rol,puede', [('medico', True), ('jefe', True), ('auxiliar', False), ('administrador', False)])
def test_inactivar_alergia_por_rol(client, residente, usuarios, rol, puede):
    a = Alergia.objects.create(residente=residente, sustancia='Látex', tipo='ambiental', registrado_por=usuarios['jefe'])
    client.force_login(usuarios[rol])
    client.post(reverse('alergia_inactivar', args=[a.pk]), {'motivo': 'Registrada por error'})
    a.refresh_from_db()
    assert (not a.activo) is puede


def test_inactivar_exige_motivo_y_no_borra(client, residente, usuarios):
    a = Alergia.objects.create(residente=residente, sustancia='Látex', tipo='ambiental', registrado_por=usuarios['jefe'])
    client.force_login(usuarios['medico'])
    client.post(reverse('alergia_inactivar', args=[a.pk]), {'motivo': ''})
    a.refresh_from_db()
    assert a.activo
    with pytest.raises(ValueError):
        a.delete()


def test_antecedente_registrar_e_inactivar(client, residente, usuarios):
    client.force_login(usuarios['nutricionista'])
    r = client.post(reverse('antecedente_crear', args=[residente.pk]), {
        'tipo': 'patologico', 'descripcion': 'Diabetes mellitus tipo 2', 'cuando': '2010', 'observaciones': '',
    })
    assert r.status_code == 302
    ant = Antecedente.objects.get()
    client.force_login(usuarios['jefe'])
    client.post(reverse('antecedente_inactivar', args=[ant.pk]), {'motivo': 'Duplicado'})
    ant.refresh_from_db()
    assert not ant.activo and ant.inactivado_por == usuarios['jefe']


# ── Pantallas y aislamiento ─────────────────────────────────────────

def test_pantallas_renderizan(client, residente, usuarios, amoxicilina):
    Alergia.objects.create(residente=residente, sustancia='Penicilina', tipo='medicamento',
                           severidad='grave', registrado_por=usuarios['jefe'])
    client.force_login(usuarios['medico'])
    for nombre in ['residente_antecedentes', 'alergia_crear', 'antecedente_crear', 'residente_detalle', 'hoja_dia', 'tratamiento_crear']:
        r = client.get(reverse(nombre, args=[residente.pk]))
        assert r.status_code == 200, nombre
        if nombre in ('residente_detalle', 'hoja_dia', 'tratamiento_crear'):
            assert 'Penicilina' in r.content.decode(), nombre


def test_otro_hogar_no_ve_ni_registra(client, residente, medico_otro_hogar, usuarios):
    a = Alergia.objects.create(residente=residente, sustancia='Látex', tipo='ambiental', registrado_por=usuarios['jefe'])
    client.force_login(medico_otro_hogar)
    assert client.get(reverse('residente_antecedentes', args=[residente.pk])).status_code == 404
    assert client.post(reverse('alergia_inactivar', args=[a.pk]), {'motivo': 'x'}).status_code == 404


# ── EPS y ambulancia desde el formulario del residente ──────────────

def test_alta_rapida_eps_y_ambulancia(client, usuarios):
    from catalogos.models import EPS, ServicioAmbulancia
    client.force_login(usuarios['administrador'])
    r = client.post(reverse('eps_crear_rapido'), {'nombre': 'Nueva EPS', 'codigo': 'EPS037', 'telefono': '123'})
    assert r.status_code == 200 and r.json()['text'] == 'Nueva EPS'
    assert EPS.objects.filter(nombre='Nueva EPS', codigo='EPS037').exists()
    assert client.post(reverse('eps_crear_rapido'), {'nombre': 'nueva eps'}).status_code == 400
    r = client.post(reverse('ambulancia_crear_rapido'), {'nombre': 'Ambulancias Vida', 'telefono': '456'})
    assert r.status_code == 200 and ServicioAmbulancia.objects.filter(nombre='Ambulancias Vida').exists()
    assert client.post(reverse('ambulancia_crear_rapido'), {'nombre': ''}).status_code == 400
    assert client.get(reverse('eps_crear_rapido')).status_code == 405


def test_alta_rapida_eps_solo_administrador(client, usuarios):
    from catalogos.models import EPS
    client.force_login(usuarios['medico'])
    client.post(reverse('eps_crear_rapido'), {'nombre': 'EPS X'})
    assert not EPS.objects.filter(nombre='EPS X').exists()


def test_formulario_residente_muestra_alta_rapida(client, usuarios):
    client.force_login(usuarios['administrador'])
    html = client.get(reverse('residente_crear')).content.decode()
    assert '¿La EPS no está en la lista? Agregarla' in html
    assert '¿El servicio no está en la lista? Agregarlo' in html
