"""Signos vitales, peso y balance de líquidos.

Reglas comunes con el resto de la historia clínica:
- Los registros no se editan ni se borran. Un registro equivocado se anula
  con motivo (queda visible, tachado) y se registra de nuevo.
- Cada registro guarda quién lo hizo, cuándo se tomó y cuándo se digitó.
- Huella SHA-256 del contenido para verificar integridad.

La diuresis y la deposición NO se registran aquí: siguen en la nota de
enfermería (casillas sí/no), por decisión de Juan Carlos. Este módulo solo
las lee para graficarlas y para la alerta de días sin deposición.
"""
import hashlib
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from hogares.models import Hogar
from residentes.models import Residente

from . import parametros as P


def _canon(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, Decimal):
        return str(v.quantize(Decimal('0.001')))
    if hasattr(v, 'utcoffset') and hasattr(v, 'timestamp'):
        return str(int(v.timestamp()))  # independiente de la zona horaria
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    return str(v)


class RegistroAnulable(models.Model):
    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='+')
    fecha_hora = models.DateTimeField('Fecha y hora de la toma', default=timezone.now)
    observaciones = models.TextField('Observaciones', blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)
    hash_integridad = models.CharField(max_length=64, editable=False, blank=True)

    anulado = models.BooleanField(default=False)
    motivo_anulacion = models.TextField(blank=True)
    anulado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+')
    fecha_anulacion = models.DateTimeField(null=True, blank=True)

    CAMPOS_HASH = []
    CAMPOS_ANULACION = {'anulado', 'motivo_anulacion', 'anulado_por', 'fecha_anulacion'}

    class Meta:
        abstract = True

    def calcular_hash(self):
        partes = [str(self.residente_id), _canon(self.fecha_hora), str(self.registrado_por_id), self.observaciones]
        partes += [_canon(getattr(self, c)) for c in self.CAMPOS_HASH]
        return hashlib.sha256('|'.join(partes).encode('utf-8')).hexdigest()

    def verificar_integridad(self):
        return self.hash_integridad == self.calcular_hash()

    def save(self, *args, **kwargs):
        if not self.pk:
            self.hash_integridad = self.calcular_hash()
        else:
            campos = kwargs.get('update_fields')
            if not campos or not set(campos) <= self.CAMPOS_ANULACION:
                raise ValueError('Los registros de signos y líquidos no se modifican: se anulan con motivo.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Los registros de signos y líquidos no se eliminan: se anulan con motivo.')

    def anular(self, usuario, motivo):
        self.anulado = True
        self.motivo_anulacion = motivo
        self.anulado_por = usuario
        self.fecha_anulacion = timezone.now()
        self.save(update_fields=list(self.CAMPOS_ANULACION))


class ControlSignos(RegistroAnulable):
    AYUNAS = 'ayunas'
    PREPRANDIAL = 'preprandial'
    POSTPRANDIAL = 'postprandial'
    ALEATORIA = 'aleatoria'
    MOMENTOS_GLUCOMETRIA = [
        (AYUNAS, 'En ayunas'),
        (PREPRANDIAL, 'Antes de comer'),
        (POSTPRANDIAL, 'Dos horas después de comer'),
        (ALEATORIA, 'En otro momento'),
    ]

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='controles_signos')
    pas = models.PositiveSmallIntegerField('Presión sistólica (mmHg)', null=True, blank=True)
    pad = models.PositiveSmallIntegerField('Presión diastólica (mmHg)', null=True, blank=True)
    fc = models.PositiveSmallIntegerField('Frecuencia cardiaca (lpm)', null=True, blank=True)
    fr = models.PositiveSmallIntegerField('Frecuencia respiratoria (rpm)', null=True, blank=True)
    temperatura = models.DecimalField('Temperatura (°C)', max_digits=4, decimal_places=1, null=True, blank=True)
    spo2 = models.PositiveSmallIntegerField('Saturación de oxígeno (%)', null=True, blank=True)
    oxigeno_suplementario = models.BooleanField('Con oxígeno suplementario', default=False)
    litros_oxigeno = models.DecimalField('Litros por minuto', max_digits=4, decimal_places=1, null=True, blank=True)
    glucometria = models.PositiveSmallIntegerField('Glucometría (mg/dL)', null=True, blank=True)
    momento_glucometria = models.CharField('Momento de la glucometría', max_length=15,
                                           choices=MOMENTOS_GLUCOMETRIA, blank=True)
    dolor = models.PositiveSmallIntegerField('Dolor (0 a 10)', null=True, blank=True)
    peso = models.DecimalField('Peso (kg)', max_digits=5, decimal_places=1, null=True, blank=True)

    CAMPOS_HASH = ['pas', 'pad', 'fc', 'fr', 'temperatura', 'spo2', 'oxigeno_suplementario', 'litros_oxigeno',
                   'glucometria', 'momento_glucometria', 'dolor', 'peso']

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = 'Control de signos vitales'
        verbose_name_plural = 'Controles de signos vitales'
        indexes = [models.Index(fields=['residente', 'fecha_hora'])]

    def __str__(self):
        return f'Signos de {self.residente_id} — {timezone.localtime(self.fecha_hora):%d/%m/%Y %H:%M}'

    def valores(self):
        return {c: getattr(self, c) for c in P.CODIGOS if getattr(self, c) is not None}

    @property
    def presion(self):
        if self.pas is None and self.pad is None:
            return ''
        return f'{self.pas or "—"}/{self.pad or "—"}'


