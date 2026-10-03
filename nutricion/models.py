"""Nutrición e hidratación: dieta de cada residente, ingesta por comida y
lista de dietas para la cocina.

- La dieta no se edita: cada cambio crea una dieta nueva y la anterior queda
  en el historial con su fecha de fin.
- La ingesta de cada comida es un registro inmutable con huella SHA-256; si
  se corrige, el registro anterior queda anulado con el motivo.
- Los líquidos se registran en el balance de líquidos de signos vitales
  (`signos.RegistroLiquidos`, vía oral); aquí solo se ofrece el botón rápido
  "+1 vaso" y se comparan con la meta del residente.
"""
import hashlib

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from hogares.models import Hogar
from residentes.models import Residente

COMIDAS = [
    ('desayuno', 'Desayuno', '07:00'),
    ('media_manana', 'Media mañana', '10:00'),
    ('almuerzo', 'Almuerzo', '12:30'),
    ('onces', 'Onces', '15:30'),
    ('cena', 'Cena', '18:00'),
    ('nocturno', 'Refrigerio nocturno', '20:30'),
]
NOMBRE_COMIDA = {c: n for c, n, _ in COMIDAS}


class TipoDieta(models.Model):
    """Catálogo de dietas: las básicas (sin hogar) y las que crea cada hogar."""
    nombre = models.CharField(max_length=80)
    descripcion = models.CharField('Descripción', max_length=255, blank=True)
    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, null=True, blank=True, related_name='tipos_dieta')
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=100)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='+')

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Tipo de dieta'
        verbose_name_plural = 'Tipos de dieta'

    def __str__(self):
        return self.nombre

    @classmethod
    def disponibles(cls, hogar):
        return cls.objects.filter(Q(hogar__isnull=True) | Q(hogar=hogar), activo=True)


class ConfiguracionNutricion(models.Model):
    hogar = models.OneToOneField(Hogar, on_delete=models.CASCADE, related_name='configuracion_nutricion')
    comidas_activas = models.JSONField(default=list, blank=True,
                                       help_text='Códigos de las comidas que sirve el hogar. Vacío = todas.')
    horas = models.JSONField(default=dict, blank=True)
    vaso_ml = models.PositiveSmallIntegerField('Tamaño del vaso (mL)', default=200)
    meta_liquidos_ml = models.PositiveIntegerField('Meta diaria de líquidos por defecto (mL)', default=1500)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='+')
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración de nutrición'
        verbose_name_plural = 'Configuraciones de nutrición'

    @classmethod
    def para_hogar(cls, hogar):
        config, _ = cls.objects.get_or_create(hogar=hogar)
        return config

    def comidas(self):
        """[(codigo, nombre, hora)] de las comidas que sirve el hogar, en orden."""
        activas = set(self.comidas_activas or [c for c, _, _ in COMIDAS])
        return [(c, n, (self.horas or {}).get(c, h)) for c, n, h in COMIDAS if c in activas]


class DietaResidente(models.Model):
    TEXTURAS = [
        ('normal', 'Normal'),
        ('blanda', 'Blanda o picada fina'),
        ('molida', 'Molida o en puré'),
        ('licuada', 'Licuada o líquida'),
    ]
    LIQUIDOS = [
        ('normal', 'Líquidos normales'),
        ('nectar', 'Espesados — néctar'),
        ('miel', 'Espesados — miel'),
        ('pudin', 'Espesados — pudín'),
    ]
    AYUDAS = [
        ('independiente', 'Come solo'),
        ('supervision', 'Come solo con supervisión'),
        ('parcial', 'Necesita ayuda parcial'),
        ('total', 'Hay que darle de comer'),
        ('sonda', 'Alimentación por sonda'),
    ]

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='dietas')
    tipo = models.ForeignKey(TipoDieta, on_delete=models.PROTECT, related_name='+', verbose_name='Tipo de dieta')
    textura = models.CharField(max_length=10, choices=TEXTURAS, default='normal')
    liquidos = models.CharField('Consistencia de los líquidos', max_length=10, choices=LIQUIDOS, default='normal')
    ayuda = models.CharField('Ayuda para comer', max_length=15, choices=AYUDAS, default='independiente')
    meta_liquidos_ml = models.PositiveIntegerField('Meta de líquidos al día (mL)', null=True, blank=True,
                                                   help_text='Vacío = la meta general del hogar.')
    restriccion_liquidos_ml = models.PositiveIntegerField('Máximo de líquidos al día (mL)', null=True, blank=True,
                                                          help_text='Solo si el médico restringió los líquidos.')
    alimentos_evitar = models.TextField('Alimentos que debe evitar', blank=True)
    preferencias = models.TextField('Gustos y preferencias', blank=True)
    indicaciones = models.TextField('Otras indicaciones', blank=True,
                                    help_text='Ej.: fraccionar en 6 comidas, sentarlo a 90°, suplemento en las onces.')
    indicada_por = models.CharField('Quién la indicó', max_length=120, blank=True)

    vigente = models.BooleanField(default=True)
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    class Meta:
        ordering = ['-fecha_inicio']
        verbose_name = 'Dieta del residente'
        verbose_name_plural = 'Dietas de los residentes'
        constraints = [
            models.UniqueConstraint(fields=['residente'], condition=Q(vigente=True), name='dieta_vigente_unica'),
        ]

    def __str__(self):
        return f'{self.tipo} — {self.get_textura_display()}'

    def delete(self, *args, **kwargs):
        raise ValueError('Las dietas no se eliminan: se reemplazan por una nueva.')

    @property
    def resumen(self):
        partes = [self.tipo.nombre]
        if self.textura != 'normal':
            partes.append(self.get_textura_display().lower())
        if self.liquidos != 'normal':
            partes.append(self.get_liquidos_display().lower())
        return ' · '.join(partes)


