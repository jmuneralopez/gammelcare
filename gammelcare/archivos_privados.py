"""Archivos clínicos privados: almacenamiento y validación compartidos.

Los archivos clínicos (resultados de exámenes, fotos de fórmulas médicas,
consentimientos firmados, etc.) son historia clínica: nunca se publican bajo
una URL estática. Viven en PRIVATE_MEDIA_ROOT y solo se entregan a través de
vistas que verifican rol y hogar y dejan registro en la auditoría.

La ubicación se lee de settings en cada acceso (no al cargar los modelos)
para que las pruebas puedan apuntarla a una carpeta temporal.
"""
import os

from django import forms
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class AlmacenamientoPrivado(FileSystemStorage):

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise NotImplementedError(
            'Los archivos clínicos no tienen URL pública; se sirven con una vista que verifica permisos.'
        )


almacenamiento_privado = AlmacenamientoPrivado()


TIPOS_PERMITIDOS = {
    'application/pdf': (b'%PDF',),
    'image/jpeg': (b'\xff\xd8\xff',),
    'image/png': (b'\x89PNG\r\n\x1a\n',),
}
EXTENSIONES_PERMITIDAS = {'.pdf', '.jpg', '.jpeg', '.png'}


def validar_archivo_clinico(archivo):
    """Acepta solo PDF, JPG y PNG, verificando la firma real del archivo
    (no solo la extensión) y el tamaño máximo (ARCHIVOS_CLINICOS_MAX_MB).
    Deja en `archivo.tipo_detectado` el tipo MIME real."""
    extension = os.path.splitext(archivo.name)[1].lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        raise forms.ValidationError(f'"{archivo.name}": solo se aceptan archivos PDF, JPG o PNG.')
    maximo_mb = getattr(settings, 'EXAMENES_MAX_MB', 10)
    if archivo.size > maximo_mb * 1024 * 1024:
        raise forms.ValidationError(f'"{archivo.name}" supera el tamaño máximo de {maximo_mb} MB.')
    archivo.seek(0)
    cabecera = archivo.read(8)
    archivo.seek(0)
    for content_type, firmas in TIPOS_PERMITIDOS.items():
        if any(cabecera.startswith(f) for f in firmas):
            archivo.tipo_detectado = content_type
            return archivo
    raise forms.ValidationError(f'"{archivo.name}" no parece un PDF o una imagen válida.')


def tipo_por_extension(nombre):
    extension = os.path.splitext(nombre)[1].lower()
    return {'.pdf': 'application/pdf', '.png': 'image/png'}.get(extension, 'image/jpeg')
