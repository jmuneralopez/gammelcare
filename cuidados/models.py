"""Cuidados diarios (baño, pañal, cambios de posición, higiene oral,
movilización) y heridas, incluidas las lesiones por presión.

Reglas comunes con el resto de la historia clínica:
- Los registros de cuidados y los seguimientos de heridas no se editan ni se
  borran: un registro equivocado se anula con motivo y se registra de nuevo.
- Cada registro guarda quién lo hizo, cuándo se hizo y cuándo se digitó, con
  una huella SHA-256 para verificar que no cambió.
- Las fotos de las heridas son historia clínica: se guardan en el
  almacenamiento privado y solo se ven a través de una vista que verifica
  permisos y deja registro en la auditoría.

La diuresis y la deposición siguen registrándose en la nota de enfermería
(decisión de Juan Carlos); lo que se anota al cambiar el pañal es solo el
hallazgo de ese cambio.
"""
import hashlib
import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from gammelcare.archivos_privados import almacenamiento_privado
from residentes.models import Residente


def _canon(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, Decimal):
        return str(v.quantize(Decimal('0.001')))
    if hasattr(v, 'utcoffset') and hasattr(v, 'timestamp'):
        return str(int(v.timestamp()))
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    return str(v)


class Inmutable(models.Model):
    """Base de los registros que no se modifican: se anulan con motivo."""
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
        partes = [str(self.registrado_por_id), self.observaciones]
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
                raise ValueError('Este registro no se modifica: se anula con motivo y se registra de nuevo.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Este registro no se elimina: se anula con motivo.')

    def anular(self, usuario, motivo):
        self.anulado = True
        self.motivo_anulacion = motivo
        self.anulado_por = usuario
        self.fecha_anulacion = timezone.now()
        self.save(update_fields=list(self.CAMPOS_ANULACION))


# ── Cuidados diarios ────────────────────────────────────────────────

BANIO, PANAL, POSICION, HIGIENE_ORAL, MOVILIZACION = 'banio', 'panal', 'posicion', 'higiene_oral', 'movilizacion'

TIPOS_CUIDADO = [
    (BANIO, 'Baño'),
    (PANAL, 'Cambio de pañal'),
    (POSICION, 'Cambio de posición'),
    (HIGIENE_ORAL, 'Higiene oral'),
    (MOVILIZACION, 'Movilización'),
]

# Opciones de cada cuidado. La primera es la que se ofrece por defecto.
DETALLES = {
    BANIO: [('ducha', 'En ducha'), ('cama', 'En cama'), ('parcial', 'Parcial (por partes)')],
    PANAL: [('orina', 'Con orina'), ('deposicion', 'Con deposición'), ('ambos', 'Orina y deposición'),
            ('seco', 'Seco')],
    POSICION: [('supino', 'Boca arriba'), ('lateral_der', 'De lado derecho'), ('lateral_izq', 'De lado izquierdo'),
               ('semisentado', 'Semisentado'), ('sentado', 'Sentado en la silla')],
    HIGIENE_ORAL: [('dientes', 'Cepillado'), ('protesis', 'Limpieza de la prótesis'),
                   ('boca', 'Limpieza de boca y encías')],
    MOVILIZACION: [('silla', 'Levantado a la silla'), ('camino', 'Caminó acompañado'),
                   ('ejercicios', 'Ejercicios en cama')],
}

# Rotación sugerida para el siguiente cambio de posición.
ROTACION_POSICION = ['lateral_der', 'supino', 'lateral_izq', 'semisentado']

ICONOS = {
    BANIO: 'bi-droplet', PANAL: 'bi-arrow-repeat', POSICION: 'bi-arrow-left-right',
    HIGIENE_ORAL: 'bi-emoji-smile', MOVILIZACION: 'bi-person-walking',
}