class RegistroLiquidos(RegistroAnulable):
    INGRESO = 'ingreso'
    EGRESO = 'egreso'
    TIPOS = [(INGRESO, 'Ingreso (lo que recibió)'), (EGRESO, 'Egreso (lo que eliminó)')]
    VIAS = [
        ('oral', 'Ingreso — vía oral'),
        ('sonda', 'Ingreso — sonda o gastrostomía'),
        ('intravenosa', 'Ingreso — líquidos intravenosos'),
        ('subcutanea', 'Ingreso — hipodermoclisis'),
        ('otro_ingreso', 'Ingreso — otro'),
        ('orina', 'Egreso — orina'),
        ('vomito', 'Egreso — vómito'),
        ('deposicion_liquida', 'Egreso — deposición líquida'),
        ('drenaje', 'Egreso — drenaje o sonda'),
        ('otro_egreso', 'Egreso — otro'),
    ]
    VIAS_INGRESO = {'oral', 'sonda', 'intravenosa', 'subcutanea', 'otro_ingreso'}

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='registros_liquidos')
    tipo = models.CharField(max_length=10, choices=TIPOS)
    via = models.CharField('Vía o tipo', max_length=20, choices=VIAS)
    cantidad_ml = models.PositiveIntegerField('Cantidad (mL)')

    CAMPOS_HASH = ['tipo', 'via', 'cantidad_ml']

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = 'Registro de líquidos'
        verbose_name_plural = 'Registros de líquidos'
        indexes = [models.Index(fields=['residente', 'fecha_hora'])]

    def __str__(self):
        return f'{self.get_tipo_display()} {self.cantidad_ml} mL'


class RangosHogar(models.Model):
    """Rangos generales del hogar. `rangos` = {codigo: {normal_min, ...}} con
    solo lo que el hogar cambió; lo demás sale de los valores por defecto."""
    hogar = models.OneToOneField(Hogar, on_delete=models.CASCADE, related_name='rangos_signos')
    rangos = models.JSONField(default=dict, blank=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='+')
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Rangos de signos vitales del hogar'
        verbose_name_plural = 'Rangos de signos vitales de los hogares'

    @classmethod
    def para_hogar(cls, hogar):
        obj, _ = cls.objects.get_or_create(hogar=hogar)
        return obj

    def rango(self, codigo):
        base = P.rango_por_defecto(codigo)
        propio = (self.rangos or {}).get(codigo)
        if propio:
            base = {k: (None if propio.get(k) in (None, '') else Decimal(str(propio[k]))) for k in base}
        return base


class RangoResidente(models.Model):
    """Rango que el médico fija para un residente en un parámetro. Nunca se
    borra: al cambiarlo, el anterior queda inactivo con fecha y autor."""
    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='rangos_signos')
    parametro = models.CharField(max_length=15, choices=[(p.codigo, p.nombre) for p in P.PARAMETROS])
    critico_min = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    normal_min = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    normal_max = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    critico_max = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    motivo = models.TextField()
    definido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha = models.DateTimeField(default=timezone.now)
    activo = models.BooleanField(default=True)
    inactivado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name='+')
    fecha_inactivacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['parametro', '-fecha']
        verbose_name = 'Rango de signos vitales del residente'
        verbose_name_plural = 'Rangos de signos vitales de residentes'
        constraints = [
            models.UniqueConstraint(fields=['residente', 'parametro'], condition=Q(activo=True),
                                    name='rango_residente_activo_unico'),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('Los rangos no se eliminan: se reemplazan y el anterior queda en el historial.')

    def como_dict(self):
        return {'critico_min': self.critico_min, 'normal_min': self.normal_min,
                'normal_max': self.normal_max, 'critico_max': self.critico_max}

    @property
    def parametro_obj(self):
        return P.POR_CODIGO[self.parametro]
