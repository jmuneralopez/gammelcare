"""Exámenes médicos y paraclínicos del residente.

Ciclo de vida de un examen:

    PENDIENTE ──cargar resultado──▶ RESULTADO ──revisión médica──▶ REVISADO
        │                              ▲                              │
        └──cancelar (con motivo)       └──────adenda o corrección─────┘

Reglas de integridad (mismo espíritu que NotaClinica):
- Un archivo, un valor o una revisión ya guardados no se editan ni se borran.
- Una corrección de un valor es una fila nueva que apunta a la anterior
  (`reemplaza`) con su motivo; el historial completo queda visible.
- Agregar información a un resultado ya revisado (adenda o corrección)
  lo devuelve a RESULTADO: necesita una revisión médica nueva.
- Valores, archivos y revisiones llevan hash SHA-256 que liga quién, a qué
  examen, de qué residente y cuándo (base para la Fase 2 del plan).
"""
import hashlib
import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from residentes.models import Residente

from .storage import almacenamiento_privado


def _canon(valor):
    """Representación estable para el hash: los decimales se fijan a 3
    cifras para que el hash calculado al guardar coincida con el que se
    recalcula después de leer la fila de la base de datos."""
    if valor is None:
        return ''
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, (Decimal, float)):
        return format(Decimal(str(valor)).quantize(Decimal('0.001')), 'f')
    return str(valor)


def _sha256(*partes):
    texto = '|'.join(_canon(p) for p in partes)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