class RegistroIngesta(models.Model):
    TODO, TRES_CUARTOS, MITAD, CUARTO, NADA, RECHAZO, AUSENTE = 'todo', 'tres_cuartos', 'mitad', 'cuarto', 'nada', 'rechazo', 'ausente'
    CONSUMOS = [
        (TODO, 'Todo'),
        (TRES_CUARTOS, '¾'),
        (MITAD, 'La mitad'),
        (CUARTO, '¼'),
        (NADA, 'Nada'),
        (RECHAZO, 'Lo rechazó'),
        (AUSENTE, 'No estaba (cita, salida, hospital o ayuno)'),
    ]
    PORCENTAJE = {TODO: 100, TRES_CUARTOS: 75, MITAD: 50, CUARTO: 25, NADA: 0, RECHAZO: 0, AUSENTE: None}

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='ingestas')
    fecha = models.DateField(default=timezone.localdate)
    comida = models.CharField(max_length=15, choices=[(c, n) for c, n, _ in COMIDAS])
    consumo = models.CharField(max_length=15, choices=CONSUMOS)
    observaciones = models.TextField(blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)
    hash_integridad = models.CharField(max_length=64, editable=False, blank=True)

    anulado = models.BooleanField(default=False)
    motivo_anulacion = models.TextField(blank=True)
    anulado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+')
    fecha_anulacion = models.DateTimeField(null=True, blank=True)

    CAMPOS_ANULACION = {'anulado', 'motivo_anulacion', 'anulado_por', 'fecha_anulacion'}

    class Meta:
        ordering = ['-fecha', '-fecha_registro']
        verbose_name = 'Registro de ingesta'
        verbose_name_plural = 'Registros de ingesta'
        indexes = [models.Index(fields=['residente', 'fecha'])]
        constraints = [
            models.UniqueConstraint(fields=['residente', 'fecha', 'comida'], condition=Q(anulado=False),
                                    name='ingesta_vigente_unica'),
        ]

    def __str__(self):
        return f'{NOMBRE_COMIDA.get(self.comida, self.comida)} {self.fecha:%d/%m}: {self.get_consumo_display()}'

    @property
    def porcentaje(self):
        return self.PORCENTAJE.get(self.consumo)

    def calcular_hash(self):
        partes = [str(self.residente_id), self.fecha.isoformat(), self.comida, self.consumo, self.observaciones,
                  str(self.registrado_por_id), str(int(self.fecha_registro.timestamp()))]
        return hashlib.sha256('|'.join(partes).encode('utf-8')).hexdigest()

    def verificar_integridad(self):
        return self.hash_integridad == self.calcular_hash()

    def save(self, *args, **kwargs):
        if not self.pk:
            self.hash_integridad = self.calcular_hash()
        else:
            campos = kwargs.get('update_fields')
            if not campos or not set(campos) <= self.CAMPOS_ANULACION:
                raise ValueError('La ingesta no se modifica: se corrige con un registro nuevo.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('La ingesta no se elimina: se anula con motivo.')

    def anular(self, usuario, motivo):
        self.anulado = True
        self.motivo_anulacion = motivo
        self.anulado_por = usuario
        self.fecha_anulacion = timezone.now()
        self.save(update_fields=list(self.CAMPOS_ANULACION))
