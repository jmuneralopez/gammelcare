import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import models

from gammelcare.archivos_privados import almacenamiento_privado
from django.db.models import Q
from django.utils import timezone

from hogares.models import Hogar
from residentes.models import Residente, DiagnosticoResidente
from notas_clinicas.models import NotaClinica


# ── Choices compartidas ─────────────────────────────────────────

UNIDADES_DOSIS = [
    ('tableta', 'Tableta'),
    ('capsula', 'Cápsula'),
    ('ml', 'mL'),
    ('gota', 'Gota'),
    ('mg', 'mg'),
    ('aplicacion', 'Aplicación'),
    ('puff', 'Puff'),
    ('ui', 'UI'),
    ('sobre', 'Sobre'),
    ('otro', 'Otro'),
]

VIA_ADMINISTRACION = [
    ('oral', 'Oral'),
    ('sublingual', 'Sublingual'),
    ('topica', 'Tópica'),
    ('oftalmica', 'Oftálmica'),
    ('otica', 'Ótica'),
    ('nasal', 'Nasal'),
    ('inhalada', 'Inhalada'),
    ('subcutanea', 'Subcutánea'),
    ('intramuscular', 'Intramuscular'),
    ('intravenosa', 'Intravenosa'),
    ('rectal', 'Rectal'),
    ('vaginal', 'Vaginal'),
    ('transdermica', 'Transdérmica'),
]


