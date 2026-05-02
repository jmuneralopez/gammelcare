from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Rol


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'descripcion']


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ['username', 'get_full_name', 'roles_display', 'hogar', 'activo']
    list_filter = ['hogar', 'activo']
    fieldsets = UserAdmin.fieldsets + (
        ('GammelCare', {'fields': ('roles', 'hogar', 'activo')}),
    )