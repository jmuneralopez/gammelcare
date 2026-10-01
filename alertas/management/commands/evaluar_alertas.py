from django.core.management.base import BaseCommand

from hogares.models import Hogar

from alertas.motor import evaluar_hogar


class Command(BaseCommand):
    help = 'Evalúa las reglas de alertas de todos los hogares activos (programar cada 15 minutos).'

    def add_arguments(self, parser):
        parser.add_argument('--hogar', type=int, help='Evaluar solo este hogar (id).')

    def handle(self, *args, **opciones):
        hogares = Hogar.objects.all()
        if opciones.get('hogar'):
            hogares = hogares.filter(pk=opciones['hogar'])
        elif hasattr(Hogar, 'activo'):
            hogares = hogares.filter(activo=True)
        for hogar in hogares:
            resumen = evaluar_hogar(hogar)
            creadas = sum(c for c, _ in resumen.values())
            resueltas = sum(r for _, r in resumen.values())
            self.stdout.write(f'{hogar}: {creadas} alerta(s) nueva(s), {resueltas} resuelta(s).')
