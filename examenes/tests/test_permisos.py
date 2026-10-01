"""Quién puede hacer qué en el módulo de exámenes, y aislamiento por hogar."""
from datetime import date

import pytest
from django.urls import reverse

from examenes import services
from examenes.models import Examen


def _llega(respuesta):
    """True si la vista respondió (no redirigió al dashboard por permisos)."""
    return respuesta.status_code == 200


@pytest.mark.parametrize('rol,puede', [
    ('administrador', True), ('medico', True), ('jefe', True), ('auxiliar', True), ('fisioterapeuta', False),
])
def test_registrar_examen(client, residente, usuarios, rol, puede):
    client.force_login(usuarios[rol])
    assert _llega(client.get(reverse('examen_crear', args=[residente.pk]))) is puede


@pytest.mark.parametrize('rol,puede', [
    ('administrador', True), ('medico', True), ('jefe', True), ('auxiliar', True), ('fisioterapeuta', False),
])
def test_cargar_resultado(client, examen_pendiente, usuarios, rol, puede):
    client.force_login(usuarios[rol])
    assert _llega(client.get(reverse('examen_resultado', args=[examen_pendiente.pk]))) is puede


@pytest.mark.parametrize('rol,puede', [
    ('administrador', False), ('medico', True), ('jefe', False), ('auxiliar', False), ('fisioterapeuta', False),
])
def test_revisar_solo_medico(client, examen_pendiente, usuarios, rol, puede):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), conclusion='Normal')
    client.force_login(usuarios[rol])
    respuesta = client.post(reverse('examen_revisar', args=[examen_pendiente.pk]), {'conducta': 'Ok'})
    examen_pendiente.refresh_from_db()
    assert (examen_pendiente.estado == Examen.REVISADO) is puede
    assert respuesta.status_code == 302


@pytest.mark.parametrize('rol', ['administrador', 'medico', 'jefe', 'auxiliar', 'fisioterapeuta'])
def test_consultar_todos_los_clinicos(client, examen_pendiente, usuarios, rol):
    client.force_login(usuarios[rol])
    assert _llega(client.get(reverse('examen_detalle', args=[examen_pendiente.pk])))
    assert _llega(client.get(reverse('examenes_bandeja')))


def test_superadmin_no_opera_examenes(client, superadmin, examen_pendiente):
    client.force_login(superadmin)
    assert not _llega(client.get(reverse('examenes_bandeja')))
    assert not _llega(client.get(reverse('examen_detalle', args=[examen_pendiente.pk])))


def test_anonimo_redirige_al_login(client, examen_pendiente):
    respuesta = client.get(reverse('examen_detalle', args=[examen_pendiente.pk]))
    assert respuesta.status_code == 302 and 'login' in respuesta.url


def test_aislamiento_entre_hogares(client, medico_otro_hogar, examen_pendiente, residente, usuarios, pdf):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), archivos=[pdf])
    archivo = examen_pendiente.archivos.get()
    client.force_login(medico_otro_hogar)
    for nombre, args in [
        ('examen_detalle', [examen_pendiente.pk]), ('examen_revisar', [examen_pendiente.pk]),
        ('archivo_ver', [archivo.pk]), ('examenes_residente', [residente.pk]),
        ('examenes_tendencias', [residente.pk]), ('examen_crear', [residente.pk]),
    ]:
        assert client.get(reverse(nombre, args=args)).status_code == 404, nombre
    bandeja = client.get(reverse('examenes_bandeja'))
    assert examen_pendiente not in bandeja.context['pendientes'] + bandeja.context['por_revisar']


def test_cancelar_requiere_post(client, examen_pendiente, usuarios):
    client.force_login(usuarios['auxiliar'])
    assert client.get(reverse('examen_cancelar', args=[examen_pendiente.pk])).status_code == 405