class Medicamento(models.Model):

    FORMAS_FARMACEUTICAS = [
        ('tableta', 'Tableta'),
        ('capsula', 'Cápsula'),
        ('jarabe', 'Jarabe'),
        ('suspension', 'Suspensión'),
        ('gotas', 'Gotas'),
        ('ampolla', 'Ampolla'),
        ('crema_ungüento', 'Crema / Ungüento'),
        ('parche', 'Parche'),
        ('inhalador', 'Inhalador'),
        ('supositorio', 'Supositorio'),
        ('ovulo', 'Óvulo'),
        ('insulina', 'Insulina'),
    ]

    nombre_generico = models.CharField(
        max_length=200,
        verbose_name='Nombre genérico'
    )
    nombre_comercial = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Nombre comercial'
    )
    concentracion = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Concentración'
    )
    forma_farmaceutica = models.CharField(
        max_length=30,
        choices=FORMAS_FARMACEUTICAS,
        blank=True,
        verbose_name='Forma farmacéutica'
    )
    unidad_dosificacion = models.CharField(
        max_length=20,
        choices=UNIDADES_DOSIS,
        blank=True,
        verbose_name='Unidad de dosificación'
    )
    requiere_refrigeracion = models.BooleanField(
        default=False,
        verbose_name='Requiere refrigeración'
    )
    control_especial = models.BooleanField(
        default=False,
        verbose_name='Medicamento de control especial'
    )
    # Catálogo híbrido: hogar=NULL es el catálogo base compartido;
    # hogar=X es un alta propia de ese hogar (ver plan, sección 2.1).
    hogar = models.ForeignKey(
        Hogar,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='medicamentos',
        verbose_name='Hogar (vacío = catálogo general)'
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'medicamentos_medicamento'
        verbose_name = 'Medicamento'
        verbose_name_plural = 'Medicamentos'
        ordering = ['nombre_generico', 'concentracion']

    def __str__(self):
        partes = [self.nombre_generico]
        if self.concentracion:
            partes.append(self.concentracion)
        texto = ' '.join(partes)
        if self.nombre_comercial:
            texto += f' ({self.nombre_comercial})'
        return texto

    def promover_a_catalogo_general(self):
        """Solo superadmin. Vuelve NULL el hogar de esta fila sin migrar ni
        duplicar datos: cualquier Prescripcion/IngresoMedicamento que ya
        apunte a ella sigue apuntando a la misma fila (ver plan 2.1)."""
        self.hogar = None
        self.save(update_fields=['hogar'])


def _ruta_formula(instance, filename):
    import os
    import uuid
    extension = os.path.splitext(filename)[1].lower()
    return (
        f'medicamentos/formulas/hogar_{instance.residente.hogar_id}/'
        f'residente_{instance.residente_id}/{uuid.uuid4().hex}{extension}'
    )


class Prescripcion(models.Model):

    HORARIOS_FIJOS = 'horarios_fijos'
    PRN = 'prn'
    TIPO_PAUTA = [
        (HORARIOS_FIJOS, 'Horarios fijos'),
        (PRN, 'Por razón necesaria (PRN)'),
    ]

    ACTIVA = 'activa'
    SUSPENDIDA = 'suspendida'
    FINALIZADA = 'finalizada'
    ESTADOS = [
        (ACTIVA, 'Activa'),
        (SUSPENDIDA, 'Suspendida'),
        (FINALIZADA, 'Finalizada'),
    ]

    residente = models.ForeignKey(
        Residente,
        on_delete=models.PROTECT,
        related_name='prescripciones'
    )
    medicamento = models.ForeignKey(
        Medicamento,
        on_delete=models.PROTECT,
        related_name='prescripciones'
    )
    dosis_cantidad = models.DecimalField(
        max_digits=6, decimal_places=2,
        verbose_name='Cantidad de la dosis'
    )
    dosis_unidad = models.CharField(
        max_length=20,
        choices=UNIDADES_DOSIS,
        verbose_name='Unidad de la dosis'
    )
    via_administracion = models.CharField(
        max_length=20,
        choices=VIA_ADMINISTRACION,
        default='oral',
        verbose_name='Vía de administración'
    )
    tipo_pauta = models.CharField(
        max_length=20,
        choices=TIPO_PAUTA,
        default=HORARIOS_FIJOS,
        verbose_name='Tipo de pauta'
    )
    frecuencia_minima_horas = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name='Frecuencia mínima entre tomas (horas)',
        help_text='Solo aplica a pautas PRN.'
    )
    dosis_maxima_dia = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name='Máximo de tomas al día',
        help_text='Tope informativo, solo aplica a pautas PRN.'
    )
    dias_semana = models.CharField(
        max_length=7,
        default='LMXJVSD',
        verbose_name='Días de la semana',
        help_text='L=lunes ... D=domingo, ej: "LMXJVSD" o "LXV"'
    )
    fecha_inicio = models.DateField(verbose_name='Fecha de inicio')
    fecha_fin = models.DateField(
        null=True, blank=True,
        verbose_name='Fecha de fin',
        help_text='Vacío = tratamiento crónico / indefinido'
    )
    cantidad_total_formulada = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        verbose_name='Cantidad total formulada',
        help_text='Informativo, ej: 21 tabletas'
    )
    indicaciones = models.TextField(
        blank=True,
        verbose_name='Indicaciones',
        help_text='Ej: con alimentos, no triturar, media hora antes'
    )
    diagnostico = models.ForeignKey(
        DiagnosticoResidente,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='prescripciones',
        verbose_name='Diagnóstico relacionado'
    )

    # El tratamiento lo formula la EPS afuera del sistema; aquí se
    # transcribe. El respaldo legal recae en el documento externo, no en
    # quien digita (ver plan, sección 2.2).
    formulada_por = models.CharField(
        max_length=200,
        verbose_name='Formulada por',
        help_text='Ej: "Dr. Restrepo — Sanitas"'
    )
    fecha_formula = models.DateField(verbose_name='Fecha de la fórmula')
    numero_formula = models.CharField(
        max_length=50, blank=True,
        verbose_name='Número de fórmula'
    )
    # Foto de la fórmula: historia clínica, en el almacenamiento privado y
    # servida solo por la vista tratamiento_formula_ver (permiso + auditoría).
    archivo_formula = models.FileField(
        upload_to=_ruta_formula,
        storage=almacenamiento_privado,
        max_length=255,
        null=True, blank=True,
        verbose_name='Archivo de la fórmula (foto o escaneo)'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=ACTIVA
    )
    motivo_suspension = models.TextField(
        blank=True,
        verbose_name='Motivo de suspensión'
    )
    fecha_suspension = models.DateTimeField(null=True, blank=True)
    suspendida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='prescripciones_suspendidas'
    )
    reemplaza_a = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reemplazos',
        verbose_name='Reemplaza a'
    )

    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='prescripciones_registradas'
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'medicamentos_prescripcion'
        verbose_name = 'Prescripción'
        verbose_name_plural = 'Prescripciones'
        ordering = ['-fecha_registro']

    def __str__(self):
        return f'{self.medicamento} — {self.residente} ({self.get_estado_display()})'

    def tiene_administraciones(self):
        return self.administraciones.exists()

    def puede_editarse(self):
        """Mientras no tenga ninguna administración registrada es una
        corrección de digitación; en cuanto tiene la primera, ya es
        historia clínica y solo se suspende/reemplaza (ver plan 2.2)."""
        return self.estado == self.ACTIVA and not self.tiene_administraciones()

    def es_prn(self):
        return self.tipo_pauta == self.PRN

    def vigente_en(self, fecha):
        if self.estado != self.ACTIVA:
            return False
        if fecha < self.fecha_inicio:
            return False
        if self.fecha_fin and fecha > self.fecha_fin:
            return False
        letra = 'LMXJVSD'[fecha.weekday()]
        return letra in self.dias_semana


