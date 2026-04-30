from django.contrib import admin
from .models import NotaClinica, NotaAclaratoria

@admin.register(NotaClinica)
class NotaClinicaAdmin(admin.ModelAdmin):
    list_display = ['pk', 'residente', 'tipo', 'autor', 'fecha_creacion']
    list_filter = ['tipo']
    search_fields = ['contenido']
    readonly_fields = ['hash_integridad', 'fecha_creacion']

@admin.register(NotaAclaratoria)
class NotaAclaratoriaAdmin(admin.ModelAdmin):
    list_display = ['pk', 'nota_original', 'autor', 'fecha_creacion']
    readonly_fields = ['fecha_creacion']