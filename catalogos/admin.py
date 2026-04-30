from django.contrib import admin
from .models import EPS, ServicioAmbulancia, CodigoCIE10


@admin.register(EPS)
class EPSAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'codigo', 'telefono', 'activo']
    search_fields = ['nombre', 'codigo']
    list_filter = ['activo']


@admin.register(ServicioAmbulancia)
class ServicioAmbulanciaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'telefono', 'activo']
    search_fields = ['nombre']
    list_filter = ['activo']


@admin.register(CodigoCIE10)
class CodigoCIE10Admin(admin.ModelAdmin):
    list_display = ['codigo', 'descripcion', 'categoria']
    search_fields = ['codigo', 'descripcion']
    list_filter = ['categoria']