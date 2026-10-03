"""Dietas, ingesta por comida, líquidos, cocina, configuración, alertas y PDF."""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from alertas import motor
from alertas.models import Alerta
from auditoria.models import RegistroAuditoria
from medicamentos.tests.conftest import *  # noqa: F401,F403
from nutricion import services
from nutricion.models import ConfiguracionNutricion, DietaResidente, RegistroIngesta, TipoDieta
from signos.models import RegistroLiquidos

pytestmark = pytest.mark.django_db


def _activas(hogar, regla):
    return Alerta.objects.filter(hogar=hogar, regla=regla, estado__in=Alerta.ACTIVAS)


def _dieta(residente, usuario, **kw):
    datos = dict(tipo=TipoDieta.objects.get(nombre='Blanda'), textura='molida')
    datos.update(kw)
    return services.cambiar_dieta(residente, DietaResidente(**datos), usuario)


class TestDieta:

    def test_catalogo_basico(self, hogar):
        assert TipoDieta.disponibles(hogar).filter(nombre='Para diabéticos').exists()

    def test_cambio_deja_historial(self, residente, usuario_medico):
        d1 = _dieta(residente, usuario_medico)
        d2 = _dieta(residente, usuario_medico, tipo=TipoDieta.objects.get(nombre='Normal'), textura='normal')
        d1.refresh_from_db()
        assert not d1.vigente and d1.fecha_fin and d2.vigente
        assert services.dieta_vigente(residente) == d2
        with pytest.raises(ValueError):
            d1.delete()

    def test_formulario_y_catalogo_en_contexto(self, client, residente, usuario_nutricionista, hogar):
        client.force_login(usuario_nutricionista)
        r = client.post(reverse('nutricion_tipo_dieta_rapido'), {'nombre': 'Sin gluten'})
        assert r.status_code == 200
        tipo_id = r.json()['id']
        assert TipoDieta.objects.get(pk=tipo_id).hogar == hogar
        assert client.post(reverse('nutricion_tipo_dieta_rapido'), {'nombre': 'sin gluten'}).status_code == 400
        r = client.post(reverse('nutricion_dieta', args=[residente.pk]), {
            'tipo': tipo_id, 'textura': 'normal', 'liquidos': 'nectar', 'ayuda': 'parcial',
            'meta_liquidos_ml': 1200, 'restriccion_liquidos_ml': 1000})
        assert r.status_code == 200  # meta mayor que el máximo
        r = client.post(reverse('nutricion_dieta', args=[residente.pk]), {
            'tipo': tipo_id, 'textura': 'normal', 'liquidos': 'nectar', 'ayuda': 'parcial', 'restriccion_liquidos_ml': 1000})
        assert r.status_code == 302
        d = services.dieta_vigente(residente)
        assert d.liquidos == 'nectar' and services.meta_liquidos(residente, d) == 1000
        assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.DIETA_INDICADA).exists()

    def test_auxiliar_no_indica_dieta(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        assert client.get(reverse('nutricion_dieta', args=[residente.pk])).status_code in (302, 403)


class TestIngesta:

    def test_registro_y_correccion(self, residente, usuario_enfermero):
        hoy = timezone.localdate()
        r1 = services.registrar_ingesta(residente, hoy, 'almuerzo', 'mitad', usuario_enfermero)
        assert r1.verificar_integridad() and r1.porcentaje == 50
        r2 = services.registrar_ingesta(residente, hoy, 'almuerzo', 'todo', usuario_enfermero)
        r1.refresh_from_db()
        assert r1.anulado and 'antes "La mitad"' in r1.motivo_anulacion and r2.porcentaje == 100
        with pytest.raises(ValueError):
            services.registrar_ingesta(residente, hoy + timedelta(days=1), 'cena', 'todo', usuario_enfermero)
        with pytest.raises(ValueError):
            r2.consumo = 'nada'
            r2.save()

    def test_planilla_un_toque(self, client, residente, usuario_enfermero):
        client.force_login(usuario_enfermero)
        r = client.get(reverse('nutricion_planilla'), {'comida': 'cena'})
        assert r.status_code == 200 and r.context['comida'] == 'cena'
        r = client.post(reverse('nutricion_ingesta', args=[residente.pk]), {
            'fecha': timezone.localdate().isoformat(), 'comida': 'cena', 'consumo': 'cuarto',
            'volver': reverse('nutricion_planilla') + '?comida=cena'})
        assert r.status_code == 302 and r.url.endswith(f'#res-{residente.pk}')
        assert RegistroIngesta.objects.get().consumo == 'cuarto'

    def test_correccion_ajena_solo_jefe(self, client, residente, usuario_enfermero, usuario_jefe_enfermeria, hogar):
        from medicamentos.tests.conftest import _crear_usuario
        otra = _crear_usuario(hogar, 'otra_auxiliar', 'enfermero')
        services.registrar_ingesta(residente, timezone.localdate(), 'desayuno', 'todo', usuario_enfermero)
        datos = {'fecha': timezone.localdate().isoformat(), 'comida': 'desayuno', 'consumo': 'nada'}
        client.force_login(otra)
        client.post(reverse('nutricion_ingesta', args=[residente.pk]), datos)
        assert RegistroIngesta.objects.get(anulado=False).consumo == 'todo'
        client.force_login(usuario_jefe_enfermeria)
        client.post(reverse('nutricion_ingesta', args=[residente.pk]), datos)
        assert RegistroIngesta.objects.get(anulado=False).consumo == 'nada'
        assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.INGESTA_CORREGIDA).exists()

    def test_vaso_va_al_balance(self, client, residente, usuario_enfermero, hogar):
        client.force_login(usuario_enfermero)
        client.post(reverse('nutricion_vaso', args=[residente.pk]))
        client.post(reverse('nutricion_vaso', args=[residente.pk]))
        assert services.liquidos_del_dia(residente) == 400
        reg = RegistroLiquidos.objects.first()
        assert reg.via == 'oral' and reg.tipo == RegistroLiquidos.INGRESO

    def test_nutricionista_no_registra_vasos(self, client, residente, usuario_nutricionista):
        client.force_login(usuario_nutricionista)
        r = client.post(reverse('nutricion_vaso', args=[residente.pk]))
        assert r.status_code in (302, 403) and not RegistroLiquidos.objects.exists()

    def test_ausente_no_cuenta_en_promedio(self, residente, usuario_enfermero):
        hoy = timezone.localdate()
        a = services.registrar_ingesta(residente, hoy, 'desayuno', 'ausente', usuario_enfermero)
        b = services.registrar_ingesta(residente, hoy, 'almuerzo', 'tres_cuartos', usuario_enfermero)
        assert services.promedio([a, b]) == 75

    def test_comida_actual(self, hogar):
        from datetime import datetime
        config = ConfiguracionNutricion.para_hogar(hogar)
        tz = timezone.get_current_timezone()
        assert services.comida_actual(config, timezone.make_aware(datetime(2026, 10, 1, 12, 10), tz)) == 'almuerzo'
        assert services.comida_actual(config, timezone.make_aware(datetime(2026, 10, 1, 6, 0), tz)) == 'desayuno'