class PlanCuidados(models.Model):
    """Qué cuidados necesita cada residente y cada cuánto. Define las
    columnas que ve la auxiliar en la planilla del turno."""
    DIARIO, INTERDIARIO, NO_APLICA = 'diario', 'interdiario', 'no_aplica'
    FRECUENCIAS_BANIO = [(DIARIO, 'Todos los días'), (INTERDIARIO, 'Día de por medio'),
                         (NO_APLICA, 'No se registra')]
    INTERVALOS = [(2, 'Cada 2 horas'), (3, 'Cada 3 horas'), (4, 'Cada 4 horas')]

    residente = models.OneToOneField(Residente, on_delete=models.PROTECT, related_name='plan_cuidados')
    banio = models.CharField('Baño', max_length=12, choices=FRECUENCIAS_BANIO, default=DIARIO)
    usa_panal = models.BooleanField('Usa pañal', default=False)
    cambios_posicion = models.BooleanField('Necesita cambios de posición', default=False,
                                           help_text='Para residentes en cama o con riesgo de lesiones por presión.')
    intervalo_posicion_horas = models.PositiveSmallIntegerField('Cada cuánto', choices=INTERVALOS, default=2)
    higiene_oral = models.BooleanField('Higiene oral', default=True)
    movilizacion = models.BooleanField('Movilización (levantar, caminar o ejercicios)', default=False)
    indicaciones = models.TextField('Indicaciones especiales', blank=True,
                                    help_text='Ej.: colchón antiescaras, protección de talones, baño con ayuda de dos personas.')
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='+')
    fecha_actualizacion = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Plan de cuidados'
        verbose_name_plural = 'Planes de cuidados'

    def __str__(self):
        return f'Plan de cuidados del residente #{self.residente_id}'

    def tipos(self):
        """Los cuidados que aplican, en el orden de la planilla."""
        salida = []
        if self.cambios_posicion:
            salida.append(POSICION)
        if self.usa_panal:
            salida.append(PANAL)
        if self.banio != self.NO_APLICA:
            salida.append(BANIO)
        if self.higiene_oral:
            salida.append(HIGIENE_ORAL)
        if self.movilizacion:
            salida.append(MOVILIZACION)
        return salida


class RegistroCuidado(Inmutable):
    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='cuidados')
    tipo = models.CharField(max_length=15, choices=TIPOS_CUIDADO)
    detalle = models.CharField(max_length=20)
    fecha_hora = models.DateTimeField('Hora en que se hizo', default=timezone.now)

    CAMPOS_HASH = ['residente_id', 'tipo', 'detalle', 'fecha_hora']

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = 'Registro de cuidado'
        verbose_name_plural = 'Registros de cuidados'
        indexes = [models.Index(fields=['residente', 'tipo', 'fecha_hora'])]

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.detalle_texto} ({timezone.localtime(self.fecha_hora):%d/%m %H:%M})'

    @property
    def detalle_texto(self):
        return dict(DETALLES.get(self.tipo, [])).get(self.detalle, self.detalle)


# ── Heridas ─────────────────────────────────────────────────────────

