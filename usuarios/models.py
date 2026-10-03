from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from hogares.models import Hogar


class Rol(models.Model):
    SUPERADMIN = 'superadmin'
    ADMINISTRADOR = 'administrador'
    MEDICO = 'medico'
    ENFERMERO = 'enfermero'
    JEFE_ENFERMERIA = 'jefe_enfermeria'
    FISIOTERAPEUTA = 'fisioterapeuta'
    NUTRICIONISTA = 'nutricionista'
    PSICOLOGO = 'psicologo'
    TRABAJO_SOCIAL = 'trabajo_social'
    TERAPEUTA_OCUPACIONAL = 'terapeuta_ocupacional'

    ROLES = [
        (SUPERADMIN, 'Superadministrador'),
        (ADMINISTRADOR, 'Administrador del Hogar'),
        (MEDICO, 'Médico'),
        (ENFERMERO, 'Auxiliar de Enfermería'),
        (JEFE_ENFERMERIA, 'Jefe de Enfermería'),
        (FISIOTERAPEUTA, 'Fisioterapeuta'),
        (NUTRICIONISTA, 'Nutricionista'),
        (PSICOLOGO, 'Psicólogo/a'),
        (TRABAJO_SOCIAL, 'Trabajador/a Social'),
        (TERAPEUTA_OCUPACIONAL, 'Terapeuta Ocupacional'),
    ]

    # Roles clínicos: acceso a residentes/notas del propio hogar, pero no
    # a gestión administrativa del hogar (infraestructura, catálogos, etc.)
    ROLES_CLINICOS = [
        MEDICO, ENFERMERO, JEFE_ENFERMERIA, FISIOTERAPEUTA,
        NUTRICIONISTA, PSICOLOGO, TRABAJO_SOCIAL,
        TERAPEUTA_OCUPACIONAL
    ]

    # Quién puede exportar el expediente en PDF. El superadmin ya no hace
    # trabajo clínico/operativo del hogar, así que no exporta expedientes.
    ROLES_EXPORTACION = [ADMINISTRADOR, MEDICO, JEFE_ENFERMERIA]

    # Quién puede agregar/quitar diagnósticos de un residente YA existente.
    # El administrador del hogar entra aquí (2026-09-17): transcribe
    # diagnósticos con el mismo criterio de "transcripción de documento
    # externo" que rige el registro de tratamientos del módulo de
    # medicamentos (ver plan-modulo-medicamentos.md, sección 4.5).
    ROLES_GESTION_DIAGNOSTICOS = [ADMINISTRADOR, MEDICO, JEFE_ENFERMERIA]

    # ── Roles del módulo de medicamentos ──────────────────────────
    # El administrador registra información y custodia existencias, pero
    # nunca toca al residente; el acto clínico queda solo en manos
    # clínicas (ver plan-modulo-medicamentos.md, sección 4).
    ROLES_REGISTRO_TRATAMIENTO = [ADMINISTRADOR, MEDICO, JEFE_ENFERMERIA]
    ROLES_INGRESO_MEDICAMENTO = [ADMINISTRADOR, JEFE_ENFERMERIA, ENFERMERO]
    ROLES_ADMINISTRACION = [MEDICO, JEFE_ENFERMERIA, ENFERMERO]
    # La ronda de medicamentos es trabajo de enfermería; el médico suministra
    # desde "Medicamentos de hoy" de cada residente cuando lo considera necesario.
    ROLES_RONDA = [JEFE_ENFERMERIA, ENFERMERO]
    ROLES_AJUSTE_INVENTARIO = [ADMINISTRADOR, JEFE_ENFERMERIA]

    NOTA_POR_ROL = {
        MEDICO: 'evolucion',
        ENFERMERO: 'enfermeria',
        JEFE_ENFERMERIA: 'enfermeria',
        FISIOTERAPEUTA: 'fisioterapia',
        NUTRICIONISTA: 'nutricion',
        PSICOLOGO: 'psicologia',
        TRABAJO_SOCIAL: 'trabajo_social',
        TERAPEUTA_OCUPACIONAL: 'terapia_ocupacional',
    }

    nombre = models.CharField(max_length=50, unique=True, choices=ROLES)
    descripcion = models.TextField(blank=True)

    class Meta:
        db_table = 'roles'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.get_nombre_display()

    def es_clinico(self):
        return self.nombre in self.ROLES_CLINICOS

    def es_administrativo(self):
        return self.nombre in [self.SUPERADMIN, self.ADMINISTRADOR]

    def puede_exportar(self):
        return self.nombre in self.ROLES_EXPORTACION


