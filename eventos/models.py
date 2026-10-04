"""Eventos adversos: caídas, errores de medicación, lesiones por presión
aparecidas en el hogar, fugas, broncoaspiración, agresiones y otros.

- El reporte no se edita ni se borra: el análisis, las acciones de mejora y el
  cierre se agregan después, y las notas de seguimiento se suman sin cambiar
  lo anterior. Huella SHA-256 del reporte.
- Cada hogar elige cómo se identifica a quien reporta (ConfiguracionEventos):
  identificado, confidencial (solo lo ve el jefe de enfermería) o anónimo
  voluntario (quien reporta puede no dejar su nombre; entonces no se guarda).
- Después de una caída queda programada la vigilancia (conciencia, dolor,
  signos) cada cierto número de horas durante 72 horas.
"""
import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone

from hogares.models import Hogar
from residentes.models import Residente

CAIDA, MEDICACION, LPP = 'caida', 'medicacion', 'lpp'
TIPOS = [
    (CAIDA, 'Caída'),
    (MEDICACION, 'Error de medicación'),
    (LPP, 'Lesión por presión aparecida en el hogar'),
    ('reaccion', 'Reacción adversa a un medicamento'),
    ('fuga', 'Fuga o salida no autorizada'),
    ('broncoaspiracion', 'Atragantamiento o broncoaspiración'),
    ('agresion', 'Agresión o conflicto entre residentes'),
    ('lesion', 'Lesión, golpe o quemadura'),
    ('otro', 'Otro'),
]
GRAVEDADES = [
    ('sin_dano', 'Sin daño'),
    ('leve', 'Daño leve (no requiere más que primeros auxilios)'),
    ('moderado', 'Daño moderado (requiere atención médica o tratamiento)'),
    ('grave', 'Daño grave (hospitalización o lesión permanente)'),
    ('muerte', 'Muerte'),
]
GRAVEDADES_ALTAS = {'moderado', 'grave', 'muerte'}
LUGARES = [
    ('habitacion', 'Habitación'), ('bano', 'Baño'), ('comedor', 'Comedor'), ('pasillo', 'Pasillo'),
    ('sala', 'Sala o zona común'), ('exterior', 'Patio o zona exterior'), ('escaleras', 'Escaleras'),
    ('fuera', 'Fuera del hogar'), ('otro', 'Otro'),
]
ERRORES_MEDICACION = [
    ('omision', 'No se suministró una dosis'),
    ('dosis', 'Dosis equivocada'),
    ('medicamento', 'Medicamento equivocado'),
    ('residente', 'Residente equivocado'),
    ('hora', 'Hora equivocada'),
    ('via', 'Vía equivocada'),
    ('vencido', 'Medicamento vencido'),
    ('otro', 'Otro'),
]


class ConfiguracionEventos(models.Model):
    IDENTIFICADO, CONFIDENCIAL, ANONIMO = 'identificado', 'confidencial', 'anonimo'
    MODOS = [
        (IDENTIFICADO, 'Identificado: el jefe de enfermería, el médico y el administrador ven quién reportó'),
        (CONFIDENCIAL, 'Confidencial: solo el jefe de enfermería ve quién reportó; en listados e indicadores no aparece'),
        (ANONIMO, 'Anónimo voluntario: quien reporta puede no dejar su nombre (no se guarda en ninguna parte)'),
    ]
    hogar = models.OneToOneField(Hogar, on_delete=models.CASCADE, related_name='configuracion_eventos')
    modo_reporte = models.CharField('Quién reportó', max_length=15, choices=MODOS, default=CONFIDENCIAL)
    horas_vigilancia_caida = models.PositiveSmallIntegerField('Horas de vigilancia después de una caída', default=72)
    intervalo_vigilancia_horas = models.PositiveSmallIntegerField('Revisar cada (horas)', default=8)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='+')
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración de eventos adversos'
        verbose_name_plural = 'Configuraciones de eventos adversos'

    @classmethod
    def para_hogar(cls, hogar):
        config, _ = cls.objects.get_or_create(hogar=hogar)
        return config


