from django.db import models
from django.conf import settings


class RegistroAuditoria(models.Model):
    INICIO_SESION = 'inicio_sesion'
    CIERRE_SESION = 'cierre_sesion'
    CONSULTA_EXPEDIENTE = 'consulta_expediente'
    CREACION_NOTA = 'creacion_nota'
    EXPORTACION = 'exportacion'
    CREACION_RESIDENTE = 'creacion_residente'
    ASIGNACION_CAMA = 'asignacion_cama'
    RESETEO_PASSWORD = 'reseteo_password'

    # Módulo de medicamentos — solo lo excepcional; la rutina de
    # administración diaria ya queda trazada en el propio modelo
    # Administracion (inmutable, con hash) y no se duplica aquí
    # (ver plan-modulo-medicamentos.md, sección 5).
    PRESCRIPCION_CREADA = 'prescripcion_creada'
    PRESCRIPCION_SUSPENDIDA = 'prescripcion_suspendida'
    INGRESO_MEDICAMENTO = 'ingreso_medicamento'
    NO_ADMINISTRACION = 'no_administracion'
    AJUSTE_INVENTARIO = 'ajuste_inventario'
    DESCARTE_VENCIDO = 'descarte_vencido'
    ANULACION_ADMINISTRACION = 'anulacion_administracion'
    USO_BOTIQUIN = 'uso_botiquin'

    # Módulo de exámenes y paraclínicos.
    EXAMEN_REGISTRADO = 'examen_registrado'
    RESULTADO_EXAMEN = 'resultado_examen'
    ADENDA_EXAMEN = 'adenda_examen'
    CORRECCION_RESULTADO = 'correccion_resultado'
    REVISION_EXAMEN = 'revision_examen'
    CANCELACION_EXAMEN = 'cancelacion_examen'
    CONSULTA_RESULTADO = 'consulta_resultado'

    # Alergias y antecedentes.
    ALERGIA_REGISTRADA = 'alergia_registrada'
    ALERGIA_INACTIVADA = 'alergia_inactivada'
    SIN_ALERGIAS = 'sin_alergias'
    ANTECEDENTE_REGISTRADO = 'antecedente_registrado'
    ANTECEDENTE_INACTIVADO = 'antecedente_inactivado'
    ORDEN_PESE_A_ALERGIA = 'orden_pese_a_alergia'

    # Citas médicas.
    CITA_REGISTRADA = 'cita_registrada'
    CITA_MODIFICADA = 'cita_modificada'
    CITA_CERRADA = 'cita_cerrada'
    CITA_CANCELADA = 'cita_cancelada'

    # Alertas.
    AVISO_CREADO = 'aviso_creado'
    ALERTA_ATENDIDA = 'alerta_atendida'
    ALERTA_DESCARTADA = 'alerta_descartada'
    CONFIGURACION_ALERTAS = 'configuracion_alertas'

    ACCIONES = [
        (INICIO_SESION, 'Inicio de sesión'),
        (CIERRE_SESION, 'Cierre de sesión'),
        (CONSULTA_EXPEDIENTE, 'Consulta de expediente'),
        (CREACION_NOTA, 'Creación de nota clínica'),
        (EXPORTACION, 'Exportación de expediente'),
        (CREACION_RESIDENTE, 'Registro de residente'),
        (ASIGNACION_CAMA, 'Asignación de cama'),
        (RESETEO_PASSWORD, 'Restablecimiento de contraseña'),
        (PRESCRIPCION_CREADA, 'Registro de orden médica'),
        (PRESCRIPCION_SUSPENDIDA, 'Suspensión de orden médica'),
        (INGRESO_MEDICAMENTO, 'Medicamentos guardados en el cajón o el botiquín'),
        (NO_ADMINISTRACION, 'Medicamento no suministrado'),
        (AJUSTE_INVENTARIO, 'Ajuste de inventario de medicamentos'),
        (DESCARTE_VENCIDO, 'Descarte de lote vencido'),
        (ANULACION_ADMINISTRACION, 'Anulación de un suministro'),
        (USO_BOTIQUIN, 'Uso del botiquín del hogar'),
        (EXAMEN_REGISTRADO, 'Registro de orden de examen'),
        (RESULTADO_EXAMEN, 'Carga de resultado de examen'),
        (ADENDA_EXAMEN, 'Información adicional en examen'),
        (CORRECCION_RESULTADO, 'Corrección de valor de examen'),
        (REVISION_EXAMEN, 'Revisión médica de examen'),
        (CANCELACION_EXAMEN, 'Cancelación de orden de examen'),
        (CONSULTA_RESULTADO, 'Consulta de archivo de resultado'),
        (ALERGIA_REGISTRADA, 'Registro de alergia'),
        (ALERGIA_INACTIVADA, 'Inactivación de alergia'),
        (SIN_ALERGIAS, 'Declaración de sin alergias conocidas'),
        (ANTECEDENTE_REGISTRADO, 'Registro de antecedente'),
        (ANTECEDENTE_INACTIVADO, 'Inactivación de antecedente'),
        (ORDEN_PESE_A_ALERGIA, 'Orden médica registrada pese a alergia'),
        (CITA_REGISTRADA, 'Cita médica agendada'),
        (CITA_MODIFICADA, 'Cita médica corregida o reprogramada'),
        (CITA_CERRADA, 'Registro de lo que pasó en una cita'),
        (CITA_CANCELADA, 'Cita médica cancelada'),
        (AVISO_CREADO, 'Aviso manual publicado'),
        (ALERTA_ATENDIDA, 'Alerta atendida'),
        (ALERTA_DESCARTADA, 'Alerta descartada'),
        (CONFIGURACION_ALERTAS, 'Cambio en la configuración de alertas'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='registros_auditoria',
        null=True
    )
    accion = models.CharField(max_length=50, choices=ACCIONES)
    descripcion = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'auditoria'
        verbose_name = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'
        ordering = ['-timestamp']

    def save(self, *args, **kwargs):
        # Inmutabilidad — no permite modificaciones
        if self.pk:
            raise ValueError(
                'Los registros de auditoría son inmutables.'
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.usuario} — {self.get_accion_display()} ({self.timestamp})'