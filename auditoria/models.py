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

    ACCIONES = [
        (INICIO_SESION, 'Inicio de sesión'),
        (CIERRE_SESION, 'Cierre de sesión'),
        (CONSULTA_EXPEDIENTE, 'Consulta de expediente'),
        (CREACION_NOTA, 'Creación de nota clínica'),
        (EXPORTACION, 'Exportación de expediente'),
        (CREACION_RESIDENTE, 'Registro de residente'),
        (ASIGNACION_CAMA, 'Asignación de cama'),
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