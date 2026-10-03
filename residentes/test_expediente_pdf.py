"""PDF del expediente con las secciones clínicas nuevas."""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from medicamentos.tests.conftest import *  # noqa: F401,F403  (fixtures compartidos)
from residentes import pdf_secciones
from residentes.views import SECCIONES_PDF_DISPONIBLES

pytestmark = pytest.mark.django_db


def _textos(flowables):
    """Todo el texto de los párrafos, incluidos los que están dentro de tablas."""
    salida = []

    def recorrer(f):
        if hasattr(f, 'text'):
            salida.append(f.text)
        for fila in getattr(f, '_cellvalues', []) or []:
            for celda in fila:
                recorrer(celda)

    for f in flowables:
        recorrer(f)
    return ' '.join(salida)


@pytest.fixture
def kit():
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    n = getSampleStyleSheet()['Normal']
    return pdf_secciones.Kit(seccion=n, label=n, body=n, encabezado=n,
                             azul_medio=colors.blue, azul_claro=colors.white, azul_xclaro=colors.white)


def test_secciones_disponibles():
    assert {'alergias', 'medicamentos', 'signos', 'valoracion', 'plan', 'examenes_clinicos', 'citas',
            'diagnosticos', 'notas'} <= SECCIONES_PDF_DISPONIBLES


def test_alergias_y_sin_registrar(residente, kit, usuario_medico):
    from antecedentes.models import Alergia
    assert 'sin registrar' in _textos(pdf_secciones.alergias(residente, kit))
    Alergia.objects.create(residente=residente, sustancia='Penicilina', registrado_por=usuario_medico)
    assert 'Penicilina' in _textos(pdf_secciones.alergias(residente, kit))


def test_medicamentos(residente, kit, prescripcion_horarios_fijos, prescripcion_prn):
    texto = _textos(pdf_secciones.medicamentos(residente, kit))
    assert 'Acetaminofén' in texto and '08:00' in texto and 'Si es necesario' in texto


def test_signos_valoracion_y_vacios(residente, kit, usuario_enfermero):
    from signos.models import ControlSignos
    assert pdf_secciones.signos(residente, kit) == []
    assert pdf_secciones.valoracion(residente, kit) == []
    assert pdf_secciones.plan(residente, kit) == []
    assert pdf_secciones.examenes(residente, kit) == []
    assert pdf_secciones.citas(residente, kit) == []
    ControlSignos.objects.create(residente=residente, pas=130, pad=80, fc=72, registrado_por=usuario_enfermero)
    assert '130/80' in _textos(pdf_secciones.signos(residente, kit))


def test_valoracion_ultima_por_escala(residente, kit, usuario_medico):
    from valoracion import escalas as E
    from valoracion.models import Valoracion
    for p, dias in ((3, 30), (5, 1)):
        b = E.POR_CODIGO['katz'].interpretar(p)
        Valoracion.objects.create(residente=residente, escala='katz', puntaje=p, interpretacion=b.texto,
                                  nivel=b.nivel, registrado_por=usuario_medico,
                                  fecha=timezone.localdate() - timedelta(days=dias))
    flow = pdf_secciones.valoracion(residente, kit)
    filas = flow[1]._cellvalues
    assert len(filas) == 2  # encabezado + una fila
    assert '5' in _textos(flow)


def test_citas_proximas(residente, kit, usuario_enfermero):
    from citas.models import Cita
    Cita.objects.create(residente=residente, lugar='Clínica Norte', especialidad='Cardiología',
                        fecha_hora=timezone.now() + timedelta(days=5), registrado_por=usuario_enfermero)
    assert 'Cardiología' in _textos(pdf_secciones.citas(residente, kit))


def test_vista_genera_pdf_completo(client, usuario_medico, residente, prescripcion_horarios_fijos):
    client.force_login(usuario_medico)
    r = client.get(reverse('residente_pdf', args=[residente.pk]))
    assert r.status_code == 200
    assert r['Content-Type'] == 'application/pdf'
    assert r.content[:4] == b'%PDF'


def test_vista_parcial(client, usuario_medico, residente):
    client.force_login(usuario_medico)
    r = client.get(reverse('residente_pdf', args=[residente.pk]), {'secciones': ['medicamentos', 'alergias']})
    assert r.status_code == 200 and r.content[:4] == b'%PDF'


def test_modal_ofrece_secciones(client, usuario_medico, residente):
    client.force_login(usuario_medico)
    html = client.get(reverse('residente_detalle', args=[residente.pk])).content.decode()
    for v in ('alergias', 'medicamentos', 'signos', 'valoracion', 'plan', 'examenes_clinicos', 'citas'):
        assert f'value="{v}"' in html


def test_cita_pasada_sin_cierre_aparece(residente, kit, usuario_enfermero):
    from citas.models import Cita
    Cita.objects.create(residente=residente, lugar='Clínica Norte', especialidad='Ortopedia',
                        fecha_hora=timezone.now() - timedelta(days=2), registrado_por=usuario_enfermero)
    texto = _textos(pdf_secciones.citas(residente, kit))
    assert 'Ortopedia' in texto and 'Sin registrar qué pasó' in texto
