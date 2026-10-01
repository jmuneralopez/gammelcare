"""Citas médicas externas de cada residente.

Una cita es un compromiso fuera del hogar (o una visita que llega al hogar):
control con medicina general, especialista, odontología, toma de muestras,
imágenes, terapia. Lo que el hogar necesita saber es cuándo, dónde, cómo
prepararlo, quién lo acompaña y cómo llega; y después, qué pasó.

Ciclo de vida:
    programada → cumplida | no asistió | cancelada | reprogramada
- Mientras está programada se puede corregir.
- Reprogramar no cambia la fecha de la cita original: la cierra como
  "reprogramada" y crea una nueva enlazada, para que quede el rastro de
  cuántas veces se movió y por qué.
- Las citas no se borran.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from gammelcare.archivos_privados import almacenamiento_privado
from residentes.models import Residente


def _ruta_soporte(instancia, nombre):
    return f'citas/hogar_{instancia.residente.hogar_id}/residente_{instancia.residente_id}/{nombre}'


class Cita(models.Model):
    CONTROL = 'control'
    ESPECIALISTA = 'especialista'
    ODONTOLOGIA = 'odontologia'
    TOMA_MUESTRA = 'toma_muestra'
    IMAGEN = 'imagen'
    TERAPIA = 'terapia'
    PROCEDIMIENTO = 'procedimiento'
    OTRO = 'otro'
    TIPOS = [
        (CONTROL, 'Control de medicina general'),
        (ESPECIALISTA, 'Especialista'),
        (ODONTOLOGIA, 'Odontología'),
        (TOMA_MUESTRA, 'Toma de muestras de laboratorio'),
        (IMAGEN, 'Imágenes diagnósticas'),
        (TERAPIA, 'Terapia'),
        (PROCEDIMIENTO, 'Procedimiento'),
        (OTRO, 'Otra'),
    ]

    PROGRAMADA = 'programada'
    CUMPLIDA = 'cumplida'
    NO_ASISTIO = 'no_asistio'
    CANCELADA = 'cancelada'
    REPROGRAMADA = 'reprogramada'
    ESTADOS = [
        (PROGRAMADA, 'Programada'),
        (CUMPLIDA, 'Cumplida'),
        (NO_ASISTIO, 'No asistió'),
        (CANCELADA, 'Cancelada'),
        (REPROGRAMADA, 'Reprogramada'),
    ]

    POR_DEFINIR = 'por_definir'
    TRANSPORTES = [
        (POR_DEFINIR, 'Por definir'),
        ('hogar', 'Vehículo del hogar'),
        ('familia', 'La familia lo lleva'),
        ('eps', 'Transporte de la EPS'),
        ('ambulancia', 'Ambulancia'),
        ('taxi', 'Taxi o transporte público'),
        ('en_el_hogar', 'No sale: la atención es en el hogar'),
    ]

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='citas')
    tipo = models.CharField('Tipo de cita', max_length=20, choices=TIPOS, default=CONTROL)
    especialidad = models.CharField('Especialidad o servicio', max_length=120, blank=True)
    profesional = models.CharField('Profesional', max_length=120, blank=True)
    lugar = models.CharField('Lugar (entidad y dirección)', max_length=200)
    fecha_hora = models.DateTimeField('Fecha y hora')
    requiere_ayuno = models.BooleanField('Requiere ayuno', default=False)
    preparacion = models.TextField('Preparación e indicaciones', blank=True)
    acompanante = models.CharField('Quién lo acompaña', max_length=120, blank=True)
    transporte = models.CharField('Transporte', max_length=20, choices=TRANSPORTES, default=POR_DEFINIR)
    observaciones = models.TextField('Observaciones', blank=True)

    estado = models.CharField(max_length=15, choices=ESTADOS, default=PROGRAMADA)
    resumen = models.TextField('Qué pasó en la cita', blank=True)
    archivo_soporte = models.FileField(
        'Soporte (fórmula, orden o resumen)', upload_to=_ruta_soporte,
        storage=almacenamiento_privado, blank=True,
    )
    cerrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    reprogramada_desde = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='reprogramada_en',
    )

    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['fecha_hora']
        verbose_name = 'Cita médica'
        verbose_name_plural = 'Citas médicas'
        indexes = [models.Index(fields=['estado', 'fecha_hora'])]

    def __str__(self):
        return f'{self.titulo} — {timezone.localtime(self.fecha_hora):%d/%m/%Y %H:%M}'

    def delete(self, *args, **kwargs):
        raise ValueError('Las citas no se eliminan: se cancelan con motivo.')

    @property
    def titulo(self):
        if self.especialidad:
            return f'{self.get_tipo_display()} — {self.especialidad}'
        return self.get_tipo_display()

    @property
    def abierta(self):
        return self.estado == self.PROGRAMADA

    @property
    def vencida_sin_cierre(self):
        """Ya pasó la hora y nadie registró qué pasó."""
        return self.abierta and self.fecha_hora < timezone.now()

    @property
    def nombre_residente(self):
        return self.residente.get_nombre()
