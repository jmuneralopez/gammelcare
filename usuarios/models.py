from django.db import models
from django.contrib.auth.models import AbstractUser
from hogares.models import Hogar


class Rol(models.Model):
    SUPERADMIN = 'superadmin'
    ADMINISTRADOR = 'administrador'
    CLINICO = 'clinico'

    ROLES = [
        (SUPERADMIN, 'Superadministrador'),
        (ADMINISTRADOR, 'Administrador del Hogar'),
        (CLINICO, 'Personal Clínico'),
    ]

    nombre = models.CharField(max_length=50, unique=True, choices=ROLES)
    descripcion = models.TextField(blank=True)

    class Meta:
        db_table = 'roles'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.get_nombre_display()


class Usuario(AbstractUser):
    rol = models.ForeignKey(
        Rol,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='usuarios'
    )
    hogar = models.ForeignKey(
        Hogar,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='usuarios'
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f'{self.get_full_name()} ({self.username})'