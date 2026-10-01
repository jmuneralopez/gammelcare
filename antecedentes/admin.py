from django.contrib import admin

from .models import Alergia, Antecedente, EstadoAlergias


class SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Alergia)
class AlergiaAdmin(SoloLectura):
    list_display = ('sustancia', 'residente', 'tipo', 'severidad', 'activo', 'fecha_registro')
    list_filter = ('tipo', 'severidad', 'activo')


@admin.register(Antecedente)
class AntecedenteAdmin(SoloLectura):
    list_display = ('descripcion', 'residente', 'tipo', 'activo', 'fecha_registro')
    list_filter = ('tipo', 'activo')


@admin.register(EstadoAlergias)
class EstadoAlergiasAdmin(SoloLectura):
    list_display = ('residente', 'sin_alergias_conocidas', 'fecha_actualizacion')