class HorarioPrescripcion(models.Model):
    prescripcion = models.ForeignKey(
        Prescripcion,
        on_delete=models.CASCADE,
        related_name='horarios'
    )
    hora = models.TimeField()

    class Meta:
        db_table = 'medicamentos_horario_prescripcion'
        verbose_name = 'Horario de prescripción'
        verbose_name_plural = 'Horarios de prescripción'
        ordering = ['hora']
        unique_together = ('prescripcion', 'hora')

    def __str__(self):
        return f'{self.prescripcion} — {self.hora.strftime("%H:%M")}'


class IngresoMedicamento(models.Model):

    DISPONIBLE = 'disponible'
    AGOTADO = 'agotado'
    VENCIDO = 'vencido'
    DESCARTADO = 'descartado'
    DEVUELTO = 'devuelto'
    ESTADOS = [
        (DISPONIBLE, 'Disponible'),
        (AGOTADO, 'Agotado'),
        (VENCIDO, 'Vencido'),
        (DESCARTADO, 'Descartado'),
        (DEVUELTO, 'Devuelto a la familia'),
    ]

    UNIDADES_INGRESO = [
        ('tabletas', 'Tabletas'),
        ('capsulas', 'Cápsulas'),
        ('ml', 'mL'),
        ('ampollas', 'Ampollas'),
        ('sobres', 'Sobres'),
        ('frascos', 'Frascos'),
        ('otro', 'Otro'),
    ]

    # Dueño del lote: un residente (lo trajo su familia) o, si es nulo,
    # el hogar directamente (botiquín común — ver plan 2.3). Nunca ambos,
    # nunca ninguno: se valida en clean().
    residente = models.ForeignKey(
        Residente,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='ingresos_medicamento'
    )
    hogar = models.ForeignKey(
        Hogar,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='botiquin_ingresos',
        verbose_name='Hogar (botiquín común)'
    )
    medicamento = models.ForeignKey(
        Medicamento,
        on_delete=models.PROTECT,
        related_name='ingresos'
    )
    lote = models.CharField(max_length=50, verbose_name='Lote')
    fecha_vencimiento = models.DateField(verbose_name='Fecha de vencimiento')
    cantidad_ingresada = models.DecimalField(
        max_digits=8, decimal_places=2,
        verbose_name='Cantidad ingresada'
    )
    cantidad_disponible = models.DecimalField(
        max_digits=8, decimal_places=2,
        verbose_name='Cantidad disponible'
    )
    unidad = models.CharField(
        max_length=20,
        choices=UNIDADES_INGRESO,
        default='tabletas'
    )
    fecha_ingreso = models.DateField(
        default=timezone.localdate,
        verbose_name='Fecha de ingreso'
    )
    entregado_por = models.CharField(
        max_length=200, blank=True,
        verbose_name='Entregado por',
        help_text='Nombre del familiar que lo trajo (vacío si es compra del hogar)'
    )
    recibido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='ingresos_recibidos'
    )
    observaciones = models.TextField(blank=True)
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=DISPONIBLE
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'medicamentos_ingreso'
        verbose_name = 'Ingreso de medicamento'
        verbose_name_plural = 'Ingresos de medicamento'
        ordering = ['fecha_vencimiento']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(residente__isnull=False, hogar__isnull=True) |
                    Q(residente__isnull=True, hogar__isnull=False)
                ),
                name='ingreso_dueno_unico_residente_o_hogar'
            )
        ]

    def __str__(self):
        dueno = self.residente if self.residente_id else f'Botiquín — {self.hogar}'
        return f'{self.medicamento} · lote {self.lote} · {dueno}'

    def es_botiquin(self):
        return self.residente_id is None

    def dias_para_vencer(self):
        return (self.fecha_vencimiento - timezone.localdate()).days

    def semaforo(self, dias_verde=365, dias_amarillo=180):
        """Propiedad calculada, nunca guardada (ver plan 2.3). Sobre el
        lote, no sobre el medicamento."""
        dias = self.dias_para_vencer()
        if dias < 0:
            return 'vencido'
        if dias < dias_amarillo:
            return 'rojo'
        if dias < dias_verde:
            return 'amarillo'
        return 'verde'

    def esta_vencido(self):
        return self.dias_para_vencer() < 0


