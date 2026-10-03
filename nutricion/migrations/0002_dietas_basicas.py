from django.db import migrations

BASICAS = [
    ('Normal', 'Sin restricciones.'),
    ('Blanda', 'Alimentos suaves, fáciles de masticar y digerir.'),
    ('Baja en sal (hiposódica)', 'Sin sal agregada ni embutidos, enlatados o caldos de cubo.'),
    ('Para diabéticos', 'Sin azúcar agregada, harinas controladas y fraccionada.'),
    ('Baja en grasa', 'Sin fritos ni grasas saturadas.'),
    ('Alta en proteína', 'Para desnutrición, heridas o lesiones por presión.'),
    ('Alta en fibra', 'Para el estreñimiento: frutas, verduras, granos integrales y líquidos.'),
    ('Astringente', 'Para la diarrea: sin fibra irritante, lácteos ni grasas.'),
    ('Para enfermedad renal', 'Controlada en proteína, sodio, potasio y fósforo, según indicación médica.'),
    ('Líquida', 'Solo líquidos (claros o completos), por indicación médica.'),
]


def crear(apps, schema_editor):
    TipoDieta = apps.get_model('nutricion', 'TipoDieta')
    for i, (nombre, descripcion) in enumerate(BASICAS):
        TipoDieta.objects.get_or_create(nombre=nombre, hogar=None, defaults={'descripcion': descripcion, 'orden': i})


class Migration(migrations.Migration):
    dependencies = [('nutricion', '0001_initial')]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
