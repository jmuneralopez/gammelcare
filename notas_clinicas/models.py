from django.db import models
from django.conf import settings
import hashlib
from residentes.models import Residente


class NotaClinica(models.Model):
    ENFERMERIA = 'enfermeria'
    EVOLUCION = 'evolucion'

    TIPOS = [
        (ENFERMERIA, 'Nota de Enfermería'),
        (EVOLUCION, 'Evolución Médica'),
    ]

    residente = models.ForeignKey(
        Residente,
        on_delete=models.PROTECT,
        related_name='notas'
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='notas_creadas'
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    contenido = models.TextField()
    hash_integridad = models.CharField(max_length=64, editable=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notas_clinicas'
        verbose_name = 'Nota Clínica'
        verbose_name_plural = 'Notas Clínicas'
        ordering = ['-fecha_creacion']

    def save(self, *args, **kwargs):
        # Generar hash antes de guardar — inmutabilidad
        if not self.pk:
            self.hash_integridad = hashlib.sha256(
                self.contenido.encode('utf-8')
            ).hexdigest()
        else:
            raise ValueError(
                'Las notas clínicas son inmutables y no pueden modificarse.'
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.residente} ({self.fecha_creacion.date()})'


class NotaAclaratoria(models.Model):
    nota_original = models.ForeignKey(
        NotaClinica,
        on_delete=models.PROTECT,
        related_name='aclaraciones'
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='aclaraciones_creadas'
    )
    contenido = models.TextField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notas_aclaratorias'
        verbose_name = 'Nota Aclaratoria'
        verbose_name_plural = 'Notas Aclaratorias'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f'Aclaración de nota #{self.nota_original.pk} ({self.fecha_creacion.date()})'