class Administracion(models.Model):

    ADMINISTRADO = 'administrado'
    NO_ADMINISTRADO = 'no_administrado'
    ESTADOS = [
        (ADMINISTRADO, 'Suministrado'),
        (NO_ADMINISTRADO, 'No suministrado'),
    ]

    MOTIVOS_NO_ADMINISTRACION = [
        ('sin_existencias', 'Sin existencias'),
        ('residente_rechazo', 'El residente rechazó el medicamento'),
        ('suspendido_por_medico', 'Suspendido por el médico'),
        ('residente_hospitalizado', 'Residente hospitalizado'),
        ('residente_ausente', 'Residente ausente'),
        ('residente_dormido', 'Residente dormido'),
        ('contraindicado_en_el_momento', 'Contraindicado en el momento'),
        ('lote_vencido', 'Lote vencido'),
        ('otro', 'Otro'),
    ]

    PRESTAMO = 'prestamo'
    EMERGENCIA = 'emergencia'
    OTRO_BOTIQUIN = 'otro'
    MOTIVOS_USO_BOTIQUIN = [
        (PRESTAMO, 'Préstamo — se espera reposición de la familia'),
        (EMERGENCIA, 'Emergencia — no se espera reposición'),
        (OTRO_BOTIQUIN, 'Otro'),
    ]

    # Campos que sí pueden actualizarse después de creada la fila —
    # anulación acotada y marcado de reposición del botiquín. Cualquier
    # otro intento de update se rechaza (ver save()).
    CAMPOS_ANULACION = {'anulada', 'motivo_anulacion', 'anulada_por', 'fecha_anulacion'}
    CAMPOS_REPOSICION = {'repuesto', 'fecha_reposicion', 'repuesto_marcado_por'}
    CAMPOS_EDITABLES_POST_CREACION = CAMPOS_ANULACION | CAMPOS_REPOSICION

    prescripcion = models.ForeignKey(
        Prescripcion,
        on_delete=models.PROTECT,
        related_name='administraciones'
    )
    # Denormalizado a propósito para consultas rápidas (ver plan 2.5).
    residente = models.ForeignKey(
        Residente,
        on_delete=models.PROTECT,
        related_name='administraciones_medicamento'
    )
    fecha_programada = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Fecha y hora programada',
        help_text='Vacío en tomas PRN'
    )
    horario = models.ForeignKey(
        HorarioPrescripcion,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='administraciones'
    )
    estado = models.CharField(max_length=20, choices=ESTADOS)
    fecha_administracion = models.DateTimeField(auto_now_add=True)
    cantidad_administrada = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name='Cantidad suministrada'
    )
    ingreso_usado = models.ForeignKey(
        IngresoMedicamento,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='administraciones',
        verbose_name='Lote usado (FEFO)'
    )
    motivo_no_administracion = models.CharField(
        max_length=40,
        choices=MOTIVOS_NO_ADMINISTRACION,
        blank=True
    )
    observacion = models.TextField(
        blank=True,
        help_text='Obligatoria si la dosis fue parcial, si es PRN, o si se usó el botiquín'
    )
    motivo_uso_botiquin = models.CharField(
        max_length=20,
        choices=MOTIVOS_USO_BOTIQUIN,
        blank=True
    )
    repuesto = models.BooleanField(
        default=False,
        verbose_name='Repuesto',
        help_text='Solo aplica si motivo_uso_botiquin = préstamo'
    )
    fecha_reposicion = models.DateField(null=True, blank=True)
    repuesto_marcado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reposiciones_marcadas'
    )
    administrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='administraciones_realizadas'
    )
    nota_clinica = models.ForeignKey(
        NotaClinica,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='administraciones_medicamento'
    )
    anulada = models.BooleanField(default=False)
    motivo_anulacion = models.TextField(blank=True)
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='anulaciones_administracion'
    )
    fecha_anulacion = models.DateTimeField(null=True, blank=True)
    hash_integridad = models.CharField(max_length=64, editable=False, blank=True)

    class Meta:
        db_table = 'medicamentos_administracion'
        verbose_name = 'Administración'
        verbose_name_plural = 'Administraciones'
        ordering = ['-fecha_administracion']
        constraints = [
            # Protección contra doble registro (dos auxiliares marcando la
            # misma toma, o un doble clic) — ver plan 2.5. Las anuladas no
            # cuentan, y las tomas PRN (fecha_programada NULL) nunca chocan
            # entre sí porque Postgres no compara NULLs como iguales.
            models.UniqueConstraint(
                fields=['prescripcion', 'fecha_programada'],
                condition=Q(anulada=False),
                name='uniq_administracion_prescripcion_fecha_programada'
            )
        ]

    def __str__(self):
        return f'{self.prescripcion} — {self.get_estado_display()} ({self.fecha_administracion})'

    def es_dosis_parcial(self):
        if self.cantidad_administrada is None:
            return False
        return self.cantidad_administrada != self.prescripcion.dosis_cantidad

    def es_uso_botiquin(self):
        return bool(self.ingreso_usado_id and self.ingreso_usado.es_botiquin())

    def puede_anularse_por(self, usuario, minutos_anulacion=120):
        """Dos niveles (ver plan 4.6): el autor, dentro de la ventana
        acotada; el jefe de enfermería, cualquier registro del hogar
        durante el resto de ese mismo día."""
        if self.anulada:
            return False
        from usuarios.models import Rol
        ahora = timezone.now()
        if usuario.tiene_rol(Rol.JEFE_ENFERMERIA) and self.fecha_administracion.date() == ahora.date():
            return True
        if self.administrada_por_id == usuario.id:
            limite = self.fecha_administracion + timedelta(minutes=minutos_anulacion)
            return ahora <= limite
        return False

    def save(self, *args, **kwargs):
        if not self.pk:
            contenido_hash = (
                f'{self.prescripcion_id}'
                f'{self.residente_id}'
                f'{self.estado}'
                f'{self.cantidad_administrada}'
                f'{self.motivo_no_administracion}'
                f'{self.observacion}'
                f'{self.ingreso_usado_id}'
                f'{self.administrada_por_id}'
            )
            self.hash_integridad = hashlib.sha256(
                contenido_hash.encode('utf-8')
            ).hexdigest()
        else:
            update_fields = kwargs.get('update_fields')
            if not update_fields or not set(update_fields).issubset(self.CAMPOS_EDITABLES_POST_CREACION):
                raise ValueError(
                    'Las administraciones son inmutables. Solo se permite anular '
                    '(dentro de la ventana permitida) o marcar la reposición del botiquín.'
                )
        super().save(*args, **kwargs)


