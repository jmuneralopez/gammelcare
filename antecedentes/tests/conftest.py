from datetime import date

import pytest

from hogares.models import Hogar
from medicamentos.models import Medicamento
from residentes.models import Residente
from usuarios.models import Rol, Usuario


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
        'nutricionista': _usuario(hogar, 'nutri', Rol.NUTRICIONISTA),
    }


@pytest.fixture
def medico_otro_hogar(otro_hogar):
    return _usuario(otro_hogar, 'medico2', Rol.MEDICO)


@pytest.fixture
def residente(hogar):
    r = Residente(hogar=hogar, fecha_nacimiento=date(1941, 2, 3))
    r.set_nombre('Residente Alergias')
    r.set_documento('111')
    r.set_contacto('300')
    r.save()
    return r


@pytest.fixture
def amoxicilina(db):
    return Medicamento.objects.create(nombre_generico='Amoxicilina', concentracion='500 mg',
                                      forma_farmaceutica='capsula', unidad_dosificacion='tableta')


@pytest.fixture
def acetaminofen(db):
    return Medicamento.objects.create(nombre_generico='Acetaminofén', nombre_comercial='Dolex',
                                      concentracion='500 mg', forma_farmaceutica='tableta',
                                      unidad_dosificacion='tableta')
