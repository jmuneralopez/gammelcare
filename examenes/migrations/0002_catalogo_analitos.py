"""Carga inicial del catálogo de analitos frecuentes en geriatría.

Rangos de referencia de adulto por defecto, en las unidades que usan los
laboratorios en Colombia. Son solo un punto de partida: cada laboratorio
reporta su propio rango y ese es el que se debe registrar en el resultado.
Los valores críticos son umbrales conservadores de uso común para resaltar
el resultado y avisar al médico; cada hogar puede ajustarlos desde el
administrador de Django.
"""
from decimal import Decimal as D

from django.db import migrations

ANALITOS = [
    # codigo, nombre, unidad, ref_min, ref_max, critico_min, critico_max, nota
    ('glucosa', 'Glucosa en ayunas', 'mg/dL', D('70'), D('100'), D('50'), D('400'), ''),
    ('hba1c', 'Hemoglobina glicosilada (HbA1c)', '%', D('4.0'), D('5.6'), None, None,
     'En el adulto mayor diabético la meta la individualiza el médico.'),
    ('creatinina', 'Creatinina', 'mg/dL', D('0.6'), D('1.2'), None, None, ''),
    ('bun', 'Nitrógeno ureico (BUN)', 'mg/dL', D('7'), D('20'), None, None, ''),
    ('tfg', 'Tasa de filtración glomerular estimada', 'mL/min/1.73 m²', D('60'), None, None, None, ''),
    ('hemoglobina', 'Hemoglobina', 'g/dL', D('12.0'), D('17.0'), D('7.0'), None,
     'El rango varía por sexo; use el que reporta el laboratorio.'),
    ('hematocrito', 'Hematocrito', '%', D('36'), D('50'), None, None, ''),
    ('leucocitos', 'Leucocitos', '×10³/µL', D('4.5'), D('11.0'), D('2.0'), D('30.0'), ''),
    ('plaquetas', 'Plaquetas', '×10³/µL', D('150'), D('450'), D('20'), D('1000'), ''),
    ('sodio', 'Sodio', 'mEq/L', D('135'), D('145'), D('120'), D('160'), ''),
    ('potasio', 'Potasio', 'mEq/L', D('3.5'), D('5.0'), D('2.8'), D('6.2'), ''),
    ('inr', 'INR', '', D('0.8'), D('1.2'), None, D('5.0'),
     'En anticoagulación con warfarina la meta suele ser 2–3: ajuste el rango en el resultado.'),
    ('colesterol_total', 'Colesterol total', 'mg/dL', None, D('200'), None, None, ''),
    ('ldl', 'Colesterol LDL', 'mg/dL', None, D('130'), None, None, 'La meta depende del riesgo cardiovascular.'),
    ('hdl', 'Colesterol HDL', 'mg/dL', D('40'), None, None, None, ''),
    ('trigliceridos', 'Triglicéridos', 'mg/dL', None, D('150'), None, None, ''),
    ('tsh', 'TSH', 'mUI/L', D('0.4'), D('4.0'), None, None, ''),
    ('t4_libre', 'T4 libre', 'ng/dL', D('0.8'), D('1.8'), None, None, ''),
    ('albumina', 'Albúmina', 'g/dL', D('3.5'), D('5.0'), None, None, ''),
    ('ast', 'AST (TGO)', 'U/L', D('10'), D('40'), None, None, ''),
    ('alt', 'ALT (TGP)', 'U/L', D('7'), D('56'), None, None, ''),
    ('acido_urico', 'Ácido úrico', 'mg/dL', D('3.5'), D('7.2'), None, None, ''),
    ('vitamina_b12', 'Vitamina B12', 'pg/mL', D('200'), D('900'), None, None, ''),
    ('vitamina_d', 'Vitamina D (25-OH)', 'ng/mL', D('30'), D('100'), None, None, ''),
    ('pcr', 'Proteína C reactiva', 'mg/L', None, D('5'), None, None, 'El corte varía por laboratorio.'),
]


def cargar(apps, schema_editor):
    Analito = apps.get_model('examenes', 'AnalitoCatalogo')
    for orden, (codigo, nombre, unidad, rmin, rmax, cmin, cmax, nota) in enumerate(ANALITOS, start=1):
        Analito.objects.update_or_create(codigo=codigo, defaults={
            'nombre': nombre, 'unidad': unidad, 'ref_min': rmin, 'ref_max': rmax,
            'critico_min': cmin, 'critico_max': cmax, 'nota': nota, 'orden': orden * 10,
        })


def descargar(apps, schema_editor):
    Analito = apps.get_model('examenes', 'AnalitoCatalogo')
    Analito.objects.filter(codigo__in=[a[0] for a in ANALITOS], valores__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [('examenes', '0001_initial')]

    operations = [migrations.RunPython(cargar, descargar)]
