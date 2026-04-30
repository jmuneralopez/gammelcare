from django.db import models
from cryptography.fernet import Fernet
from django.conf import settings
from hogares.models import Hogar
from infraestructura.models import Cama


class Residente(models.Model):
    hogar = models.ForeignKey(
        Hogar,
        on_delete=models.PROTECT,
        related_name='residentes'
    )
    cama_actual = models.OneToOneField(
        Cama,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='residente_actual'
    )
    # Campos cifrados
    nombre_completo = models.BinaryField()
    numero_documento = models.BinaryField()
    contacto_emergencia = models.BinaryField()

    fecha_nacimiento = models.DateField()
    activo = models.BooleanField(default=True)
    fecha_ingreso = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'residentes'
        verbose_name = 'Residente'
        verbose_name_plural = 'Residentes'

    def __str__(self):
        return f'Residente #{self.pk}'

    def _get_fernet(self):
        return Fernet(settings.FERNET_KEY.encode())

    def set_nombre(self, valor):
        self.nombre_completo = self._get_fernet().encrypt(valor.encode())

    def get_nombre(self):
        return self._get_fernet().decrypt(bytes(self.nombre_completo)).decode()

    def set_documento(self, valor):
        self.numero_documento = self._get_fernet().encrypt(valor.encode())

    def get_documento(self):
        return self._get_fernet().decrypt(bytes(self.numero_documento)).decode()

    def set_contacto(self, valor):
        self.contacto_emergencia = self._get_fernet().encrypt(valor.encode())

    def get_contacto(self):
        return self._get_fernet().decrypt(bytes(self.contacto_emergencia)).decode()


class AsignacionCama(models.Model):
    residente = models.ForeignKey(
        Residente,
        on_delete=models.PROTECT,
        related_name='asignaciones'
    )
    cama = models.ForeignKey(
        Cama,
        on_delete=models.PROTECT,
        related_name='asignaciones'
    )
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'asignaciones_cama'
        verbose_name = 'Asignación de Cama'
        verbose_name_plural = 'Asignaciones de Cama'
        ordering = ['-fecha_inicio']

    def __str__(self):
        return f'{self.residente} — Cama {self.cama} ({self.fecha_inicio.date()})'