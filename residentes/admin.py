from django.contrib import admin
from .models import Residente, AsignacionCama

@admin.register(Residente)
class ResidenteAdmin(admin.ModelAdmin):
    list_display = ['pk', 'hogar', 'cama_actual', 'fecha_nacimiento', 'activo']
    list_filter = ['hogar', 'activo']

@admin.register(AsignacionCama)
class AsignacionCamaAdmin(admin.ModelAdmin):
    list_display = ['residente', 'cama', 'fecha_inicio', 'fecha_fin', 'activo']
    list_filter = ['activo']