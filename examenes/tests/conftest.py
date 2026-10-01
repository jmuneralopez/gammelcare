"""Fixtures del módulo de exámenes: un hogar con un usuario por rol, un
residente, y un segundo hogar para probar el aislamiento entre hogares.
Los archivos van a una carpeta temporal por prueba."""
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from examenes.models import AnalitoCatalogo, Examen
from hogares.models import Hogar
from residentes.models import Residente
from usuarios.models import Rol, Usuario

PDF_MINIMO = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
PNG_MINIMO = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


@pytest.fixture(autouse=True)
def media_privada_temporal(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = str(tmp_path / 'media_privada')
    return settings.PRIVATE_MEDIA_ROOT


def _usuario(hogar, username, *roles):
    u = Usuario.objects.create_user(
        username=username, password='clave-de-prueba-123', hogar=hogar,
        first_name=username.title(), last_name='Prueba',
    )
    for nombre in roles:
        rol, _ = Rol.objects.get_or_create(nombre=nombre)
        u.roles.add(rol)
    return u


def _residente(hogar, nombre='Residente de Prueba'):
    r = Residente(hogar=hogar, fecha_nacimiento=date(1944, 5, 2), tipo_documento='CC')
    r.set_nombre(nombre)
    r.set_documento('987654321')
    r.set_contacto('3000000000')
    r.save()
    return r


@pytest.fixture
def hogar(db):
    return Hogar.objects.create(nombre='Hogar Uno', nit='900000001-1', direccion='Calle 1')


@pytest.fixture
def otro_hogar(db):
    return Hogar.objects.create(nombre='Hogar Dos', nit='900000002-2', direccion='Calle 2')


@pytest.fixture
def usuarios(hogar):
    return {
        'administrador': _usuario(hogar, 'admin', Rol.ADMINISTRADOR),
        'medico': _usuario(hogar, 'medico', Rol.MEDICO),
        'jefe': _usuario(hogar, 'jefe', Rol.JEFE_ENFERMERIA),
        'auxiliar': _usuario(hogar, 'auxiliar', Rol.ENFERMERO),
        'fisioterapeuta': _usuario(hogar, 'fisio', Rol.FISIOTERAPEUTA),
    }


@pytest.fixture
def superadmin(db):
    u = Usuario.objects.create_user(username='super', password='clave-de-prueba-123')
    rol, _ = Rol.objects.get_or_create(nombre=Rol.SUPERADMIN)
    u.roles.add(rol)
    return u


@pytest.fixture
def residente(hogar):
    return _residente(hogar)


@pytest.fixture
def residente_otro_hogar(otro_hogar):
    return _residente(otro_hogar, 'Residente Ajeno')


@pytest.fixture
def medico_otro_hogar(otro_hogar):
    return _usuario(otro_hogar, 'medico2', Rol.MEDICO)


@pytest.fixture
def glucosa(db):
    return AnalitoCatalogo.objects.get(codigo='glucosa')


@pytest.fixture
def examen_pendiente(residente, usuarios):
    return Examen.objects.create(
        residente=residente, nombre='Glucosa y hemograma', ordenado_por='Dra. Prueba',
        fecha_orden=date.today(), registrado_por=usuarios['auxiliar'],
    )


@pytest.fixture
def pdf():
    return SimpleUploadedFile('resultado.pdf', PDF_MINIMO, content_type='application/pdf')


@pytest.fixture
def png():
    return SimpleUploadedFile('foto.png', PNG_MINIMO, content_type='image/png')