class RegistroInmutable(models.Model):
    """Base para filas que solo admiten INSERT."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError(f'{self._meta.verbose_name} es inmutable y no puede modificarse.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(f'{self._meta.verbose_name} es inmutable y no puede eliminarse.')


class AnalitoCatalogo(models.Model):
    """Parámetros de laboratorio frecuentes (en el código, "analitos") con
    unidad y rango de referencia POR DEFECTO.

    El rango real es el que reporta cada laboratorio: al registrar un valor
    el rango se copia al resultado y se puede ajustar ahí. Este catálogo
    solo evita digitar lo mismo cada vez.
    """
    codigo = models.SlugField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    unidad = models.CharField(max_length=30)
    ref_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    ref_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    critico_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    critico_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    nota = models.CharField(max_length=255, blank=True)
    orden = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    # Catálogo híbrido, igual que el de medicamentos: hogar=NULL es el
    # catálogo base compartido; hogar=X es un analito que agregó ese hogar
    # desde el formulario de resultados y que solo ese hogar ve.
    hogar = models.ForeignKey(
        'hogares.Hogar', on_delete=models.PROTECT, null=True, blank=True,
        related_name='analitos_propios',
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )

    class Meta:
        db_table = 'examenes_analitos'
        verbose_name = 'Parámetro de laboratorio'
        verbose_name_plural = 'Parámetros de laboratorio'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return f'{self.nombre} ({self.unidad})' if self.unidad else self.nombre

    @classmethod
    def disponibles_para(cls, hogar):
        """Catálogo base más los analitos propios del hogar."""
        return cls.objects.filter(activo=True).filter(
            models.Q(hogar__isnull=True) | models.Q(hogar=hogar)
        )


class Examen(models.Model):
    LABORATORIO = 'laboratorio'
    IMAGEN = 'imagen'
    ELECTROCARDIOGRAMA = 'electrocardiograma'
    OTRO = 'otro'
    TIPOS = [
        (LABORATORIO, 'Laboratorio clínico'),
        (IMAGEN, 'Imagen diagnóstica'),
        (ELECTROCARDIOGRAMA, 'Electrocardiograma'),
        (OTRO, 'Otro paraclínico'),
    ]

    PENDIENTE = 'pendiente'
    RESULTADO = 'resultado'
    REVISADO = 'revisado'
    CANCELADO = 'cancelado'
    ESTADOS = [
        (PENDIENTE, 'Pendiente de resultado'),
        (RESULTADO, 'Pendiente de revisión médica'),
        (REVISADO, 'Revisado'),
        (CANCELADO, 'Cancelado'),
    ]

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='examenes')
    tipo = models.CharField(max_length=30, choices=TIPOS, default=LABORATORIO)
    nombre = models.CharField(
        max_length=200,
        help_text='Qué se ordenó, p. ej. "Hemograma, glucosa y creatinina" o "Rx de tórax".',
    )
    ordenado_por = models.CharField(
        max_length=150, blank=True,
        help_text='Profesional que ordenó el examen (puede ser externo al hogar).',
    )
    entidad = models.CharField(
        max_length=150, blank=True, verbose_name='EPS, IPS o laboratorio',
    )
    fecha_orden = models.DateField(null=True, blank=True, verbose_name='Fecha de la orden')
    indicaciones = models.TextField(blank=True, help_text='Ayuno, preparación, motivo de la orden.')

    estado = models.CharField(max_length=20, choices=ESTADOS, default=PENDIENTE)
    fecha_toma = models.DateField(
        null=True, blank=True, verbose_name='Fecha de toma o realización',
    )
    conclusion = models.TextField(
        blank=True, verbose_name='Conclusión del informe',
        help_text='Para imágenes, electrocardiogramas y otros informes en texto.',
    )

    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='examenes_registrados',
    )
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)
    resultado_cargado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='resultados_cargados',
    )
    fecha_resultado = models.DateTimeField(null=True, blank=True)

    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='examenes_cancelados',
    )
    fecha_cancelacion = models.DateTimeField(null=True, blank=True)
    motivo_cancelacion = models.TextField(blank=True)

    class Meta:
        db_table = 'examenes'
        verbose_name = 'Examen'
        verbose_name_plural = 'Exámenes'
        ordering = ['-fecha_registro']
        indexes = [models.Index(fields=['estado', 'fecha_registro'])]

    def __str__(self):
        return f'{self.nombre} — residente #{self.residente_id}'

    # ── Consultas de apoyo ──────────────────────────────────────────

    def valores_vigentes(self):
        """Valores sin una corrección posterior."""
        return self.valores.filter(corregido_por__isnull=True).select_related('analito')

    def ultima_revision(self):
        return self.revisiones.order_by('-fecha').first()

    def tiene_criticos(self):
        return any(v.es_critico() for v in self.valores_vigentes())

    def tiene_fuera_de_rango(self):
        return any(v.fuera_de_rango() for v in self.valores_vigentes())

    def dias_pendiente(self):
        desde = self.fecha_orden or timezone.localdate(self.fecha_registro)
        return (timezone.localdate() - desde).days

    @property
    def editable(self):
        """Los datos de la orden solo se corrigen mientras no hay resultado."""
        return self.estado == self.PENDIENTE


def _ruta_archivo(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    examen = instance.examen
    return (
        f'examenes/hogar_{examen.residente.hogar_id}/residente_{examen.residente_id}/'
        f'{uuid.uuid4().hex}{extension}'
    )


class ArchivoResultado(RegistroInmutable):
    examen = models.ForeignKey(Examen, on_delete=models.PROTECT, related_name='archivos')
    archivo = models.FileField(upload_to=_ruta_archivo, storage=almacenamiento_privado, max_length=255)
    nombre_original = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    tamano_bytes = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64, editable=False)
    motivo = models.TextField(
        blank=True, help_text='Obligatorio si se agrega después del resultado inicial (información adicional).',
    )
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_subida = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = 'examenes_archivos'
        verbose_name = 'Archivo de resultado'
        verbose_name_plural = 'Archivos de resultado'
        ordering = ['fecha_subida']

    def __str__(self):
        return self.nombre_original

    @property
    def es_imagen(self):
        return self.content_type.startswith('image/')

    def verificar_integridad(self):
        """True si el archivo en disco sigue siendo el que se subió."""
        h = hashlib.sha256()
        with self.archivo.open('rb') as f:
            for bloque in iter(lambda: f.read(65536), b''):
                h.update(bloque)
        return h.hexdigest() == self.sha256


class ValorResultado(RegistroInmutable):
    CRITICO_BAJO = 'critico_bajo'
    BAJO = 'bajo'
    NORMAL = 'normal'
    ALTO = 'alto'
    CRITICO_ALTO = 'critico_alto'
    SIN_RANGO = 'sin_rango'

    examen = models.ForeignKey(Examen, on_delete=models.PROTECT, related_name='valores')
    analito = models.ForeignKey(
        AnalitoCatalogo, on_delete=models.PROTECT, null=True, blank=True, related_name='valores',
    )
    nombre = models.CharField(max_length=120)
    valor = models.DecimalField(max_digits=12, decimal_places=3)
    unidad = models.CharField(max_length=30, blank=True)
    ref_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    ref_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    critico_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    critico_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)

    reemplaza = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='corregido_por',
    )
    motivo_correccion = models.TextField(blank=True)

    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)
    hash_integridad = models.CharField(max_length=64, editable=False)

    class Meta:
        db_table = 'examenes_valores'
        verbose_name = 'Valor de resultado'
        verbose_name_plural = 'Valores de resultado'
        ordering = ['analito__orden', 'nombre', 'fecha_registro']

    def __str__(self):
        return f'{self.nombre}: {self.valor_formateado} {self.unidad}'

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.analito_id and self.critico_min is None and self.critico_max is None:
                self.critico_min = self.analito.critico_min
                self.critico_max = self.analito.critico_max
            self.hash_integridad = self.calcular_hash()
        super().save(*args, **kwargs)

    def calcular_hash(self):
        return _sha256(
            'valor', self.examen_id, self.examen.residente_id, self.registrado_por_id,
            self.fecha_registro.isoformat(), self.nombre, self.valor, self.unidad,
            self.ref_min, self.ref_max, str(self.reemplaza_id or ''), self.motivo_correccion,
        )

    def verificar_integridad(self):
        return self.hash_integridad == self.calcular_hash()

    @property
    def valor_formateado(self):
        v = self.valor.normalize() if isinstance(self.valor, Decimal) else self.valor
        texto = format(v, 'f')
        return texto

    def interpretacion(self):
        v = self.valor
        if self.critico_min is not None and v < self.critico_min:
            return self.CRITICO_BAJO
        if self.critico_max is not None and v > self.critico_max:
            return self.CRITICO_ALTO
        if self.ref_min is None and self.ref_max is None:
            return self.SIN_RANGO
        if self.ref_min is not None and v < self.ref_min:
            return self.BAJO
        if self.ref_max is not None and v > self.ref_max:
            return self.ALTO
        return self.NORMAL

    def es_critico(self):
        return self.interpretacion() in (self.CRITICO_BAJO, self.CRITICO_ALTO)

    def fuera_de_rango(self):
        return self.interpretacion() not in (self.NORMAL, self.SIN_RANGO)

    def rango_texto(self):
        if self.ref_min is not None and self.ref_max is not None:
            return f'{self.ref_min.normalize():f} – {self.ref_max.normalize():f}'
        if self.ref_min is not None:
            return f'≥ {self.ref_min.normalize():f}'
        if self.ref_max is not None:
            return f'≤ {self.ref_max.normalize():f}'
        return '—'


class RevisionMedica(RegistroInmutable):
    examen = models.ForeignKey(Examen, on_delete=models.PROTECT, related_name='revisiones')
    medico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    interpretacion = models.TextField(blank=True, verbose_name='Hallazgos e interpretación')
    conducta = models.TextField(verbose_name='Conducta')
    fecha = models.DateTimeField(default=timezone.now, editable=False)
    hash_integridad = models.CharField(max_length=64, editable=False)

    class Meta:
        db_table = 'examenes_revisiones'
        verbose_name = 'Revisión médica'
        verbose_name_plural = 'Revisiones médicas'
        ordering = ['-fecha']

    def __str__(self):
        return f'Revisión de {self.examen} ({self.fecha:%Y-%m-%d})'

    def save(self, *args, **kwargs):
        if not self.pk:
            self.hash_integridad = self.calcular_hash()
        super().save(*args, **kwargs)

    def calcular_hash(self):
        return _sha256(
            'revision', self.examen_id, self.examen.residente_id, self.medico_id,
            self.fecha.isoformat(), self.interpretacion, self.conducta,
        )

    def verificar_integridad(self):
        return self.hash_integridad == self.calcular_hash()