class TestCocinaYConfiguracion:

    def test_lista_cocina(self, client, residente, usuario_enfermero, usuario_medico):
        from antecedentes.models import Alergia
        Alergia.objects.create(residente=residente, tipo=Alergia.ALIMENTO, sustancia='Mariscos', registrado_por=usuario_medico)
        client.force_login(usuario_enfermero)
        r = client.get(reverse('nutricion_cocina'))
        assert len(r.context['sin_dieta']) == 1 and 'Mariscos' in r.content.decode()
        _dieta(residente, usuario_medico)
        r = client.get(reverse('nutricion_cocina'))
        assert r.context['grupos'][0]['dieta'] == 'Blanda' and r.context['grupos'][0]['textura'] == 'Molida o en puré'

    def test_configuracion(self, client, hogar, usuario_nutricionista, usuario_enfermero):
        client.force_login(usuario_enfermero)
        assert client.get(reverse('nutricion_configuracion')).status_code in (302, 403)
        client.force_login(usuario_nutricionista)
        datos = {'vaso_ml': 250, 'meta_liquidos_ml': 1800, 'activa_desayuno': 'on', 'activa_almuerzo': 'on',
                 'activa_cena': 'on'}
        for c, h in (('desayuno', '07:30'), ('media_manana', '10:00'), ('almuerzo', '12:00'), ('onces', '15:00'),
                     ('cena', '17:30'), ('nocturno', '20:00')):
            datos[f'hora_{c}'] = h
        assert client.post(reverse('nutricion_configuracion'), datos).status_code == 302
        c = ConfiguracionNutricion.para_hogar(hogar)
        assert [x[0] for x in c.comidas()] == ['desayuno', 'almuerzo', 'cena'] and c.comidas()[0][2] == '07:30'
        assert c.vaso_ml == 250


