from django.contrib import admin

from .models import ConfiguracionNutricion, DietaResidente, RegistroIngesta, TipoDieta

admin.site.register(TipoDieta)
admin.site.register(DietaResidente)
admin.site.register(RegistroIngesta)
admin.site.register(ConfiguracionNutricion)
