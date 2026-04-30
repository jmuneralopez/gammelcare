from django.contrib import admin
from .models import Hogar

@admin.register(Hogar)
class HogarAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'nit', 'direccion', 'activo']
    search_fields = ['nombre', 'nit']
    list_filter = ['activo']