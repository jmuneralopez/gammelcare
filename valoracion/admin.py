from django.contrib import admin

from .models import Valoracion


@admin.register(Valoracion)
class ValoracionAdmin(admin.ModelAdmin):
    list_display = ('residente', 'escala', 'fecha', 'puntaje', 'interpretacion', 'anulada')
    list_filter = ('escala', 'anulada')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
