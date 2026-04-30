from django.contrib import admin
from .models import Residente, AsignacionCama, ExpedienteIngreso, ExamenIngreso, DiagnosticoResidente


@admin.register(Residente)
class ResidenteAdmin(admin.ModelAdmin):
    list_display = ['pk', 'hogar', 'tipo_documento', 'cama_actual', 'fecha_nacimiento', 'activo']
    list_filter = ['hogar', 'activo', 'tipo_documento']


@admin.register(AsignacionCama)
class AsignacionCamaAdmin(admin.ModelAdmin):
    list_display = ['residente', 'cama', 'fecha_inicio', 'fecha_fin', 'activo']
    list_filter = ['activo']


@admin.register(ExpedienteIngreso)
class ExpedienteIngresoAdmin(admin.ModelAdmin):
    list_display = ['residente', 'fecha_creacion', 'fecha_actualizacion']
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion']


@admin.register(ExamenIngreso)
class ExamenIngresoAdmin(admin.ModelAdmin):
    list_display = ['residente', 'peso', 'talla', 'procedencia', 'estado_mental', 'fecha_creacion']
    readonly_fields = ['fecha_creacion', 'fecha_actualizacion']


@admin.register(DiagnosticoResidente)
class DiagnosticoResidenteAdmin(admin.ModelAdmin):
    list_display = ['residente', 'codigo_cie10', 'fecha_registro', 'activo']
    list_filter = ['activo']
    search_fields = ['codigo_cie10__codigo', 'codigo_cie10__descripcion']