class TestAlertas:

    def test_ingesta_baja(self, hogar, residente, usuario_enfermero):
        hoy = timezone.localdate()
        for comida, consumo in (('desayuno', 'mitad'), ('almuerzo', 'nada'), ('cena', 'rechazo')):
            services.registrar_ingesta(residente, hoy, comida, consumo, usuario_enfermero)
        motor.evaluar_hogar(hogar)
        a = _activas(hogar, 'ingesta_baja').get()
        assert a.gravedad == Alerta.ALTA
        services.registrar_ingesta(residente, hoy, 'nocturno', 'todo', usuario_enfermero)
        motor.evaluar_hogar(hogar)
        a.refresh_from_db()
        assert a.estado == Alerta.RESUELTA

    def test_liquidos(self, hogar, residente, usuario_enfermero, usuario_medico):
        from residentes.models import Residente
        Residente.objects.filter(pk=residente.pk).update(fecha_ingreso=timezone.now() - timedelta(days=10))
        residente.refresh_from_db()
        services.registrar_vaso(residente, usuario_enfermero, 200)
        motor.evaluar_hogar(hogar)
        assert _activas(hogar, 'liquidos_insuficientes').filter(clave=f'liquidos_bajos:{residente.pk}').exists()
        _dieta(residente, usuario_medico, restriccion_liquidos_ml=300)
        services.registrar_vaso(residente, usuario_enfermero, 200)
        motor.evaluar_hogar(hogar)
        assert _activas(hogar, 'liquidos_insuficientes').filter(clave=f'liquidos_exceso:{residente.pk}').exists()

    def test_sin_dieta(self, hogar, residente, usuario_medico):
        from residentes.models import Residente
        Residente.objects.filter(pk=residente.pk).update(fecha_ingreso=timezone.now() - timedelta(days=5))
        motor.evaluar_hogar(hogar)
        assert _activas(hogar, 'sin_dieta').exists()
        _dieta(residente, usuario_medico)
        motor.evaluar_hogar(hogar)
        assert not _activas(hogar, 'sin_dieta').exists()


class TestIntegracion:

    def test_residente_expediente_y_ayuda(self, client, residente, usuario_medico, usuario_enfermero):
        _dieta(residente, usuario_medico)
        services.registrar_ingesta(residente, timezone.localdate(), 'almuerzo', 'todo', usuario_enfermero)
        client.force_login(usuario_medico)
        r = client.get(reverse('nutricion_residente', args=[residente.pk]))
        assert r.status_code == 200 and 'Dieta del residente' in r.content.decode()
        html = client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()
        assert 'Nutrición e hidratación' in html and 'value="nutricion"' in html
        assert reverse('nutricion_planilla') in html

    def test_pdf(self, residente, usuario_medico):
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from residentes import pdf_secciones
        n = getSampleStyleSheet()['Normal']
        kit = pdf_secciones.Kit(n, n, n, n, colors.blue, colors.white, colors.white)
        assert pdf_secciones.nutricion(residente, kit) == []
        _dieta(residente, usuario_medico)
        assert len(pdf_secciones.nutricion(residente, kit)) >= 3
