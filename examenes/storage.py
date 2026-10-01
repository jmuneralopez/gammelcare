"""Almacenamiento privado para los resultados de exámenes.

Los resultados son historia clínica: nunca se publican bajo una URL
estática. Viven fuera de STATIC/MEDIA, en PRIVATE_MEDIA_ROOT, y solo se
entregan a través de la vista `archivo_ver`, que verifica rol y hogar y deja
registro en la auditoría.

La ubicación se lee de settings en cada acceso (no al cargar el modelo) para
que las pruebas puedan apuntarla a una carpeta temporal.
"""
import os

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
            'Los resultados de exámenes no tienen URL pública; use la vista archivo_ver.'
        )


almacenamiento_privado = AlmacenamientoPrivado()
