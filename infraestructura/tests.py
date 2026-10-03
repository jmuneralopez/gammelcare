import pytest
from django.urls import reverse

from citas.tests.conftest import (  # noqa: F401
    _usuario, crear_residente, hogar, media_privada, otro_hogar, residente, usuario_otro_hogar, usuarios,
)
from infraestructura.models import Cama, Departamento, Habitacion
from residentes.models import Residente


@pytest.fixture
def estructura(hogar):
    dep = Departamento.objects.create(hogar=hogar, nombre='Pabellón A')
    hab = Habitacion.objects.create(departamento=dep, numero='101')
    c1 = Cama.objects.create(habitacion=hab, codigo='A', estado=Cama.OCUPADA)
    c2 = Cama.objects.create(habitacion=hab, codigo='B')
    return dep, hab, c1, c2


def test_todos_los_roles_ven_la_institucion_con_el_residente_de_cada_cama(client, usuarios, residente, estructura):
    dep, hab, c1, c2 = estructura
    Residente.objects.filter(pk=residente.pk).update(cama_actual=c1)
    for rol in ('auxiliar', 'fisio', 'medico', 'administrador'):
        client.force_login(usuarios[rol])
        r = client.get(reverse('institucion'))
        html = r.content.decode()
        assert r.status_code == 200
        assert 'Pabellón A' in html and 'Cama A' in html and 'Residente Citas' in html
        assert reverse('residente_detalle', args=[residente.pk]) in html
        assert ('Nuevo departamento' in html) is (rol == 'administrador')


def test_listas_anteriores_redirigen(client, usuarios):
    client.force_login(usuarios['auxiliar'])
    for nombre in ('departamento_lista', 'habitacion_lista', 'cama_lista'):
        assert client.get(reverse(nombre)).url == reverse('institucion')


def test_solo_el_administrador_crea_y_edita(client, usuarios, estructura):
    dep, hab, c1, c2 = estructura
    client.force_login(usuarios['jefe'])
    client.post(reverse('departamento_crear'), {'nombre': 'Pabellón B', 'activo': 'on'})
    assert not Departamento.objects.filter(nombre='Pabellón B').exists()
    client.force_login(usuarios['administrador'])
    r = client.post(reverse('departamento_crear'), {'nombre': 'Pabellón B', 'activo': 'on'})
    dep_b = Departamento.objects.get(nombre='Pabellón B')
    assert r.url == reverse('institucion') + f'#dep-{dep_b.pk}'
    r = client.post(reverse('cama_crear'), {'habitacion': hab.pk, 'codigo': 'C', 'estado': 'disponible', 'activo': 'on'})
    assert Cama.objects.filter(codigo='C', habitacion=hab).exists()
    assert r.url.endswith(f'#hab-{hab.pk}')


def test_formularios_con_preseleccion_y_alta_en_contexto(client, usuarios, estructura):
    dep, hab, c1, c2 = estructura
    client.force_login(usuarios['administrador'])
    r = client.get(reverse('cama_crear') + f'?habitacion={hab.pk}')
    assert r.context['form'].initial['habitacion'] == str(hab.pk)
    assert 'Agregar habitación' in r.content.decode()
    assert 'Agregar departamento' in client.get(reverse('habitacion_crear')).content.decode()
    r = client.post(reverse('departamento_crear_rapido'), {'nombre': 'Pabellón C'})
    assert r.json()['text'] == 'Pabellón C'
    r = client.post(reverse('departamento_crear_rapido'), {'nombre': 'pabellón c'})
    assert r.status_code == 400
    r = client.post(reverse('habitacion_crear_rapido'), {'departamento': dep.pk, 'numero': '102'})
    assert Habitacion.objects.filter(departamento=dep, numero='102').exists() and r.json()['id']
    r = client.post(reverse('habitacion_crear_rapido'), {'departamento': dep.pk, 'numero': '102'})
    assert r.status_code == 400
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('departamento_crear_rapido'), {'nombre': 'X'})
    assert r.status_code == 302 and not Departamento.objects.filter(nombre='X').exists()


def test_desactivar_solo_por_post_y_no_si_esta_ocupada(client, usuarios, residente, estructura):
    dep, hab, c1, c2 = estructura
    Residente.objects.filter(pk=residente.pk).update(cama_actual=c1)
    client.force_login(usuarios['administrador'])
    assert client.get(reverse('cama_desactivar', args=[c2.pk])).status_code == 405
    client.post(reverse('cama_desactivar', args=[c1.pk]))
    c1.refresh_from_db()
    assert c1.activo
    client.post(reverse('habitacion_desactivar', args=[hab.pk]))
    hab.refresh_from_db()
    assert hab.activo
    client.post(reverse('cama_desactivar', args=[c2.pk]))
    c2.refresh_from_db()
    assert not c2.activo
    html = client.get(reverse('institucion')).content.decode()
    assert 'Cama B' not in html
    assert 'Cama B' in client.get(reverse('institucion') + '?inactivos=1').content.decode()


def test_residentes_sin_cama(client, usuarios, residente, estructura):
    client.force_login(usuarios['medico'])
    assert 'Residentes activos sin cama asignada' in client.get(reverse('institucion')).content.decode()


def test_otro_hogar_no_ve_ni_edita(client, usuarios, estructura, usuario_otro_hogar):
    dep, hab, c1, c2 = estructura
    client.force_login(usuario_otro_hogar)
    assert 'Pabellón A' not in client.get(reverse('institucion')).content.decode()
