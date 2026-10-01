"""Alergias y antecedentes estructurados del residente.

Reemplazan los campos de texto libre del expediente de ingreso
(`ExpedienteIngreso.alergias`, `ExamenIngreso.antecedentes_*`), que siguen
visibles como "registro anterior" hasta que alguien los estructure.

Reglas:
- Nada se borra: una alergia o un antecedente registrado por error, o
  descartado después (por ejemplo, una alergia que una prueba descartó), se
  inactiva con motivo y queda en el historial.
- "Sin alergias conocidas" es una declaración explícita, distinta de "nadie
  ha preguntado". Registrar una alergia la anula automáticamente.
- Las alergias a medicamentos pueden enlazarse al catálogo de medicamentos
  para que el sistema avise al registrar una orden médica.
"""
import unicodedata

from django.conf import settings
from django.db import models
from django.utils import timezone

from residentes.models import Residente


def normalizar(texto):
    """Minúsculas y sin tildes, para comparar nombres de sustancias."""
    texto = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in texto if not unicodedata.combining(c)).lower().strip()


class RegistroInactivable(models.Model):
    activo = models.BooleanField(default=True)
    motivo_inactivacion = models.TextField(blank=True)
    inactivado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )
    fecha_inactivacion = models.DateTimeField(null=True, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValueError('Los antecedentes no se eliminan: se inactivan con motivo.')

    def inactivar(self, usuario, motivo):
        self.activo = False
        self.motivo_inactivacion = motivo
        self.inactivado_por = usuario
        self.fecha_inactivacion = timezone.now()
        self.save(update_fields=['activo', 'motivo_inactivacion', 'inactivado_por', 'fecha_inactivacion'])


class Alergia(RegistroInactivable):
    MEDICAMENTO = 'medicamento'
    ALIMENTO = 'alimento'
    AMBIENTAL = 'ambiental'
    OTRA = 'otra'
    TIPOS = [
        (MEDICAMENTO, 'Medicamento'),
        (ALIMENTO, 'Alimento'),
        (AMBIENTAL, 'Ambiental (polen, ácaros, látex…)'),
        (OTRA, 'Otra'),
    ]

    REACCIONES = [
        ('erupcion', 'Erupción o urticaria'),
        ('angioedema', 'Hinchazón de cara, labios o lengua'),
        ('respiratoria', 'Dificultad para respirar'),
        ('anafilaxia', 'Anafilaxia'),
        ('gastrointestinal', 'Náuseas, vómito o diarrea'),
        ('otra', 'Otra'),
        ('desconocida', 'No se sabe'),
    ]

    LEVE = 'leve'
    MODERADA = 'moderada'
    GRAVE = 'grave'
    DESCONOCIDA = 'desconocida'
    SEVERIDADES = [
        (GRAVE, 'Grave'),
        (MODERADA, 'Moderada'),
        (LEVE, 'Leve'),
        (DESCONOCIDA, 'No se sabe'),
    ]

    FUENTES = [
        ('familia', 'Lo informó la familia o el acudiente'),
        ('historia', 'Historia clínica o epicrisis previa'),
        ('residente', 'Lo informó el residente'),
        ('observada', 'Reacción observada en el hogar'),
    ]

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='alergias')
    tipo = models.CharField(max_length=20, choices=TIPOS, default=MEDICAMENTO)
    medicamento = models.ForeignKey(
        'medicamentos.Medicamento', on_delete=models.PROTECT, null=True, blank=True, related_name='alergias',
        help_text='Si es alérgico a un medicamento del catálogo, elíjalo: el sistema avisará al formularlo.',
    )
    sustancia = models.CharField(
        max_length=150,
        help_text='A qué es alérgico, como lo diría el personal: "Penicilina", "Mariscos", "Látex".',
    )
    reaccion = models.CharField(max_length=20, choices=REACCIONES, default='desconocida', verbose_name='Reacción')
    descripcion_reaccion = models.TextField(blank=True, verbose_name='Detalle de la reacción')
    severidad = models.CharField(max_length=20, choices=SEVERIDADES, default=DESCONOCIDA)
    fuente = models.CharField(max_length=20, choices=FUENTES, default='familia', verbose_name='¿Quién lo informó?')

    class Meta:
        db_table = 'antecedentes_alergias'
        verbose_name = 'Alergia'
        verbose_name_plural = 'Alergias'
        ordering = ['-activo', 'tipo', 'sustancia']

    def __str__(self):
        return self.sustancia

    def coincide_con(self, medicamento):
        """True si este medicamento podría ser al que el residente es alérgico."""
        if not self.activo or medicamento is None:
            return False
        if self.medicamento_id and self.medicamento_id == medicamento.pk:
            return True
        if self.tipo not in (self.MEDICAMENTO, self.OTRA):
            return False
        sustancia = normalizar(self.sustancia)
        if len(sustancia) < 4:
            return False
        nombres = [normalizar(medicamento.nombre_generico), normalizar(medicamento.nombre_comercial)]
        return any(n and (sustancia in n or n in sustancia) for n in nombres)


class EstadoAlergias(models.Model):
    """Declaración explícita de que el residente no tiene alergias conocidas."""
    residente = models.OneToOneField(Residente, on_delete=models.PROTECT, related_name='estado_alergias')
    sin_alergias_conocidas = models.BooleanField(default=False)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_actualizacion = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'antecedentes_estado_alergias'
        verbose_name = 'Estado de alergias'
        verbose_name_plural = 'Estados de alergias'


class Antecedente(RegistroInactivable):
    PATOLOGICO = 'patologico'
    QUIRURGICO = 'quirurgico'
    TRAUMATICO = 'traumatico'
    TOXICO = 'toxico'
    FAMILIAR = 'familiar'
    OTRO = 'otro'
    TIPOS = [
        (PATOLOGICO, 'Enfermedad (patológico)'),
        (QUIRURGICO, 'Cirugía (quirúrgico)'),
        (TRAUMATICO, 'Fractura o trauma'),
        (TOXICO, 'Tabaco, alcohol u otras sustancias'),
        (FAMILIAR, 'Enfermedad en la familia'),
        (OTRO, 'Otro'),
    ]

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='antecedentes')
    tipo = models.CharField(max_length=20, choices=TIPOS, default=PATOLOGICO)
    descripcion = models.CharField(max_length=255, verbose_name='Descripción')
    codigo_cie10 = models.ForeignKey(
        'catalogos.CodigoCIE10', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Código CIE-10 (opcional)',
    )
    cuando = models.CharField(
        max_length=60, blank=True, verbose_name='¿Cuándo?',
        help_text='Como se sepa: "2015", "hace 10 años", "en la infancia".',
    )
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = 'antecedentes_antecedentes'
        verbose_name = 'Antecedente'
        verbose_name_plural = 'Antecedentes'
        ordering = ['-activo', 'tipo', '-fecha_registro']

    def __str__(self):
        return self.descripcion