class Herida(models.Model):
    LPP = 'lpp'
    TIPOS = [
        (LPP, 'Lesión por presión'),
        ('humedad', 'Lesión por humedad (dermatitis del pañal)'),
        ('desgarro', 'Desgarro cutáneo'),
        ('traumatica', 'Herida por caída o golpe'),
        ('quirurgica', 'Herida quirúrgica'),
        ('venosa', 'Úlcera venosa'),
        ('arterial', 'Úlcera arterial'),
        ('pie_diabetico', 'Pie diabético'),
        ('quemadura', 'Quemadura'),
        ('otra', 'Otra'),
    ]
    UBICACIONES = [
        ('sacro', 'Sacro'), ('coxis', 'Coxis'), ('gluteo_der', 'Glúteo derecho'), ('gluteo_izq', 'Glúteo izquierdo'),
        ('isquion_der', 'Isquion derecho'), ('isquion_izq', 'Isquion izquierdo'),
        ('trocanter_der', 'Cadera derecha (trocánter)'), ('trocanter_izq', 'Cadera izquierda (trocánter)'),
        ('talon_der', 'Talón derecho'), ('talon_izq', 'Talón izquierdo'),
        ('maleolo_der', 'Tobillo derecho (maléolo)'), ('maleolo_izq', 'Tobillo izquierdo (maléolo)'),
        ('pie_der', 'Pie derecho'), ('pie_izq', 'Pie izquierdo'),
        ('pierna_der', 'Pierna derecha'), ('pierna_izq', 'Pierna izquierda'),
        ('rodilla_der', 'Rodilla derecha'), ('rodilla_izq', 'Rodilla izquierda'),
        ('codo_der', 'Codo derecho'), ('codo_izq', 'Codo izquierdo'),
        ('brazo_der', 'Brazo o antebrazo derecho'), ('brazo_izq', 'Brazo o antebrazo izquierdo'),
        ('mano_der', 'Mano derecha'), ('mano_izq', 'Mano izquierda'),
        ('escapula', 'Espalda (omóplatos)'), ('columna', 'Columna'),
        ('occipital', 'Nuca (occipital)'), ('oreja_der', 'Oreja derecha'), ('oreja_izq', 'Oreja izquierda'),
        ('cara', 'Cara'), ('abdomen', 'Abdomen'), ('otra', 'Otra'),
    ]
    ESTADIOS = [
        ('1', 'Estadio 1 — piel intacta, enrojecimiento que no blanquea'),
        ('2', 'Estadio 2 — pérdida parcial de la piel (ampolla o erosión)'),
        ('3', 'Estadio 3 — pérdida total de la piel, se ve grasa'),
        ('4', 'Estadio 4 — se ve músculo, tendón o hueso'),
        ('no_estadificable', 'No estadificable — cubierta por esfacelo o escara'),
        ('tejido_profundo', 'Lesión de tejido profundo — piel morada o granate'),
    ]
    ORIGENES = [
        ('hogar', 'Apareció en el hogar'),
        ('ingreso', 'Ya la traía al ingresar al hogar'),
        ('hospital', 'Llegó así de una hospitalización o salida'),
    ]
    ACTIVA, CERRADA = 'activa', 'cerrada'
    ESTADOS = [(ACTIVA, 'Activa'), (CERRADA, 'Cerrada')]
    MOTIVOS_CIERRE = [
        ('cicatrizada', 'Cicatrizó'),
        ('egreso', 'El residente egresó o fue trasladado'),
        ('fallecimiento', 'Fallecimiento'),
        ('error', 'Se registró por error'),
    ]

    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, related_name='heridas')
    tipo = models.CharField('Tipo de herida', max_length=15, choices=TIPOS, default=LPP)
    ubicacion = models.CharField('Ubicación', max_length=20, choices=UBICACIONES)
    ubicacion_detalle = models.CharField('Detalle de la ubicación', max_length=120, blank=True)
    estadio_inicial = models.CharField('Estadio al detectarla', max_length=20, choices=ESTADIOS, blank=True)
    origen = models.CharField('¿Dónde apareció?', max_length=10, choices=ORIGENES, default='hogar')
    fecha_deteccion = models.DateField('Fecha en que se detectó', default=timezone.localdate)
    descripcion = models.TextField('Descripción inicial', blank=True)

    estado = models.CharField(max_length=10, choices=ESTADOS, default=ACTIVA)
    motivo_cierre = models.CharField(max_length=15, choices=MOTIVOS_CIERRE, blank=True)
    nota_cierre = models.TextField(blank=True)
    cerrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+')
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    fecha_registro = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['estado', '-fecha_deteccion']
        verbose_name = 'Herida'
        verbose_name_plural = 'Heridas'

    def __str__(self):
        return self.nombre

    def delete(self, *args, **kwargs):
        raise ValueError('Las heridas no se eliminan: se cierran con motivo.')

    @property
    def nombre(self):
        lugar = self.get_ubicacion_display() if self.ubicacion != 'otra' else (self.ubicacion_detalle or 'Otra ubicación')
        return f'{self.get_tipo_display()} — {lugar}'

    @property
    def es_lpp(self):
        return self.tipo == self.LPP

    @property
    def activa(self):
        return self.estado == self.ACTIVA

    def seguimientos_vigentes(self):
        return self.seguimientos.filter(anulado=False)

    def ultimo_seguimiento(self):
        return self.seguimientos_vigentes().order_by('-fecha_hora').first()

    @property
    def estadio_actual(self):
        s = self.seguimientos_vigentes().exclude(estadio='').order_by('-fecha_hora').first()
        codigo = s.estadio if s else self.estadio_inicial
        return dict(self.ESTADIOS).get(codigo, '').split(' — ')[0] if codigo else ''


