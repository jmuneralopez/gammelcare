"""Foto de la fórmula en almacenamiento privado y enlace al botiquín."""
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from hogares.models import Hogar
from medicamentos.models import Prescripcion
from usuarios.models import Rol, Usuario

PDF = b'%PDF-1.4\n%%EOF\n'


@pytest.fixture(autouse=True)
def media_privada(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = str(tmp_path / 'privada')


def _datos_orden(medicamento, **extra):
    from medicamentos.tests.test_lifecycle import _payload_tratamiento
    return _payload_tratamiento(medicamento, **extra)


def test_formula_se_guarda_en_privado_y_se_sirve_con_auditoria(client, usuario_medico, usuario_fisioterapeuta,
                                                               residente, medicamento, settings):
    client.force_login(usuario_medico)
    archivo = SimpleUploadedFile('formula.pdf', PDF, content_type='application/pdf')
    r = client.post(reverse('tratamiento_crear', args=[residente.pk]), _datos_orden(medicamento, archivo_formula=archivo))
    p = Prescripcion.objects.get()
    assert r.status_code == 302, r.context['form'].errors if r.context else r
    assert p.archivo_formula.name.startswith(f'medicamentos/formulas/hogar_{residente.hogar_id}/')
    assert p.archivo_formula.path.startswith(settings.PRIVATE_MEDIA_ROOT)
    with pytest.raises(NotImplementedError):
        p.archivo_formula.url  # no tiene URL pública

    client.force_login(usuario_fisioterapeuta)
    r = client.get(reverse('tratamiento_formula_ver', args=[p.pk]))
    assert r.status_code == 200 and b''.join(r.streaming_content) == PDF
    assert r['X-Content-Type-Options'] == 'nosniff'
    assert RegistroAuditoria.objects.filter(descripcion__contains=f'orden médica #{p.pk}').exists()


def test_formula_falsa_rechazada(client, usuario_medico, residente, medicamento):
    client.force_login(usuario_medico)
    falso = SimpleUploadedFile('formula.pdf', b'MZ no es pdf', content_type='application/pdf')
    r = client.post(reverse('tratamiento_crear', args=[residente.pk]), _datos_orden(medicamento, archivo_formula=falso))
    assert r.status_code == 200 and 'archivo_formula' in r.context['form'].errors
    assert not Prescripcion.objects.exists()


def test_formula_de_otro_hogar_no_se_ve(client, usuario_medico, residente, medicamento):
    client.force_login(usuario_medico)
    archivo = SimpleUploadedFile('formula.pdf', PDF, content_type='application/pdf')
    client.post(reverse('tratamiento_crear', args=[residente.pk]), _datos_orden(medicamento, archivo_formula=archivo))
    p = Prescripcion.objects.get()
    otro = Hogar.objects.create(nombre='Otro', nit='1-9', direccion='x')
    ajeno = Usuario.objects.create_user('ajeno', password='x12345678', hogar=otro)
    ajeno.roles.add(Rol.objects.get_or_create(nombre=Rol.MEDICO)[0])
    client.force_login(ajeno)
    assert client.get(reverse('tratamiento_formula_ver', args=[p.pk])).status_code == 404


@pytest.mark.parametrize('fixture,ve', [
    ('usuario_administrador', True), ('usuario_jefe_enfermeria', True), ('usuario_enfermero', True),
    ('usuario_medico', False), ('usuario_fisioterapeuta', False),
])
def test_enlace_botiquin_en_el_menu(client, request, fixture, ve):
    client.force_login(request.getfixturevalue(fixture))
    html = client.get(reverse('dashboard')).content.decode()
    assert (reverse('botiquin_lista') in html) is ve
