from django.db import models
from hogares.models import Hogar


class Departamento(models.Model):
    hogar = models.ForeignKey(
        Hogar,
        on_delete=models.CASCADE,
        related_name='departamentos'
    )
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'departamentos'
        verbose_name = 'Departamento'
        verbose_name_plural = 'Departamentos'
        ordering = ['hogar', 'nombre']

    def __str__(self):
        return f'{self.hogar} — {self.nombre}'


class Habitacion(models.Model):
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.CASCADE,
        related_name='habitaciones'
    )
    numero = models.CharField(max_length=10)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'habitaciones'
        verbose_name = 'Habitación'
        verbose_name_plural = 'Habitaciones'
        ordering = ['departamento', 'numero']

    def __str__(self):
        return f'Hab. {self.numero} — {self.departamento}'


class Cama(models.Model):
    DISPONIBLE = 'disponible'
    OCUPADA = 'ocupada'
    MANTENIMIENTO = 'mantenimiento'

    ESTADOS = [
        (DISPONIBLE, 'Disponible'),
        (OCUPADA, 'Ocupada'),
        (MANTENIMIENTO, 'En mantenimiento'),
    ]

    habitacion = models.ForeignKey(
        Habitacion,
        on_delete=models.CASCADE,
        related_name='camas'
    )
    codigo = models.CharField(max_length=20)
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=DISPONIBLE
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'camas'
        verbose_name = 'Cama'
        verbose_name_plural = 'Camas'
        ordering = ['habitacion', 'codigo']

    def __str__(self):
        return f'Cama {self.codigo} — {self.habitacion} [{self.get_estado_display()}]'