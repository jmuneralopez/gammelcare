from django.core.management.base import BaseCommand
from medicamentos.models import Medicamento


# Catálogo base compartido (hogar=NULL) — medicamentos de uso geriátrico
# frecuente en Colombia. Igual que catalogos/cargar_cie10, esto se corre
# una sola vez por instalación; los hogares pueden agregar sus propios
# medicamentos, y el superadmin puede promoverlos después (ver plan
# modulo-medicamentos.md, sección 2.1). No pretende ser exhaustivo — es
# un punto de partida razonable, ampliable desde /admin/.
MEDICAMENTOS_BASE = [
    # (generico, comercial, concentracion, forma, unidad_dosis, refrigeracion, control_especial)
    ('Acetaminofén', 'Dolex', '500 mg', 'tableta', 'tableta', False, False),
    ('Acetaminofén', '', '160 mg/5 mL', 'jarabe', 'ml', False, False),
    ('Ibuprofeno', 'Advil', '400 mg', 'tableta', 'tableta', False, False),
    ('Diclofenaco', '', '50 mg', 'tableta', 'tableta', False, False),
    ('Tramadol', '', '50 mg', 'capsula', 'capsula', False, True),
    ('Naproxeno', '', '250 mg', 'tableta', 'tableta', False, False),

    ('Losartán', 'Cozaar', '50 mg', 'tableta', 'tableta', False, False),
    ('Enalapril', '', '10 mg', 'tableta', 'tableta', False, False),
    ('Amlodipino', '', '5 mg', 'tableta', 'tableta', False, False),
    ('Carvedilol', '', '6.25 mg', 'tableta', 'tableta', False, False),
    ('Metoprolol', '', '50 mg', 'tableta', 'tableta', False, False),
    ('Furosemida', '', '40 mg', 'tableta', 'tableta', False, False),
    ('Hidroclorotiazida', '', '25 mg', 'tableta', 'tableta', False, False),
    ('Espironolactona', '', '25 mg', 'tableta', 'tableta', False, False),
    ('Digoxina', '', '0.25 mg', 'tableta', 'tableta', False, False),
    ('Ácido acetilsalicílico', 'Cardioaspirina', '100 mg', 'tableta', 'tableta', False, False),
    ('Atorvastatina', '', '20 mg', 'tableta', 'tableta', False, False),
    ('Warfarina', 'Coumadin', '5 mg', 'tableta', 'tableta', False, False),
    ('Clopidogrel', 'Plavix', '75 mg', 'tableta', 'tableta', False, False),

    ('Metformina', '', '850 mg', 'tableta', 'tableta', False, False),
    ('Glibenclamida', '', '5 mg', 'tableta', 'tableta', False, False),
    ('Insulina NPH', 'Humulin N', '100 UI/mL', 'insulina', 'ui', True, False),
    ('Insulina Cristalina', 'Humulin R', '100 UI/mL', 'insulina', 'ui', True, False),

    ('Omeprazol', '', '20 mg', 'capsula', 'capsula', False, False),
    ('Ranitidina', '', '150 mg', 'tableta', 'tableta', False, False),
    ('Loperamida', '', '2 mg', 'capsula', 'capsula', False, False),
    ('Lactulosa', '', '15 mL', 'jarabe', 'ml', False, False),
    ('Bisacodilo', '', '5 mg', 'tableta', 'tableta', False, False),
    ('Metoclopramida', '', '10 mg', 'tableta', 'tableta', False, False),

    ('Levotiroxina', 'Eutirox', '50 mcg', 'tableta', 'tableta', False, False),
    ('Alopurinol', '', '300 mg', 'tableta', 'tableta', False, False),
    ('Tamsulosina', '', '0.4 mg', 'capsula', 'capsula', False, False),
    ('Finasteride', '', '5 mg', 'tableta', 'tableta', False, False),

    ('Haloperidol', '', '5 mg', 'tableta', 'tableta', False, False),
    ('Quetiapina', '', '25 mg', 'tableta', 'tableta', False, True),
    ('Clonazepam', '', '2 mg', 'tableta', 'tableta', False, True),
    ('Zolpidem', '', '10 mg', 'tableta', 'tableta', False, True),
    ('Sertralina', '', '50 mg', 'tableta', 'tableta', False, False),
    ('Escitalopram', '', '10 mg', 'tableta', 'tableta', False, False),
    ('Donepezilo', '', '10 mg', 'tableta', 'tableta', False, False),
    ('Memantina', '', '10 mg', 'tableta', 'tableta', False, False),

    ('Salbutamol', 'Ventolin', '100 mcg/dosis', 'inhalador', 'puff', False, False),
    ('Bromuro de ipratropio', 'Atrovent', '20 mcg/dosis', 'inhalador', 'puff', False, False),
    ('Prednisolona', '', '5 mg', 'tableta', 'tableta', False, False),
    ('Loratadina', '', '10 mg', 'tableta', 'tableta', False, False),

    ('Amoxicilina', '', '500 mg', 'capsula', 'capsula', False, False),
    ('Ciprofloxacina', '', '500 mg', 'tableta', 'tableta', False, False),
    ('Trimetoprim + Sulfametoxazol', '', '160/800 mg', 'tableta', 'tableta', False, False),
    ('Nistatina', '', 'crema tópica', 'crema_ungüento', 'aplicacion', False, False),
    ('Ácido fusídico', '', 'crema tópica 2%', 'crema_ungüento', 'aplicacion', False, False),

    ('Calcio + Vitamina D3', '', '600 mg / 400 UI', 'tableta', 'tableta', False, False),
    ('Complejo B', '', '', 'tableta', 'tableta', False, False),
    ('Ácido fólico', '', '1 mg', 'tableta', 'tableta', False, False),
    ('Sulfato ferroso', '', '300 mg', 'tableta', 'tableta', False, False),
    ('Multivitamínico', '', '', 'tableta', 'tableta', False, False),
    ('Lágrimas artificiales', '', '', 'gotas', 'gota', False, False),
]


class Command(BaseCommand):
    help = 'Carga el catálogo base (compartido) de medicamentos de uso geriátrico frecuente.'

    def handle(self, *args, **options):
        creados = 0
        existentes = 0
        for generico, comercial, concentracion, forma, unidad, refrigeracion, control in MEDICAMENTOS_BASE:
            _, created = Medicamento.objects.get_or_create(
                nombre_generico=generico,
                concentracion=concentracion,
                hogar=None,
                defaults={
                    'nombre_comercial': comercial,
                    'forma_farmaceutica': forma,
                    'unidad_dosificacion': unidad,
                    'requiere_refrigeracion': refrigeracion,
                    'control_especial': control,
                }
            )
            if created:
                creados += 1
            else:
                existentes += 1

        self.stdout.write(self.style.SUCCESS(
            f'Catálogo de medicamentos: {creados} creado(s), {existentes} ya existían.'
        ))
