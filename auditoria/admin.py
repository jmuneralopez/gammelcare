from django.contrib import admin
from .models import RegistroAuditoria

@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'accion', 'ip_address', 'timestamp']
    list_filter = ['accion']
    readonly_fields = ['usuario', 'accion', 'descripcion', 'ip_address', 'timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False