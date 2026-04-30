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

    # Catálogos
    eps = models.ForeignKey(
        'catalogos.EPS',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='EPS'
    )
    servicio_ambulancia = models.ForeignKey(
        'catalogos.ServicioAmbulancia',
        on_delete=models.SET_NULL,
        null=True,
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


class ExamenIngreso(models.Model):

    PROCEDENCIA = [
        ('hogar', 'Hogar familiar'),
        ('hospital', 'Hospital'),
        ('clinica', 'Clínica'),
        ('otro_hogar', 'Otro hogar geriátrico'),
        ('otro', 'Otro'),
    ]

    ESTADO_MENTAL = [
        ('orientado', 'Orientado'),
        ('desorientado_parcial', 'Desorientado parcialmente'),
        ('desorientado_total', 'Desorientado totalmente'),
        ('sedado', 'Sedado'),
        ('inconsciente', 'Inconsciente'),
    ]

    MOVILIDAD = [
        ('independiente', 'Independiente'),
        ('ayuda_parcial', 'Con ayuda parcial'),
        ('dependiente', 'Dependiente total'),
        ('en_cama', 'Postrado en cama'),
    ]

    CONDICION_NUTRICIONAL = [
        ('normal', 'Normal'),
        ('desnutricion_leve', 'Desnutrición leve'),
        ('desnutricion_moderada', 'Desnutrición moderada'),
        ('desnutricion_severa', 'Desnutrición severa'),
        ('sobrepeso', 'Sobrepeso'),
        ('obesidad', 'Obesidad'),
    ]

    residente = models.OneToOneField(
        Residente,
        on_delete=models.CASCADE,
        related_name='examen_ingreso'
    )

    # Signos vitales y medidas
    peso = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name='Peso (kg)'
    )
    talla = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name='Talla (cm)'
    )
    presion_arterial = models.CharField(
        max_length=20, blank=True,
        verbose_name='Presión arterial (mmHg)'
    )
    frecuencia_cardiaca = models.IntegerField(
        null=True, blank=True,
        verbose_name='Frecuencia cardíaca (lpm)'
    )
    temperatura = models.DecimalField(
        max_digits=4, decimal_places=1,
        null=True, blank=True,
        verbose_name='Temperatura (°C)'
    )
    saturacion_oxigeno = models.DecimalField(
        max_digits=4, decimal_places=1,
        null=True, blank=True,
        verbose_name='Saturación O2 (%)'
    )

    # Evaluación clínica
    procedencia = models.CharField(
        max_length=20,
        choices=PROCEDENCIA,
        blank=True
    )
    estado_mental = models.CharField(
        max_length=30,
        choices=ESTADO_MENTAL,
        blank=True,
        verbose_name='Estado mental'
    )
    movilidad = models.CharField(
        max_length=20,
        choices=MOVILIDAD,
        blank=True
    )
    condicion_nutricional = models.CharField(
        max_length=30,
        choices=CONDICION_NUTRICIONAL,
        blank=True,
        verbose_name='Condición nutricional'
    )

    # Observaciones y antecedentes
    observaciones_fisicas = models.TextField(
        blank=True,
        verbose_name='Observaciones físicas',
        help_text='Golpes, cortes, heridas, amputaciones u otras condiciones físicas observadas'
    )
    antecedentes_medicos = models.TextField(
        blank=True,
        verbose_name='Antecedentes médicos'
    )
    antecedentes_familiares = models.TextField(
        blank=True,
        verbose_name='Antecedentes familiares'
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'examenes_ingreso'
        verbose_name = 'Examen de Ingreso'
        verbose_name_plural = 'Exámenes de Ingreso'

    def imc(self):
        if self.peso and self.talla and self.talla > 0:
            talla_m = float(self.talla) / 100
            return round(float(self.peso) / (talla_m ** 2), 2)
        return None


class DiagnosticoResidente(models.Model):
    residente = models.ForeignKey(
        Residente,
        on_delete=models.CASCADE,
        related_name='diagnosticos'
    )
    codigo_cie10 = models.ForeignKey(
        'catalogos.CodigoCIE10',
        on_delete=models.PROTECT,
        verbose_name='Código CIE-10'
    )
    observacion = models.TextField(
        blank=True,
        verbose_name='Observación'
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'diagnosticos_residente'
        verbose_name = 'Diagnóstico'
        verbose_name_plural = 'Diagnósticos'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f'{self.codigo_cie10} — Residente #{self.residente.pk}'


class ExpedienteIngreso(models.Model):
    residente = models.OneToOneField(
        Residente,
        on_delete=models.CASCADE,
        related_name='expediente'
    )
    alergias = models.TextField(blank=True, verbose_name='Alergias')
    inventario_ingreso = models.TextField(
        blank=True,
        verbose_name='Inventario de Ingreso'
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name='Observaciones generales'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expedientes_ingreso'
        verbose_name = 'Expediente de Ingreso'
        verbose_name_plural = 'Expedientes de Ingreso'

    def __str__(self):
        return f'Expediente de {self.residente}'