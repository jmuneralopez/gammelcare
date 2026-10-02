"""Plan de atención integral individual (PAI).

Un plan es interdisciplinario: cada profesional agrega objetivos de su área
mientras el plan está en borrador; el médico o el jefe de enfermería lo
activan. Solo hay un plan vigente por residente; activar uno nuevo deja el
anterior como "reemplazado" (queda en el historial, no se borra).

Ciclo de vida del plan:
    borrador → vigente → reemplazado
- En borrador se agregan, corrigen y quitan objetivos.
- Vigente: los objetivos ya no se editan; se les registra seguimiento
  (avance) y, si hace falta, se agregan objetivos nuevos.
- "Revisar plan" crea la siguiente versión en borrador, copiando los
  objetivos que siguen en curso.

Cada objetivo: área, necesidad o problema, meta, intervenciones, rol
responsable, frecuencia, fecha meta y estado (en curso, logrado,
parcialmente logrado, no logrado, suspendido). El estado cambia solo con un
seguimiento, que queda registrado con autor y fecha.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from residentes.models import Residente
from usuarios.models import Rol


class PlanAtencion(models.Model):
    BORRADOR = 'borrador'
    VIGENTE = 'vigente'
    REEMPLAZADO = 'reemplazado'
    ESTADOS = [(BORRADOR, 'Borrador'), (VIGENTE, 'Vigente'), (REEMPLAZADO, 'Reemplazado')]

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='planes_atencion')
    version = models.PositiveSmallIntegerField(default=1)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=BORRADOR)
    resumen = models.TextField('Situación actual del residente', blank=True,
                               help_text='Resumen de la valoración integral que justifica el plan.')
    participantes = models.TextField('Quiénes participaron', blank=True,
                                     help_text='Profesionales, el residente y su familia.')
    acuerdos_familia = models.TextField('Acuerdos con el residente y la familia', blank=True)
    fecha_revision = models.DateField('Próxima revisión')
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_creacion = models.DateTimeField(default=timezone.now, editable=False)
    activado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+')
    fecha_activacion = models.DateTimeField(null=True, blank=True)
    fecha_reemplazo = models.DateTimeField(null=True, blank=True)
    anterior = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='siguiente')

    class Meta:
        ordering = ['-version']
        verbose_name = 'Plan de atención'
        verbose_name_plural = 'Planes de atención'
        constraints = [
            models.UniqueConstraint(fields=['residente', 'version'], name='plan_version_unica'),
            models.UniqueConstraint(fields=['residente'], condition=Q(estado='vigente'), name='plan_vigente_unico'),
            models.UniqueConstraint(fields=['residente'], condition=Q(estado='borrador'), name='plan_borrador_unico'),
        ]

    def __str__(self):
        return f'Plan de atención v{self.version} — {self.get_estado_display()}'

    def delete(self, *args, **kwargs):
        if self.estado != self.BORRADOR:
            raise ValueError('Un plan activado no se elimina: queda en el historial.')
        super().delete(*args, **kwargs)

    @property
    def editable(self):
        return self.estado == self.BORRADOR

    @property
    def revision_vencida(self):
        return self.estado == self.VIGENTE and self.fecha_revision < timezone.localdate()

    def avance(self):
        objetivos = [o for o in self.objetivos.all() if o.estado != ObjetivoPlan.SUSPENDIDO]
        if not objetivos:
            return None
        logrados = sum(1 for o in objetivos if o.estado == ObjetivoPlan.LOGRADO)
        return {'logrados': logrados, 'total': len(objetivos), 'porcentaje': round(100 * logrados / len(objetivos))}


class ObjetivoPlan(models.Model):
    AREAS = [
        ('funcional', 'Funcionalidad y autocuidado'),
        ('caidas', 'Movilidad y prevención de caídas'),
        ('cognitivo', 'Cognición y orientación'),
        ('afectivo', 'Estado de ánimo y salud emocional'),
        ('nutricion', 'Nutrición e hidratación'),
        ('piel', 'Piel y prevención de lesiones por presión'),
        ('eliminacion', 'Eliminación (orina y deposición)'),
        ('medicacion', 'Medicamentos y condiciones crónicas'),
        ('dolor', 'Dolor y confort'),
        ('social', 'Familia y red de apoyo'),
        ('actividades', 'Actividades, ocio y participación'),
        ('otro', 'Otra'),
    ]
    EN_CURSO = 'en_curso'
    LOGRADO = 'logrado'
    PARCIAL = 'parcial'
    NO_LOGRADO = 'no_logrado'
    SUSPENDIDO = 'suspendido'
    ESTADOS = [(EN_CURSO, 'En curso'), (LOGRADO, 'Logrado'), (PARCIAL, 'Parcialmente logrado'),
               (NO_LOGRADO, 'No logrado'), (SUSPENDIDO, 'Suspendido')]
    ROLES_RESPONSABLES = [(c, n) for c, n in Rol.ROLES if c not in (Rol.SUPERADMIN,)]

    plan = models.ForeignKey(PlanAtencion, on_delete=models.CASCADE, related_name='objetivos')
    area = models.CharField('Área', max_length=15, choices=AREAS)
    necesidad = models.TextField('Necesidad o problema', help_text='Qué se encontró en la valoración.')
    meta = models.TextField('Objetivo', help_text='Qué se quiere lograr, de forma que se pueda verificar.')
    intervenciones = models.TextField('Intervenciones', help_text='Qué se va a hacer, cómo y cada cuánto.')
    responsable = models.CharField('Rol responsable', max_length=30, choices=ROLES_RESPONSABLES)
    frecuencia = models.CharField('Frecuencia', max_length=80, blank=True)
    fecha_meta = models.DateField('Fecha para evaluarlo')
    estado = models.CharField(max_length=12, choices=ESTADOS, default=EN_CURSO)
    origen = models.CharField(max_length=60, blank=True, help_text='Escala o hallazgo que lo sugirió.')
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_creacion = models.DateTimeField(default=timezone.now, editable=False)
    copiado_de = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['area', 'fecha_creacion']
        verbose_name = 'Objetivo del plan'
        verbose_name_plural = 'Objetivos del plan'

    def __str__(self):
        return f'{self.get_area_display()}: {self.meta[:60]}'

    @property
    def vencido(self):
        return self.estado == self.EN_CURSO and self.fecha_meta < timezone.localdate()


class SeguimientoObjetivo(models.Model):
    """Registro de avance de un objetivo. Inmutable."""
    objetivo = models.ForeignKey(ObjetivoPlan, on_delete=models.CASCADE, related_name='seguimientos')
    estado = models.CharField('Estado del objetivo', max_length=12, choices=ObjetivoPlan.ESTADOS)
    nota = models.TextField('Qué se observó')
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Seguimiento de objetivo'
        verbose_name_plural = 'Seguimientos de objetivos'

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError('Los seguimientos no se modifican.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Los seguimientos no se eliminan.')
