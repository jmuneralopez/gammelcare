from datetime import date, timedelta

import pytest

from citas.tests.conftest import (  # noqa: F401
    _usuario, crear_residente, hogar, media_privada, otro_hogar, residente, usuario_otro_hogar, usuarios,
)
from medicamentos.models import Medicamento


@pytest.fixture
def medicamento(db):
    return Medicamento.objects.create(nombre_generico='Losartán', concentracion='50 mg',
                                      forma_farmaceutica='tableta', unidad_dosificacion='tableta')


@pytest.fixture
def ayer():
    return date.today() - timedelta(days=1)
