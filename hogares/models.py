from django.db import models


class Hogar(models.Model):
    nombre = models.CharField(max_length=200)
    nit = models.CharField(max_length=20, unique=True)
    direccion = models.CharField(max_length=300)
    telefono = models.CharField(max_length=20, blank=True)
    correo = models.EmailField(blank=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hogares'
        verbose_name = 'Hogar'
        verbose_name_plural = 'Hogares'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre