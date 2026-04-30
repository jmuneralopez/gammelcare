from django.contrib import admin
from .models import Departamento, Habitacion, Cama

@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'hogar', 'activo']
    list_filter = ['hogar', 'activo']
    search_fields = ['nombre']

@admin.register(Habitacion)
class HabitacionAdmin(admin.ModelAdmin):
    list_display = ['numero', 'departamento', 'activo']
    list_filter = ['departamento', 'activo']

@admin.register(Cama)
class CamaAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'habitacion', 'estado', 'activo']
    list_filter = ['estado', 'activo']