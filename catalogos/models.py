from django.db import models


class EPS(models.Model):
    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=20, blank=True, verbose_name='Código')
    telefono = models.CharField(max_length=20, blank=True, verbose_name='Teléfono')
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'catalogos_eps'
        verbose_name = 'EPS'
        verbose_name_plural = 'EPS'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class ServicioAmbulancia(models.Model):
    nombre = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20, blank=True, verbose_name='Teléfono')
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'catalogos_servicio_ambulancia'
        verbose_name = 'Servicio de Ambulancia'
        verbose_name_plural = 'Servicios de Ambulancia'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class CodigoCIE10(models.Model):
    codigo = models.CharField(max_length=10, unique=True, verbose_name='Código')
    descripcion = models.CharField(max_length=500, verbose_name='Descripción')
    categoria = models.CharField(max_length=200, blank=True, verbose_name='Categoría')

    class Meta:
        db_table = 'catalogos_cie10'
        verbose_name = 'Código CIE-10'
        verbose_name_plural = 'Códigos CIE-10'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} — {self.descripcion}'