class MovimientoInventario(models.Model):

    ENTRADA = 'entrada'
    SALIDA_ADMINISTRACION = 'salida_administracion'
    AJUSTE = 'ajuste'
    DESCARTE_VENCIDO = 'descarte_vencido'
    DEVOLUCION_FAMILIA = 'devolucion_familia'
    TIPOS = [
        (ENTRADA, 'Entrada'),
        (SALIDA_ADMINISTRACION, 'Salida por suministro'),
        (AJUSTE, 'Ajuste'),
        (DESCARTE_VENCIDO, 'Descarte por vencimiento'),
        (DEVOLUCION_FAMILIA, 'Devolución a la familia'),
    ]

    ingreso = models.ForeignKey(
        IngresoMedicamento,
        on_delete=models.PROTECT,
        related_name='movimientos'
    )
    tipo = models.CharField(max_length=30, choices=TIPOS)
    cantidad = models.DecimalField(
        max_digits=8, decimal_places=2,
        verbose_name='Cantidad',
        help_text='Positiva en entradas, negativa en salidas'
    )
    administracion = models.ForeignKey(
        Administracion,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='movimientos'
    )
    motivo = models.TextField(
        blank=True,
        help_text='Obligatorio en ajuste y descarte'
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='movimientos_inventario'
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'medicamentos_movimiento_inventario'
        verbose_name = 'Movimiento de inventario'
        verbose_name_plural = 'Movimientos de inventario'
        ordering = ['-fecha']

    def save(self, *args, **kwargs):
        # Libro mayor inmutable — mismo patrón que RegistroAuditoria.
        if self.pk:
            raise ValueError(
                'Los movimientos de inventario son inmutables y no pueden modificarse.'
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_tipo_display()} {self.cantidad} — {self.ingreso} ({self.fecha.date() if self.fecha else ""})'


class ConfiguracionMedicamentos(models.Model):

    def _horas_estandar_default():
        return {
            'desayuno': '07:00',
            'almuerzo': '12:30',
            'cena': '18:30',
            'noche': '21:00',
        }

    hogar = models.OneToOneField(
        Hogar,
        on_delete=models.CASCADE,
        related_name='configuracion_medicamentos'
    )
    dias_semaforo_verde = models.PositiveIntegerField(
        default=365,
        verbose_name='Días para semáforo verde'
    )
    dias_semaforo_amarillo = models.PositiveIntegerField(
        default=180,
        verbose_name='Días para semáforo amarillo'
    )
    horas_estandar = models.JSONField(
        default=_horas_estandar_default,
        verbose_name='Horas estándar sugeridas'
    )
    ventana_ronda_horas = models.PositiveIntegerField(
        default=2,
        verbose_name='Ventana de la ronda (horas)'
    )
    minutos_anulacion = models.PositiveIntegerField(
        default=120,
        verbose_name='Minutos para anulación'
    )
    alerta_stock_dias = models.PositiveIntegerField(
        default=5,
        verbose_name='Avisar cuando queden menos de N días de tratamiento'
    )

    class Meta:
        db_table = 'medicamentos_configuracion'
        verbose_name = 'Configuración de medicamentos'
        verbose_name_plural = 'Configuraciones de medicamentos'

    def __str__(self):
        return f'Configuración de medicamentos — {self.hogar}'

    @classmethod
    def para_hogar(cls, hogar):
        config, _ = cls.objects.get_or_create(hogar=hogar)
        return config
