from django.contrib import admin
from .models import Medicamento, ConfiguracionMedicamentos


@admin.register(Medicamento)
class MedicamentoAdmin(admin.ModelAdmin):
    list_display = ['nombre_generico', 'concentracion', 'nombre_comercial', 'hogar', 'activo']
    search_fields = ['nombre_generico', 'nombre_comercial', 'concentracion']
    list_filter = ['activo', 'requiere_refrigeracion', 'control_especial', 'forma_farmaceutica']
    actions = ['promover_a_catalogo_general']

    @admin.action(description='Promover a catálogo general (quitar hogar)')
    def promover_a_catalogo_general(self, request, queryset):
        # Solo tiene sentido sobre altas propias de un hogar (ver plan 2.1).
        pendientes = queryset.filter(hogar__isnull=False)
        total = pendientes.count()
        for medicamento in pendientes:
            medicamento.promover_a_catalogo_general()
        self.message_user(request, f'{total} medicamento(s) promovido(s) al catálogo general.')


@admin.register(ConfiguracionMedicamentos)
class ConfiguracionMedicamentosAdmin(admin.ModelAdmin):
    list_display = ['hogar', 'dias_semaforo_verde', 'dias_semaforo_amarillo', 'minutos_anulacion']