class Usuario(AbstractUser):
    roles = models.ManyToManyField(
        Rol,
        blank=True,
        related_name='usuarios',
        verbose_name='Roles'
    )
    hogar = models.ForeignKey(
        Hogar,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='usuarios'
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # Bloqueo por intentos fallidos de inicio de sesión
    intentos_fallidos = models.PositiveIntegerField(
        default=0,
        verbose_name='Intentos fallidos de inicio de sesión'
    )
    bloqueado_hasta = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Bloqueado hasta'
    )

    # Contraseña temporal asignada por un administrador (ver
    # usuarios.views.usuario_resetear_password): fuerza al usuario a
    # cambiarla en su próximo inicio de sesión antes de usar el resto
    # de la aplicación.
    debe_cambiar_password = models.BooleanField(
        default=False,
        verbose_name='Debe cambiar la contraseña en el próximo inicio de sesión'
    )

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f'{self.get_full_name()} ({self.username})'

    def esta_bloqueado(self):
        from django.utils import timezone
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())

    def registrar_intento_fallido(self):
        from django.conf import settings as dj_settings
        from django.utils import timezone
        from datetime import timedelta

        self.intentos_fallidos += 1
        maximo = getattr(dj_settings, 'LOGIN_MAX_INTENTOS', 5)
        if self.intentos_fallidos >= maximo:
            minutos = getattr(dj_settings, 'LOGIN_BLOQUEO_MINUTOS', 15)
            self.bloqueado_hasta = timezone.now() + timedelta(minutes=minutos)
        self.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])

    def resetear_intentos(self):
        if self.intentos_fallidos or self.bloqueado_hasta:
            self.intentos_fallidos = 0
            self.bloqueado_hasta = None
            self.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])

    def tiene_rol(self, *nombres):
        return self.roles.filter(nombre__in=nombres).exists()

    def es_clinico(self):
        return self.roles.filter(nombre__in=Rol.ROLES_CLINICOS).exists()

    def es_administrativo(self):
        return self.tiene_rol(Rol.SUPERADMIN, Rol.ADMINISTRADOR)

    def es_superadmin(self):
        return self.tiene_rol(Rol.SUPERADMIN)

    def es_administrador_hogar(self):
        """Administrador del hogar (no superadmin). Es quien gestiona
        residentes, infraestructura y catálogos de SU hogar."""
        return self.tiene_rol(Rol.ADMINISTRADOR)

    def puede_exportar(self):
        return self.roles.filter(nombre__in=Rol.ROLES_EXPORTACION).exists()

    def puede_gestionar_diagnosticos(self):
        """Puede agregar/quitar diagnósticos de un residente existente:
        solo médico y jefe de enfermería."""
        return self.roles.filter(nombre__in=Rol.ROLES_GESTION_DIAGNOSTICOS).exists()

    def tipos_nota_permitidos(self):
        """Retorna lista de tipos de nota que puede crear según sus roles.

        El administrador del hogar y el superadmin NO tienen tipo propio
        aquí a propósito (2026-09-27): todos los tipos de NotaClinica.TIPOS
        representan una disciplina clínica concreta (evolución médica,
        enfermería, fisioterapia, ...) y ninguno de esos dos roles ejerce
        una — es el mismo criterio que ya rige medicamentos, diagnósticos y
        exportación del expediente. Si algún día se necesita que el
        administrador registre observaciones no clínicas, eso pide un tipo
        de nota nuevo y neutral, no reusar uno clínico."""
        tipos = []
        for rol in self.roles.filter(nombre__in=Rol.NOTA_POR_ROL.keys()):
            tipo = Rol.NOTA_POR_ROL.get(rol.nombre)
            if tipo and tipo not in tipos:
                tipos.append(tipo)
        return tipos

    def roles_display(self):
        return ", ".join([r.get_nombre_display() for r in self.roles.all()])


@receiver(m2m_changed, sender=Usuario.roles.through)
def sincronizar_acceso_admin_django(sender, instance, action, **kwargs):
    """Django controla el acceso a /admin/ (el 'Administrador del Sistema')
    con is_staff/is_superuser, no con el sistema de Roles de la app. Un
    usuario creado desde /usuarios/nuevo/ con rol 'superadmin' debe poder
    entrar a /admin/ sin que alguien tenga que marcarlo manualmente ahí,
    así que cada vez que cambian sus roles (alta, edición, admin de Django,
    shell) se revisa si tiene el rol superadmin y se sincronizan ambos
    flags para que coincidan exactamente con esa condición.

    Nota de diseño: esta sincronización es de DOS sentidos — OTORGA
    is_staff/is_superuser cuando el usuario tiene el rol superadmin y los
    QUITA cuando deja de tenerlo (decisión explícita del equipo del
    producto: perder el rol superadmin debe retirar también el acceso a
    /admin/). Esto solo se dispara cuando alguien edita el M2M `roles` de
    un usuario a través de la app, del admin de Django o del shell — nunca
    para una cuenta que nadie ha tocado desde ese ángulo, por ejemplo una
    cuenta de superusuario "pura" creada con `createsuperuser` a la que
    jamás se le asignaron roles: como su M2M `roles` nunca cambia, esta
    señal simplemente no se dispara sobre ella y sus flags no se ven
    afectados. Se considera un límite natural y aceptable de esta señal.
    """
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return
    es_superadmin = instance.roles.filter(nombre=Rol.SUPERADMIN).exists()
    if instance.is_staff != es_superadmin or instance.is_superuser != es_superadmin:
        instance.is_staff = es_superadmin
        instance.is_superuser = es_superadmin
        instance.save(update_fields=['is_staff', 'is_superuser'])