def _ruta_foto(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    h = instance.herida
    return f'heridas/hogar_{h.residente.hogar_id}/residente_{h.residente_id}/{uuid.uuid4().hex}{extension}'


class SeguimientoHerida(Inmutable):
    """Valoración y curación de una herida: medidas, aspecto, curación hecha
    y foto. Comparar seguimientos muestra si la herida mejora."""
    LECHOS = [
        ('epitelizacion', 'Epitelización (piel nueva, rosada)'),
        ('granulacion', 'Granulación (rojo, húmedo, sano)'),
        ('esfacelo', 'Esfacelo (amarillo o blanco, adherido)'),
        ('necrosis', 'Necrosis o escara (negra o café, seca)'),
        ('mixto', 'Mixto'),
    ]
    EXUDADOS = [('ninguno', 'Ninguno'), ('escaso', 'Escaso'), ('moderado', 'Moderado'), ('abundante', 'Abundante')]
    PIELES = [('sana', 'Sana'), ('enrojecida', 'Enrojecida'), ('macerada', 'Macerada (blanca, húmeda)'),
              ('edema', 'Hinchada'), ('seca', 'Seca o descamada')]

    herida = models.ForeignKey(Herida, on_delete=models.PROTECT, related_name='seguimientos')
    fecha_hora = models.DateTimeField('Fecha y hora', default=timezone.now)
    largo_cm = models.DecimalField('Largo (cm)', max_digits=5, decimal_places=1, null=True, blank=True)
    ancho_cm = models.DecimalField('Ancho (cm)', max_digits=5, decimal_places=1, null=True, blank=True)
    profundidad_cm = models.DecimalField('Profundidad (cm)', max_digits=5, decimal_places=1, null=True, blank=True)
    estadio = models.CharField('Estadio actual', max_length=20, choices=Herida.ESTADIOS, blank=True)
    lecho = models.CharField('Aspecto del fondo de la herida', max_length=15, choices=LECHOS, blank=True)
    exudado = models.CharField('Secreción', max_length=10, choices=EXUDADOS, default='ninguno')
    piel_alrededor = models.CharField('Piel alrededor', max_length=12, choices=PIELES, default='sana')
    signos_infeccion = models.BooleanField('Signos de infección (calor, pus, mal olor, enrojecimiento que se extiende)',
                                           default=False)
    dolor = models.PositiveSmallIntegerField('Dolor (0 a 10)', null=True, blank=True)
    curacion = models.TextField('Curación realizada', blank=True,
                                help_text='Limpieza, producto y apósito usados.')
    proxima_curacion = models.DateField('Próxima curación', null=True, blank=True)
    foto = models.FileField(upload_to=_ruta_foto, storage=almacenamiento_privado, null=True, blank=True)
    foto_tipo = models.CharField(max_length=50, blank=True)

    CAMPOS_HASH = ['herida_id', 'fecha_hora', 'largo_cm', 'ancho_cm', 'profundidad_cm', 'estadio', 'lecho',
                   'exudado', 'piel_alrededor', 'signos_infeccion', 'dolor', 'curacion', 'proxima_curacion', 'foto']

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = 'Seguimiento de herida'
        verbose_name_plural = 'Seguimientos de heridas'

    def __str__(self):
        return f'Seguimiento de {self.herida} — {timezone.localtime(self.fecha_hora):%d/%m/%Y %H:%M}'

    def save(self, *args, **kwargs):
        # La foto se guarda antes de calcular la huella, para que la huella
        # incluya la ruta definitiva del archivo.
        if not self.pk and self.foto and not self.foto._committed:
            self.foto.save(os.path.basename(self.foto.name), self.foto.file, save=False)
        super().save(*args, **kwargs)

    @property
    def area_cm2(self):
        if self.largo_cm is None or self.ancho_cm is None:
            return None
        return (self.largo_cm * self.ancho_cm).quantize(Decimal('0.1'))
