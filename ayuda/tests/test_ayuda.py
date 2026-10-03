import pytest
from django.urls import reverse

from ayuda import secciones as S
from citas.tests.conftest import (  # noqa: F401
    _usuario, crear_residente, hogar, media_privada, otro_hogar, residente, usuario_otro_hogar, usuarios,
)


def test_todas_las_pantallas_mapeadas_existen():
    from django.urls import get_resolver
    nombres = {k for k in get_resolver().reverse_dict.keys() if isinstance(k, str)}
    for url in S.SECCION_POR_PANTALLA:
        assert url in nombres, url
    assert {s.codigo for s in S.todas()} == set(S.PANTALLAS)


def test_ayuda_segun_el_rol(client, residente, usuarios):
    client.force_login(usuarios['auxiliar'])
    html = client.get(reverse('signos_residente', args=[residente.pk])).content.decode()
    assert '¿Qué puedo hacer aquí?' in html and 'Ayuda: Signos vitales' in html
    puede = html.split('Usted puede')[1].split('Lo hacen otros roles')[0]
    otros = html.split('Lo hacen otros roles')[1]
    assert 'Registrar signos vitales y peso' in puede
    assert 'Ajustar el rango normal de un residente' in otros and 'Médico' in otros

    client.force_login(usuarios['medico'])
    html = client.get(reverse('signos_residente', args=[residente.pk])).content.decode()
    puede = html.split('Usted puede')[1].split('Para tener en cuenta')[0].split('Lo hacen otros roles')[0]
    assert 'Ajustar el rango normal de un residente' in puede


@pytest.mark.parametrize('url', ['plan_tablero', 'valoracion_tablero', 'citas_agenda', 'alertas_bandeja', 'examenes_bandeja'])
def test_ayuda_en_cada_seccion(client, usuarios, url):
    client.force_login(usuarios['jefe'])
    assert '¿Qué puedo hacer aquí?' in client.get(reverse(url)).content.decode()


def test_sin_ayuda_en_pantallas_sin_seccion(client, usuarios):
    client.force_login(usuarios['jefe'])
    assert '¿Qué puedo hacer aquí?' not in client.get(reverse('dashboard')).content.decode()
