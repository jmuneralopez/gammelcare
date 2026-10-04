from django.contrib import admin

from .models import ConfiguracionEventos, EventoAdverso, NotaEvento, VigilanciaEvento

admin.site.register(EventoAdverso)
admin.site.register(NotaEvento)
admin.site.register(VigilanciaEvento)
admin.site.register(ConfiguracionEventos)
