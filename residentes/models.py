from django.db import models
from cryptography.fernet import Fernet
from django.conf import settings
from hogares.models import Hogar
from infraestructura.models import Cama


class Residente(models.Model):

    TIPO_DOCUMENTO = [
        ('CC', 'Cédula de Ciudadanía'),
        ('CE', 'Cédula de Extranjería'),
        ('PA', 'Pasaporte'),
        ('RC', 'Registro Civil'),
        ('TI', 'Tarjeta de Identidad'),
        ('NIT', 'NIT'),
    ]

    MOTIVO_RETIRO = [
        ('obito', 'Óbito'),
        ('fuga', 'Fuga'),
        ('retiro_voluntario', 'Retiro Voluntario'),
        ('traslado', 'Traslado'),
    ]

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

    # Campos básicos
    tipo_documento = models.CharField(
        max_length=10,
        choices=TIPO_DOCUMENTO,
        default='CC'
    )
    fecha_nacimiento = models.DateField()
    nacionalidad = models.CharField(max_length=100, default='Colombiana')
    eps = models.CharField(max_length=150, blank=True, verbose_name='EPS')
    servicio_ambulancia = models.CharField(
        max_length=150,
        blank=True,
        verbose_name='Servicio de Ambulancia'
    )

    # Estado
    activo = models.BooleanField(default=True)
    motivo_retiro = models.CharField(
        max_length=20,
        choices=MOTIVO_RETIRO,
        blank=True,
        null=True
    )
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


class ExpedienteIngreso(models.Model):
    residente = models.OneToOneField(
        Residente,
        on_delete=models.CASCADE,
        related_name='expediente'
    )

    # Clínico
    diagnosticos = models.TextField(
        blank=True,
        verbose_name='Diagnósticos'
    )
    examen_ingreso = models.TextField(
        blank=True,
        verbose_name='Examen de Ingreso'
    )
    alergias = models.TextField(
        blank=True,
        verbose_name='Alergias'
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name='Observaciones'
    )

    # Inventario
    inventario_ingreso = models.TextField(
        blank=True,
        verbose_name='Inventario de Ingreso',
        help_text='Lista de pertenencias del residente al momento del ingreso'
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expedientes_ingreso'
        verbose_name = 'Expediente de Ingreso'
        verbose_name_plural = 'Expedientes de Ingreso'

    def __str__(self):
        return f'Expediente de {self.residente}'