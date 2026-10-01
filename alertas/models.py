"""Alertas del hogar.

Dos orígenes:
- Sistema: las genera el motor (alertas/motor.py) a partir de reglas que
  miran los datos (un examen con valores críticos, un lote vencido, una
  cita mañana...). Cada condición tiene una `clave` estable; mientras la
  condición exista hay UNA alerta vigente con esa clave (no se repite cada
  vez que se evalúa) y cuando la condición desaparece el sistema la marca
  como resuelta sola.
- Manual: avisos que publica una persona para un rol o para todo el
  personal ("la señora X no ha querido comer, ofrecerle líquidos"); vencen
  solos.

Las alertas pertenecen al HOGAR y se dirigen a ROLES (no a personas): el
turno cambia, el rol queda. Cada persona ve las alertas de sus roles.

Estados:
    nueva → atendida (alguien la vio y actuó; queda quién y qué hizo)
          → resuelta (la condición desapareció; la cierra el sistema)
          → descartada (no aplica; con motivo)
          → vencida (avisos manuales cuya vigencia terminó)
Nada se borra.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from hogares.models import Hogar
from residentes.models import Residente


class Alerta(models.Model):
    CRITICA = 'critica'
    ALTA = 'alta'
    MEDIA = 'media'
    INFORMATIVA = 'informativa'
    GRAVEDADES = [
        (CRITICA, 'Crítica'),
        (ALTA, 'Alta'),
        (MEDIA, 'Media'),
        (INFORMATIVA, 'Informativa'),
    ]
    ORDEN_GRAVEDAD = {CRITICA: 0, ALTA: 1, MEDIA: 2, INFORMATIVA: 3}

    NUEVA = 'nueva'
    ATENDIDA = 'atendida'
    RESUELTA = 'resuelta'
    DESCARTADA = 'descartada'
    VENCIDA = 'vencida'
    ESTADOS = [
        (NUEVA, 'Nueva'),
        (ATENDIDA, 'Atendida'),
        (RESUELTA, 'Resuelta por el sistema'),
        (DESCARTADA, 'Descartada'),
        (VENCIDA, 'Vencida'),
    ]
    ACTIVAS = [NUEVA, ATENDIDA]

    SISTEMA = 'sistema'
    MANUAL = 'manual'
    ORIGENES = [(SISTEMA, 'Sistema'), (MANUAL, 'Aviso del personal')]

    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name='alertas')
    residente = models.ForeignKey(Residente, on_delete=models.PROTECT, null=True, blank=True, related_name='alertas')
    regla = models.CharField(max_length=40)
    clave = models.CharField(max_length=120)
    origen = models.CharField(max_length=10, choices=ORIGENES, default=SISTEMA)
    gravedad = models.CharField(max_length=12, choices=GRAVEDADES)
    titulo = models.CharField(max_length=200)
    mensaje = models.TextField(blank=True)
    url_accion = models.CharField(max_length=300, blank=True)
    texto_accion = models.CharField(max_length=60, blank=True)
    # ",medico,jefe_enfermeria," — con comas a los lados para filtrar con
    # `contains` en cualquier base de datos.
    roles_destino = models.CharField(max_length=300)

    estado = models.CharField(max_length=12, choices=ESTADOS, default=NUEVA)
    # La condición que la originó sigue presente. Solo puede haber una
    # alerta vigente por clave y hogar.
    vigente = models.BooleanField(default=True)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )
    fecha_creacion = models.DateTimeField(default=timezone.now)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    vence = models.DateTimeField(null=True, blank=True)
    atendida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )
    fecha_atencion = models.DateTimeField(null=True, blank=True)
    nota_atencion = models.TextField(blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['fecha_creacion']
        verbose_name = 'Alerta'
        verbose_name_plural = 'Alertas'
        constraints = [
            models.UniqueConstraint(
                fields=['hogar', 'clave'], condition=Q(vigente=True), name='alerta_vigente_unica_por_clave',
            ),
        ]
        indexes = [models.Index(fields=['hogar', 'estado'])]

    def __str__(self):
        return self.titulo

    def delete(self, *args, **kwargs):
        raise ValueError('Las alertas no se eliminan.')

    # Roles ─────────────────────────────────────────────────────────
    @staticmethod
    def codificar_roles(roles):
        return ',' + ','.join(sorted(set(roles))) + ','

    @property
    def lista_roles(self):
        return [r for r in self.roles_destino.split(',') if r]

    def nombres_roles(self):
        from usuarios.models import Rol
        nombres = dict(Rol.ROLES)
        return [nombres.get(r, r) for r in self.lista_roles]

    @classmethod
    def filtro_roles(cls, roles):
        q = Q(pk__in=[])
        for r in roles:
            q |= Q(roles_destino__contains=f',{r},')
        return q

    def es_para(self, usuario):
        return bool(set(self.lista_roles) & set(usuario.roles.values_list('nombre', flat=True)))

    @property
    def activa(self):
        return self.estado in self.ACTIVAS

    @property
    def orden(self):
        return self.ORDEN_GRAVEDAD[self.gravedad]


class VistaAlerta(models.Model):
    """Quién ya vio una alerta (para resaltar las que son nuevas para cada
    persona). Ver no es atender."""
    alerta = models.ForeignKey(Alerta, on_delete=models.CASCADE, related_name='vistas')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['alerta', 'usuario'], name='vista_alerta_unica')]


class ConfiguracionAlertas(models.Model):
    hogar = models.OneToOneField(Hogar, on_delete=models.CASCADE, related_name='configuracion_alertas')
    umbrales = models.JSONField(default=dict, blank=True)
    reglas_desactivadas = models.JSONField(default=list, blank=True)
    ultima_evaluacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Configuración de alertas'
        verbose_name_plural = 'Configuraciones de alertas'

    @classmethod
    def para_hogar(cls, hogar):
        config, _ = cls.objects.get_or_create(hogar=hogar)
        return config

    def umbral(self, nombre):
        from .reglas import UMBRALES
        valor = self.umbrales.get(nombre)
        return int(valor) if valor not in (None, '') else UMBRALES[nombre]['defecto']

    def regla_activa(self, codigo):
        return codigo not in (self.reglas_desactivadas or [])
