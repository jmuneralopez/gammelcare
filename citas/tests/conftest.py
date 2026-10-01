from datetime import date

import pytest

from hogares.models import Hogar
from residentes.models import Residente
from usuarios.models import Rol, Usuario


@pytest.fixture(autouse=True)
def media_privada(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = str(tmp_path / 'privada')


def _usuario(hogar, username, *roles):
    u = Usuario.objects.create_user(username=username, password='clave-prueba-123', hogar=hogar,
                                    first_name=username.title(), last_name='Prueba')
    for r in roles:
        u.roles.add(Rol.objects.get_or_create(nombre=r)[0])
    return u


@pytest.fixture
def hogar(db):
    return Hogar.objects.create(nombre='Hogar A', nit='800-1', direccion='Calle 1')


@pytest.fixture
def otro_hogar(db):
    return Hogar.objects.create(nombre='Hogar B', nit='800-2', direccion='Calle 2')


@pytest.fixture
def usuarios(hogar):
    return {
        'administrador': _usuario(hogar, 'admin', Rol.ADMINISTRADOR),
        'medico': _usuario(hogar, 'medico', Rol.MEDICO),
        'jefe': _usuario(hogar, 'jefe', Rol.JEFE_ENFERMERIA),
        'auxiliar': _usuario(hogar, 'auxiliar', Rol.ENFERMERO),
        'social': _usuario(hogar, 'social', Rol.TRABAJO_SOCIAL),
        'fisio': _usuario(hogar, 'fisio', Rol.FISIOTERAPEUTA),
    }


@pytest.fixture
def usuario_otro_hogar(otro_hogar):
    return _usuario(otro_hogar, 'jefe2', Rol.JEFE_ENFERMERIA)


def crear_residente(hogar, nombre='Residente Citas'):
    r = Residente(hogar=hogar, fecha_nacimiento=date(1940, 5, 6))
    r.set_nombre(nombre)
    r.set_documento('222')
    r.set_contacto('300')
    r.save()
    return r


@pytest.fixture
def residente(hogar):
    return crear_residente(hogar)
