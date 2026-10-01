from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from citas import services
from citas.models import Cita

FMT = '%Y-%m-%dT%H:%M'
PDF = b'%PDF-1.4\n%%EOF\n'


def _datos(**extra):
    datos = {
        'tipo': 'especialista', 'especialidad': 'Cardiología', 'profesional': 'Dr. Ramírez',
        'lugar': 'Clínica X, consultorio 3', 'fecha_hora': timezone.localtime(timezone.now() + timedelta(days=2)).strftime(FMT),
        'requiere_ayuno': 'on', 'preparacion': 'Ayuno de 8 horas', 'acompanante': 'Hija',
        'transporte': 'familia', 'observaciones': '',
    }
    datos.update(extra)
    return datos


def _cita(residente, usuario, **extra):
    campos = dict(residente=residente, tipo='control', lugar='EPS', fecha_hora=timezone.now() + timedelta(days=1),
                  registrado_por=usuario)
    campos.update(extra)
    return Cita.objects.create(**campos)


def test_auxiliar_agenda_cita_y_queda_auditada(client, residente, usuarios):
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('cita_crear', args=[residente.pk]), _datos())
    assert r.status_code == 302
    cita = Cita.objects.get()
    assert cita.estado == Cita.PROGRAMADA and cita.requiere_ayuno and cita.registrado_por == usuarios['auxiliar']
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.CITA_REGISTRADA).exists()


def test_no_se_agenda_en_el_pasado(client, residente, usuarios):
    client.force_login(usuarios['jefe'])
    pasada = timezone.localtime(timezone.now() - timedelta(days=1)).strftime(FMT)
    r = client.post(reverse('cita_crear', args=[residente.pk]), _datos(fecha_hora=pasada))
    assert r.status_code == 200 and 'fecha_hora' in r.context['form'].errors
    assert not Cita.objects.exists()


def test_fisioterapeuta_ve_pero_no_agenda(client, residente, usuarios):
    client.force_login(usuarios['fisio'])
    assert client.get(reverse('citas_residente', args=[residente.pk])).status_code == 200
    assert client.get(reverse('citas_agenda')).status_code == 200
    r = client.post(reverse('cita_crear', args=[residente.pk]), _datos())
    assert r.status_code == 302 and not Cita.objects.exists()


def test_cerrar_cumplida_con_soporte_privado(client, residente, usuarios, settings):
    cita = _cita(residente, usuarios['jefe'], fecha_hora=timezone.now() - timedelta(hours=3))
    client.force_login(usuarios['social'])
    archivo = SimpleUploadedFile('resumen.pdf', PDF, content_type='application/pdf')
    r = client.post(reverse('cita_cerrar', args=[cita.pk]), {'estado': 'cumplida', 'resumen': 'Control sin cambios', 'archivo': archivo})
    assert r.status_code == 302
    cita.refresh_from_db()
    assert cita.estado == Cita.CUMPLIDA and cita.cerrada_por == usuarios['social']
    assert cita.archivo_soporte.path.startswith(settings.PRIVATE_MEDIA_ROOT)
    r = client.get(reverse('cita_soporte_ver', args=[cita.pk]))
    assert r.status_code == 200 and b''.join(r.streaming_content) == PDF
    assert r['Cache-Control'] == 'private, no-store'


def test_no_se_cierra_una_cita_futura(residente, usuarios):
    cita = _cita(residente, usuarios['jefe'], fecha_hora=timezone.now() + timedelta(days=3))
    with pytest.raises(ValidationError):
        services.cerrar(cita, usuarios['jefe'], Cita.CUMPLIDA, 'x')


def test_cerrar_exige_resumen(client, residente, usuarios):
    cita = _cita(residente, usuarios['jefe'], fecha_hora=timezone.now() - timedelta(hours=1))
    client.force_login(usuarios['jefe'])
    r = client.post(reverse('cita_cerrar', args=[cita.pk]), {'estado': 'no_asistio', 'resumen': ''})
    assert r.status_code == 400
    cita.refresh_from_db()
    assert cita.abierta


def test_reprogramar_crea_cita_enlazada(client, residente, usuarios):
    cita = _cita(residente, usuarios['jefe'], especialidad='Ortopedia', requiere_ayuno=True)
    client.force_login(usuarios['jefe'])
    nueva_fecha = timezone.localtime(timezone.now() + timedelta(days=10)).replace(second=0, microsecond=0)
    r = client.post(reverse('cita_reprogramar', args=[cita.pk]), {'fecha_hora': nueva_fecha.strftime(FMT), 'motivo': 'La EPS la movió', 'lugar': ''})
    assert r.status_code == 302
    cita.refresh_from_db()
    nueva = cita.reprogramada_en
    assert cita.estado == Cita.REPROGRAMADA and cita.resumen == 'La EPS la movió'
    assert nueva.abierta and nueva.especialidad == 'Ortopedia' and nueva.requiere_ayuno
    assert nueva.fecha_hora == nueva_fecha


def test_cancelar_y_no_se_borra(client, residente, usuarios):
    cita = _cita(residente, usuarios['jefe'])
    client.force_login(usuarios['administrador'])
    client.post(reverse('cita_cancelar', args=[cita.pk]), {'motivo': 'Hospitalizado'})
    cita.refresh_from_db()
    assert cita.estado == Cita.CANCELADA
    with pytest.raises(ValueError):
        cita.delete()
    with pytest.raises(ValidationError):
        services.cancelar(cita, usuarios['jefe'], 'otra vez')


def test_solo_se_corrigen_citas_programadas(client, residente, usuarios):
    cita = _cita(residente, usuarios['jefe'])
    client.force_login(usuarios['jefe'])
    r = client.post(reverse('cita_editar', args=[cita.pk]), _datos(lugar='Nuevo lugar'))
    assert r.status_code == 302
    cita.refresh_from_db()
    assert cita.lugar == 'Nuevo lugar'
    services.cancelar(cita, usuarios['jefe'], 'x')
    client.post(reverse('cita_editar', args=[cita.pk]), _datos(lugar='Otro'))
    cita.refresh_from_db()
    assert cita.lugar == 'Nuevo lugar'


def test_agenda_muestra_proximas_y_sin_cierre(client, residente, usuarios):
    _cita(residente, usuarios['jefe'], especialidad='Dermatología', fecha_hora=timezone.now() + timedelta(days=1))
    _cita(residente, usuarios['jefe'], especialidad='Neurología', fecha_hora=timezone.now() - timedelta(days=2))
    _cita(residente, usuarios['jefe'], especialidad='Urología', fecha_hora=timezone.now() + timedelta(days=20))
    client.force_login(usuarios['jefe'])
    html = client.get(reverse('citas_agenda')).content.decode()
    assert 'Dermatología' in html and 'Neurología' in html and 'Urología' not in html
    html = client.get(reverse('citas_agenda') + '?dias=30').content.decode()
    assert 'Urología' in html


def test_expediente_muestra_citas(client, residente, usuarios):
    _cita(residente, usuarios['jefe'], especialidad='Oftalmología')
    client.force_login(usuarios['medico'])
    html = client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()
    assert 'Citas médicas' in html and 'Oftalmología' in html and 'Agendar cita' in html


def test_otro_hogar_no_ve_la_cita(client, residente, usuarios, usuario_otro_hogar):
    cita = _cita(residente, usuarios['jefe'])
    client.force_login(usuario_otro_hogar)
    assert client.get(reverse('cita_detalle', args=[cita.pk])).status_code == 404
    assert client.get(reverse('citas_residente', args=[residente.pk])).status_code == 404
