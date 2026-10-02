import pytest

from citas.tests.conftest import (  # noqa: F401
    _usuario, crear_residente, hogar, media_privada, otro_hogar, residente, usuario_otro_hogar, usuarios,
)
from usuarios.models import Rol


@pytest.fixture
def psicologo(hogar):
    return _usuario(hogar, 'psico', Rol.PSICOLOGO)
