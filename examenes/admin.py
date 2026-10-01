from django.contrib import admin

from .models import AnalitoCatalogo, ArchivoResultado, Examen, RevisionMedica, ValorResultado


@admin.register(AnalitoCatalogo)
class AnalitoCatalogoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'unidad', 'ref_min', 'ref_max', 'critico_min', 'critico_max', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'codigo')
    ordering = ('orden', 'nombre')


class SoloLecturaAdmin(admin.ModelAdmin):
    """Los registros clínicos del módulo no se editan ni se borran desde el
    admin: la corrección es siempre una fila nueva con motivo."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Examen)
class ExamenAdmin(SoloLecturaAdmin):
    list_display = ('id', 'nombre', 'residente', 'tipo', 'estado', 'fecha_registro')
    list_filter = ('estado', 'tipo')


@admin.register(ValorResultado)
class ValorResultadoAdmin(SoloLecturaAdmin):
    list_display = ('examen', 'nombre', 'valor', 'unidad', 'fecha_registro')


@admin.register(ArchivoResultado)
class ArchivoResultadoAdmin(SoloLecturaAdmin):
    list_display = ('examen', 'nombre_original', 'content_type', 'tamano_bytes', 'fecha_subida')


@admin.register(RevisionMedica)
class RevisionMedicaAdmin(SoloLecturaAdmin):
    list_display = ('examen', 'medico', 'fecha')
