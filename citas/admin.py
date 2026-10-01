from django.contrib import admin

from .models import Cita


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = ('residente', 'tipo', 'especialidad', 'fecha_hora', 'estado')
    list_filter = ('estado', 'tipo')
    readonly_fields = [f.name for f in Cita._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False
