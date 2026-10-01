"""Descarte de lotes (vencidos o dañados): saca todo el saldo con su
movimiento en el libro y deja el lote en el historial."""
from datetime import date, timedelta

import pytest
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from hogares.models import Hogar
from medicamentos import services
from medicamentos.models import IngresoMedicamento, MovimientoInventario
from usuarios.models import Rol, Usuario


def _vencer(lote):
    IngresoMedicamento.objects.filter(pk=lote.pk).update(fecha_vencimiento=date.today() - timedelta(days=1))
    lote.refresh_from_db()
    return lote


def test_servicio_descarta_todo_el_saldo(ingreso_residente, usuario_jefe_enfermeria):
    services.descartar_lote(_vencer(ingreso_residente), usuario_jefe_enfermeria, 'Lote vencido')
    ingreso_residente.refresh_from_db()
    assert ingreso_residente.estado == IngresoMedicamento.DESCARTADO
    assert ingreso_residente.cantidad_disponible == 0
    mov = MovimientoInventario.objects.get(ingreso=ingreso_residente, tipo=MovimientoInventario.DESCARTE_VENCIDO)
    assert mov.cantidad == -30 and mov.motivo == 'Lote vencido'


def test_no_se_descarta_dos_veces(ingreso_residente, usuario_jefe_enfermeria):
    services.descartar_lote(ingreso_residente, usuario_jefe_enfermeria, 'Dañado')
    with pytest.raises(ValueError):
        services.descartar_lote(ingreso_residente, usuario_jefe_enfermeria, 'Otra vez')


def test_jefe_descarta_desde_el_cajon(client, ingreso_residente, usuario_jefe_enfermeria):
    client.force_login(usuario_jefe_enfermeria)
    _vencer(ingreso_residente)
    r = client.get(reverse('ingreso_lista', args=[ingreso_residente.residente_id]))
    assert 'Descartar lote' in r.content.decode()
    r = client.post(reverse('lote_descartar', args=[ingreso_residente.pk]), {'motivo': 'Lote vencido'})
    assert r.status_code == 302
    ingreso_residente.refresh_from_db()
    assert ingreso_residente.estado == IngresoMedicamento.DESCARTADO
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.DESCARTE_VENCIDO).exists()


def test_jefe_descarta_del_botiquin(client, ingreso_botiquin, usuario_administrador):
    client.force_login(usuario_administrador)
    r = client.post(reverse('lote_descartar', args=[ingreso_botiquin.pk]), {'motivo': 'Empaque roto'})
    assert r.url == reverse('botiquin_lista')
    ingreso_botiquin.refresh_from_db()
    assert ingreso_botiquin.estado == IngresoMedicamento.DESCARTADO


def test_enfermero_no_puede_descartar(client, ingreso_residente, usuario_enfermero):
    client.force_login(usuario_enfermero)
    r = client.get(reverse('ingreso_lista', args=[ingreso_residente.residente_id]))
    assert 'Descartar lote' not in r.content.decode()
    r = client.post(reverse('lote_descartar', args=[ingreso_residente.pk]), {'motivo': 'x'})
    ingreso_residente.refresh_from_db()
    assert ingreso_residente.estado != IngresoMedicamento.DESCARTADO
    assert r.status_code in (302, 403)


def test_lote_de_otro_hogar_no_se_descarta(client, ingreso_residente):
    otro = Hogar.objects.create(nombre='Otro', nit='1-9', direccion='x')
    ajeno = Usuario.objects.create_user('ajeno', password='x12345678', hogar=otro)
    ajeno.roles.add(Rol.objects.get_or_create(nombre=Rol.JEFE_ENFERMERIA)[0])
    client.force_login(ajeno)
    r = client.post(reverse('lote_descartar', args=[ingreso_residente.pk]), {'motivo': 'x'})
    assert r.status_code == 404
