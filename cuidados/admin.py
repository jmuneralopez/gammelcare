from django.contrib import admin

from .models import Herida, PlanCuidados, RegistroCuidado, SeguimientoHerida

admin.site.register(PlanCuidados)
admin.site.register(RegistroCuidado)
admin.site.register(Herida)
admin.site.register(SeguimientoHerida)
