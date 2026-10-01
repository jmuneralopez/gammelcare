from citas.tests.conftest import (  # noqa: F401
    _usuario, crear_residente, hogar, media_privada, otro_hogar, residente, usuario_otro_hogar, usuarios,
)
import pytest

from usuarios.models import Rol


@pytest.fixture
def nutricionista(hogar):
    return _usuario(hogar, 'nutri', Rol.NUTRICIONISTA)