class EventoAdverso(models.Model):
    ABIERTO, CERRADO = 'abierto', 'cerrado'
    ESTADOS = [(ABIERTO, 'Por analizar'), (CERRADO, 'Analizado y cerrado')]
    ORIGENES = [('manual', 'Reporte del personal'), ('herida', 'Desde una herida'),
                ('medicamento', 'Desde una corrección de suministro')]

    hogar = models.ForeignKey(Hogar, on_delete=models.PROTECT, related_name='eventos_adversos')
    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='eventos_adversos')
    tipo = models.CharField('Tipo de evento', max_length=20, choices=TIPOS)
    fecha_hora = models.DateTimeField('Cuándo pasó', default=timezone.now)
    lugar = models.CharField('Dónde pasó', max_length=15, choices=LUGARES, default='habitacion')
    lugar_detalle = models.CharField('Detalle del lugar', max_length=120, blank=True)
    descripcion = models.TextField('Qué pasó')
    testigo = models.CharField('Quién lo presenció o lo encontró', max_length=150, blank=True)
    accion_inmediata = models.TextField('Qué se hizo en el momento')
    gravedad = models.CharField('Daño al residente', max_length=10, choices=GRAVEDADES)
    aviso_medico = models.BooleanField('Se avisó al médico', default=False)
    aviso_familia = models.BooleanField('Se avisó a la familia', default=False)
    aviso_familia_quien = models.CharField('A quién de la familia', max_length=120, blank=True)

    # Caídas
    golpe_cabeza = models.BooleanField('Se golpeó la cabeza', default=False)
    perdida_conciencia = models.BooleanField('Perdió el conocimiento', default=False)
    anticoagulantes = models.BooleanField('Toma anticoagulantes', default=False)
    lesiones = models.TextField('Lesiones encontradas', blank=True)
    # Medicación
    tipo_error = models.CharField('Qué falló', max_length=15, choices=ERRORES_MEDICACION, blank=True)
    prescripcion = models.ForeignKey('medicamentos.Prescripcion', on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='eventos_adversos', verbose_name='Orden médica')
    administracion = models.ForeignKey('medicamentos.Administracion', on_delete=models.PROTECT, null=True,
                                       blank=True, related_name='eventos_adversos')
    # Lesión por presión
    herida = models.ForeignKey('cuidados.Herida', on_delete=models.PROTECT, null=True, blank=True,
                               related_name='eventos_adversos')

    origen = models.CharField(max_length=12, choices=ORIGENES, default='manual')
    anonimo = models.BooleanField(default=False)
    reportado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='+')
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)
    hash_integridad = models.CharField(max_length=64, editable=False, blank=True)

    # Análisis y cierre (se completan una vez)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=ABIERTO)
    causas = models.TextField('Por qué pasó (causas)', blank=True)
    acciones_mejora = models.TextField('Qué se va a hacer para que no se repita', blank=True)
    responsable_acciones = models.CharField('Responsable de las acciones', max_length=150, blank=True)
    fecha_limite_acciones = models.DateField('Fecha límite de las acciones', null=True, blank=True)
    cerrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+')
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    CAMPOS_REPORTE = ['residente_id', 'tipo', 'fecha_hora', 'lugar', 'lugar_detalle', 'descripcion', 'testigo',
                      'accion_inmediata', 'gravedad', 'aviso_medico', 'aviso_familia', 'aviso_familia_quien',
                      'golpe_cabeza', 'perdida_conciencia', 'anticoagulantes', 'lesiones', 'tipo_error',
                      'prescripcion_id', 'administracion_id', 'herida_id', 'reportado_por_id', 'anonimo']
    CAMPOS_CIERRE = {'estado', 'causas', 'acciones_mejora', 'responsable_acciones', 'fecha_limite_acciones',
                     'cerrado_por', 'fecha_cierre'}

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = 'Evento adverso'
        verbose_name_plural = 'Eventos adversos'
        indexes = [models.Index(fields=['hogar', 'fecha_hora']), models.Index(fields=['residente', 'fecha_hora'])]

    def __str__(self):
        return f'{self.get_tipo_display()} — {timezone.localtime(self.fecha_hora):%d/%m/%Y %H:%M}'

    def calcular_hash(self):
        partes = []
        for c in self.CAMPOS_REPORTE:
            v = getattr(self, c)
            if hasattr(v, 'timestamp'):
                v = int(v.timestamp())
            partes.append('' if v is None else str(v))
        return hashlib.sha256('|'.join(partes).encode('utf-8')).hexdigest()

    def verificar_integridad(self):
        return self.hash_integridad == self.calcular_hash()

    def save(self, *args, **kwargs):
        if not self.pk:
            self.hash_integridad = self.calcular_hash()
        else:
            campos = kwargs.get('update_fields')
            if not campos or not set(campos) <= self.CAMPOS_CIERRE:
                raise ValueError('El reporte de un evento no se modifica: se agregan notas de seguimiento.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Los eventos adversos no se eliminan.')

    @property
    def grave(self):
        return self.gravedad in GRAVEDADES_ALTAS

    @property
    def abierto(self):
        return self.estado == self.ABIERTO


class NotaEvento(models.Model):
    """Nota de seguimiento de un evento (lo que se averiguó, a quién se avisó)."""
    evento = models.ForeignKey(EventoAdverso, on_delete=models.PROTECT, related_name='notas')
    texto = models.TextField('Nota')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['fecha']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError('Las notas de seguimiento no se modifican.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Las notas de seguimiento no se eliminan.')


class VigilanciaEvento(models.Model):
    """Revisión programada después de una caída."""
    CONCIENCIAS = [
        ('alerta', 'Alerta y orientado, como siempre'),
        ('somnoliento', 'Más somnoliento de lo usual'),
        ('confuso', 'Confuso o desorientado'),
        ('no_responde', 'No responde o cuesta despertarlo'),
    ]
    evento = models.ForeignKey(EventoAdverso, on_delete=models.PROTECT, related_name='vigilancias')
    programada = models.DateTimeField()
    realizada = models.DateTimeField(null=True, blank=True)
    realizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='+')
    conciencia = models.CharField('Estado de conciencia', max_length=15, choices=CONCIENCIAS, blank=True)
    dolor = models.PositiveSmallIntegerField('Dolor (0 a 10)', null=True, blank=True)
    hallazgos = models.TextField('Hallazgos (signos, hematomas, cómo camina)', blank=True)
    requiere_medico = models.BooleanField('Necesita valoración médica', default=False)

    class Meta:
        ordering = ['programada']

    @property
    def pendiente(self):
        return self.realizada is None

    @property
    def vencida(self):
        return self.pendiente and self.programada < timezone.now()

    @property
    def preocupante(self):
        return self.requiere_medico or self.conciencia in ('confuso', 'no_responde') or (self.dolor or 0) >= 7
