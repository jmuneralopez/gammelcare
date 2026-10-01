from django.contrib import admin

from .models import ControlSignos, RangoResidente, RegistroLiquidos


class SoloLectura(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ControlSignos)
class ControlSignosAdmin(SoloLectura):
    list_display = ('residente', 'fecha_hora', 'pas', 'pad', 'fc', 'temperatura', 'spo2', 'anulado')


@admin.register(RegistroLiquidos)
class RegistroLiquidosAdmin(SoloLectura):
    list_display = ('residente', 'fecha_hora', 'tipo', 'via', 'cantidad_ml', 'anulado')


@admin.register(RangoResidente)
class RangoResidenteAdmin(SoloLectura):
    list_display = ('residente', 'parametro', 'normal_min', 'normal_max', 'activo')
