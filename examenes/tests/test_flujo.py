"""Ciclo de vida completo de un examen y sus reglas de integridad."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from examenes import services
from examenes.models import ArchivoResultado, Examen, RevisionMedica, ValorResultado

from .conftest import PDF_MINIMO


def _valor(analito, valor, **extra):
    datos = {'analito': analito, 'nombre': analito.nombre, 'valor': Decimal(valor),
             'unidad': analito.unidad, 'ref_min': analito.ref_min, 'ref_max': analito.ref_max}
    datos.update(extra)
    return datos


# ── Servicios ───────────────────────────────────────────────────────

def test_cargar_resultado_pasa_a_pendiente_de_revision(examen_pendiente, usuarios, pdf, glucosa):
    services.cargar_resultado(
        examen_pendiente, usuarios['auxiliar'], fecha_toma=date.today(),
        archivos=[pdf], valores=[_valor(glucosa, '95')],
    )
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.estado == Examen.RESULTADO
    assert examen_pendiente.resultado_cargado_por == usuarios['auxiliar']
    archivo = examen_pendiente.archivos.get()
    assert archivo.sha256 and archivo.tamano_bytes == len(PDF_MINIMO)
    assert archivo.archivo.open('rb').read() == PDF_MINIMO
    valor = examen_pendiente.valores.get()
    assert valor.interpretacion() == ValorResultado.NORMAL
    assert len(valor.hash_integridad) == 64


def test_resultado_vacio_se_rechaza(examen_pendiente, usuarios):
    with pytest.raises(ValidationError):
        services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], fecha_toma=date.today())


def test_no_se_carga_resultado_dos_veces(examen_pendiente, usuarios, glucosa):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[_valor(glucosa, '90')])
    with pytest.raises(ValidationError):
        services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[_valor(glucosa, '91')])


def test_interpretacion_y_criticos(examen_pendiente, usuarios, glucosa):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[
        _valor(glucosa, '45'),
    ])
    valor = examen_pendiente.valores.get()
    assert valor.critico_min == glucosa.critico_min  # copiado del catálogo
    assert valor.interpretacion() == ValorResultado.CRITICO_BAJO
    assert examen_pendiente.tiene_criticos()


@pytest.mark.parametrize('numero,esperado', [
    ('65', ValorResultado.BAJO), ('100', ValorResultado.NORMAL),
    ('130', ValorResultado.ALTO), ('450', ValorResultado.CRITICO_ALTO),
])
def test_interpretacion_por_rango(examen_pendiente, usuarios, glucosa, numero, esperado):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[_valor(glucosa, numero)])
    assert examen_pendiente.valores.get().interpretacion() == esperado


def test_valor_sin_rango(examen_pendiente, usuarios):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[
        {'analito': None, 'nombre': 'Ferritina', 'valor': Decimal('80'), 'unidad': 'ng/mL'},
    ])
    assert examen_pendiente.valores.get().interpretacion() == ValorResultado.SIN_RANGO


def test_revision_cierra_y_adenda_reabre(examen_pendiente, usuarios, glucosa, png):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[_valor(glucosa, '99')])
    services.revisar(examen_pendiente, usuarios['medico'], conducta='Sin cambios.')
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.estado == Examen.REVISADO

    services.agregar_adenda(examen_pendiente, usuarios['jefe'], motivo='Llegó el reporte completo', archivos=[png])
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.estado == Examen.RESULTADO
    assert examen_pendiente.archivos.get().motivo == 'Llegó el reporte completo'

    services.revisar(examen_pendiente, usuarios['medico'], conducta='Control en 3 meses.')
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.estado == Examen.REVISADO
    assert examen_pendiente.revisiones.count() == 2
    assert examen_pendiente.ultima_revision().conducta == 'Control en 3 meses.'


def test_adenda_necesita_motivo_y_contenido(examen_pendiente, usuarios, glucosa, pdf):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[_valor(glucosa, '99')])
    with pytest.raises(ValidationError):
        services.agregar_adenda(examen_pendiente, usuarios['jefe'], motivo='', archivos=[pdf])
    with pytest.raises(ValidationError):
        services.agregar_adenda(examen_pendiente, usuarios['jefe'], motivo='algo')


def test_correccion_conserva_el_original(examen_pendiente, usuarios, glucosa):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[_valor(glucosa, '190')])
    services.revisar(examen_pendiente, usuarios['medico'], conducta='Ajustar dieta.')
    original = examen_pendiente.valores.get()

    nuevo = services.corregir_valor(original, usuarios['jefe'], Decimal('90'), 'mg/dL',
                                    Decimal('70'), Decimal('100'), 'Error de digitación')
    original.refresh_from_db()
    assert original.valor == Decimal('190')
    assert original.corregido_por == nuevo
    assert list(examen_pendiente.valores_vigentes()) == [nuevo]
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.estado == Examen.RESULTADO  # requiere revisión nueva

    with pytest.raises(ValidationError):
        services.corregir_valor(original, usuarios['jefe'], Decimal('91'), '', None, None, 'otra vez')


def test_cancelar_solo_pendientes(examen_pendiente, usuarios, glucosa):
    services.cancelar(examen_pendiente, usuarios['auxiliar'], 'La EPS anuló la orden')
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.estado == Examen.CANCELADO
    with pytest.raises(ValidationError):
        services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[_valor(glucosa, '90')])


def test_registros_inmutables(examen_pendiente, usuarios, glucosa, pdf):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(),
                              archivos=[pdf], valores=[_valor(glucosa, '99')])
    revision = services.revisar(examen_pendiente, usuarios['medico'], conducta='Ok')
    for fila in (examen_pendiente.valores.get(), examen_pendiente.archivos.get(), revision):
        with pytest.raises(ValueError):
            fila.save()
        with pytest.raises(ValueError):
            fila.delete()


def test_hash_verificable_tras_leer_de_la_base(examen_pendiente, usuarios, glucosa, pdf):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(),
                              archivos=[pdf], valores=[_valor(glucosa, '99.5')])
    revision = services.revisar(examen_pendiente, usuarios['medico'], conducta='Ok')
    valor = ValorResultado.objects.get()
    assert valor.verificar_integridad()
    assert RevisionMedica.objects.get(pk=revision.pk).verificar_integridad()
    assert ArchivoResultado.objects.get().verificar_integridad()
    # Una alteración directa en la base se detecta.
    ValorResultado.objects.filter(pk=valor.pk).update(valor=Decimal('70'))
    assert not ValorResultado.objects.get().verificar_integridad()
    # El hash depende del autor: otro usuario daría otro hash.
    valor.registrado_por_id = usuarios['jefe'].pk
    assert valor.calcular_hash() != valor.hash_integridad


# ── Vistas ──────────────────────────────────────────────────────────

def test_flujo_completo_por_vistas(client, residente, usuarios, glucosa):
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('examen_crear', args=[residente.pk]), {
        'tipo': 'laboratorio', 'nombre': 'Glucosa', 'ordenado_por': 'Dr. X',
        'fecha_orden': date.today().isoformat(), 'con_resultado': '1',
    })
    examen = Examen.objects.get()
    assert r.status_code == 302 and r.url == reverse('examen_resultado', args=[examen.pk])

    archivo = SimpleUploadedFile('lab.pdf', PDF_MINIMO, content_type='application/pdf')
    r = client.post(reverse('examen_resultado', args=[examen.pk]), {
        'fecha_toma': date.today().isoformat(), 'conclusion': '',
        'archivos': [archivo],
        'valores-TOTAL_FORMS': '2', 'valores-INITIAL_FORMS': '0',
        'valores-MIN_NUM_FORMS': '0', 'valores-MAX_NUM_FORMS': '1000',
        'valores-0-analito': str(glucosa.pk), 'valores-0-valor': '480',
        'valores-0-unidad': '', 'valores-0-nombre': '', 'valores-0-ref_min': '70', 'valores-0-ref_max': '100',
        # fila vacía: se ignora
        'valores-1-analito': '', 'valores-1-valor': '', 'valores-1-unidad': '',
        'valores-1-nombre': '', 'valores-1-ref_min': '', 'valores-1-ref_max': '',
    })
    assert r.status_code == 302, r.context['form'].errors if r.context else r
    examen.refresh_from_db()
    assert examen.estado == Examen.RESULTADO
    valor = examen.valores.get()
    assert valor.unidad == 'mg/dL' and valor.es_critico()
    assert examen.archivos.count() == 1

    client.force_login(usuarios['medico'])
    r = client.get(reverse('examenes_bandeja'))
    assert r.status_code == 200 and examen in r.context['por_revisar']
    r = client.post(reverse('examen_revisar', args=[examen.pk]), {'interpretacion': 'Hiperglucemia', 'conducta': 'Remitir'})
    assert r.status_code == 302
    examen.refresh_from_db()
    assert examen.estado == Examen.REVISADO

    acciones = set(RegistroAuditoria.objects.values_list('accion', flat=True))
    assert {RegistroAuditoria.EXAMEN_REGISTRADO, RegistroAuditoria.RESULTADO_EXAMEN,
            RegistroAuditoria.REVISION_EXAMEN} <= acciones


def test_archivo_falso_rechazado(client, examen_pendiente, usuarios):
    client.force_login(usuarios['auxiliar'])
    falso = SimpleUploadedFile('virus.pdf', b'MZ\x90\x00 no es un pdf', content_type='application/pdf')
    r = client.post(reverse('examen_resultado', args=[examen_pendiente.pk]), {
        'fecha_toma': date.today().isoformat(), 'archivos': [falso],
        'valores-TOTAL_FORMS': '0', 'valores-INITIAL_FORMS': '0',
        'valores-MIN_NUM_FORMS': '0', 'valores-MAX_NUM_FORMS': '1000',
    })
    assert r.status_code == 200
    assert 'archivos' in r.context['form'].errors
    assert ArchivoResultado.objects.count() == 0


def test_extension_no_permitida(client, examen_pendiente, usuarios):
    client.force_login(usuarios['auxiliar'])
    exe = SimpleUploadedFile('lab.exe', PDF_MINIMO)
    r = client.post(reverse('examen_resultado', args=[examen_pendiente.pk]), {
        'fecha_toma': date.today().isoformat(), 'archivos': [exe],
        'valores-TOTAL_FORMS': '0', 'valores-INITIAL_FORMS': '0',
        'valores-MIN_NUM_FORMS': '0', 'valores-MAX_NUM_FORMS': '1000',
    })
    assert 'archivos' in r.context['form'].errors


def test_archivo_demasiado_grande(client, examen_pendiente, usuarios, settings):
    settings.EXAMENES_MAX_MB = 0
    client.force_login(usuarios['auxiliar'])
    archivo = SimpleUploadedFile('lab.pdf', PDF_MINIMO, content_type='application/pdf')
    r = client.post(reverse('examen_resultado', args=[examen_pendiente.pk]), {
        'fecha_toma': date.today().isoformat(), 'archivos': [archivo],
        'valores-TOTAL_FORMS': '0', 'valores-INITIAL_FORMS': '0',
        'valores-MIN_NUM_FORMS': '0', 'valores-MAX_NUM_FORMS': '1000',
    })
    assert 'archivos' in r.context['form'].errors


def test_fecha_toma_futura_rechazada(client, examen_pendiente, usuarios):
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('examen_resultado', args=[examen_pendiente.pk]), {
        'fecha_toma': (date.today() + timedelta(days=2)).isoformat(), 'conclusion': 'Normal',
        'valores-TOTAL_FORMS': '0', 'valores-INITIAL_FORMS': '0',
        'valores-MIN_NUM_FORMS': '0', 'valores-MAX_NUM_FORMS': '1000',
    })
    assert 'fecha_toma' in r.context['form'].errors


def test_archivo_se_sirve_con_auditoria(client, examen_pendiente, usuarios, pdf):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), archivos=[pdf])
    archivo = examen_pendiente.archivos.get()
    client.force_login(usuarios['fisioterapeuta'])
    r = client.get(reverse('archivo_ver', args=[archivo.pk]))
    assert r.status_code == 200
    assert b''.join(r.streaming_content) == PDF_MINIMO
    assert r['Content-Type'] == 'application/pdf'
    assert r['X-Content-Type-Options'] == 'nosniff'
    assert RegistroAuditoria.objects.filter(accion=RegistroAuditoria.CONSULTA_RESULTADO).exists()


def test_editar_orden_solo_pendiente(client, examen_pendiente, usuarios, glucosa):
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('examen_editar', args=[examen_pendiente.pk]), {
        'tipo': 'laboratorio', 'nombre': 'Glucosa corregida', 'fecha_orden': date.today().isoformat(),
    })
    assert r.status_code == 302
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.nombre == 'Glucosa corregida'

    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(), valores=[_valor(glucosa, '90')])
    client.post(reverse('examen_editar', args=[examen_pendiente.pk]), {
        'tipo': 'laboratorio', 'nombre': 'Otro nombre', 'fecha_orden': date.today().isoformat(),
    })
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.nombre == 'Glucosa corregida'


def test_cancelar_por_vista(client, examen_pendiente, usuarios):
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('examen_cancelar', args=[examen_pendiente.pk]), {'motivo': 'Orden duplicada'})
    assert r.status_code == 302
    examen_pendiente.refresh_from_db()
    assert examen_pendiente.estado == Examen.CANCELADO
    assert examen_pendiente.motivo_cancelacion == 'Orden duplicada'


def test_paginas_renderizan(client, examen_pendiente, residente, usuarios, glucosa, pdf):
    services.cargar_resultado(examen_pendiente, usuarios['auxiliar'], date.today(),
                              archivos=[pdf], valores=[_valor(glucosa, '99')])
    otro = Examen.objects.create(residente=residente, nombre='Glucosa control', registrado_por=usuarios['jefe'])
    services.cargar_resultado(otro, usuarios['jefe'], date.today(), valores=[_valor(glucosa, '120')])
    valor = examen_pendiente.valores.get()
    client.force_login(usuarios['medico'])
    for nombre, args in [
        ('examenes_bandeja', []), ('examenes_residente', [residente.pk]),
        ('examen_detalle', [examen_pendiente.pk]), ('examen_revisar', [examen_pendiente.pk]),
        ('examen_adenda', [examen_pendiente.pk]), ('valor_corregir', [valor.pk]),
        ('examenes_tendencias', [residente.pk]), ('examen_crear', [residente.pk]),
        ('residente_detalle', [residente.pk]),
    ]:
        r = client.get(reverse(nombre, args=args))
        assert r.status_code == 200, nombre
    r = client.get(reverse('examenes_tendencias', args=[residente.pk]))
    assert len(r.context['graficas']) == 1 and len(r.context['graficas'][0]['puntos']) == 2
    r = client.get(reverse('residente_detalle', args=[residente.pk]))
    assert 'Exámenes y paraclínicos' in r.content.decode()


# ── Catálogo de analitos alimentado desde el formulario ─────────────

def test_agregar_analito_desde_el_formulario(client, usuarios, hogar, otro_hogar, medico_otro_hogar, examen_pendiente):
    from examenes.models import AnalitoCatalogo
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('analito_crear_rapido'), {'nombre': 'Ferritina', 'unidad': 'ng/mL', 'ref_min': '30', 'ref_max': '400'})
    assert r.status_code == 200
    nuevo = AnalitoCatalogo.objects.get(nombre='Ferritina')
    assert nuevo.hogar == hogar and nuevo.creado_por == usuarios['auxiliar']
    assert r.json()['id'] == nuevo.pk and r.json()['unidad'] == 'ng/mL'

    # Aparece en el formulario de resultados de este hogar...
    r = client.get(reverse('examen_resultado', args=[examen_pendiente.pk]))
    assert str(nuevo.pk) in r.context['catalogo_json']
    # ...y no se puede duplicar.
    r = client.post(reverse('analito_crear_rapido'), {'nombre': 'ferritina', 'unidad': 'ng/mL'})
    assert r.status_code == 400

    # Otro hogar no lo ve y puede crear el suyo.
    assert nuevo not in AnalitoCatalogo.disponibles_para(otro_hogar)
    client.force_login(medico_otro_hogar)
    assert client.post(reverse('analito_crear_rapido'), {'nombre': 'Ferritina', 'unidad': 'ng/mL'}).status_code == 200
    assert AnalitoCatalogo.objects.filter(nombre='Ferritina').count() == 2


def test_analito_rapido_requiere_permiso_y_post(client, usuarios):
    client.force_login(usuarios['fisioterapeuta'])
    client.post(reverse('analito_crear_rapido'), {'nombre': 'X', 'unidad': 'u'})
    from examenes.models import AnalitoCatalogo
    assert not AnalitoCatalogo.objects.filter(nombre='X').exists()
    client.force_login(usuarios['auxiliar'])
    assert client.get(reverse('analito_crear_rapido')).status_code == 405


def test_valor_con_analito_de_otro_hogar_rechazado(client, usuarios, otro_hogar, examen_pendiente):
    from examenes.models import AnalitoCatalogo
    ajeno = AnalitoCatalogo.objects.create(codigo='ajeno-1', nombre='Ajeno', unidad='u', hogar=otro_hogar)
    client.force_login(usuarios['auxiliar'])
    r = client.post(reverse('examen_resultado', args=[examen_pendiente.pk]), {
        'fecha_toma': date.today().isoformat(), 'conclusion': '',
        'valores-TOTAL_FORMS': '1', 'valores-INITIAL_FORMS': '0',
        'valores-MIN_NUM_FORMS': '0', 'valores-MAX_NUM_FORMS': '1000',
        'valores-0-analito': str(ajeno.pk), 'valores-0-valor': '5',
        'valores-0-unidad': '', 'valores-0-nombre': '', 'valores-0-ref_min': '', 'valores-0-ref_max': '',
    })
    assert r.status_code == 200 and not r.context['formset'].is_valid()
